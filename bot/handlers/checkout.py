import logging
from decimal import Decimal

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.database.models import DeliveryType, OrderStatus
from bot.keyboards.user import _fmt_amount, payment_kb
from bot.payments.base import PaymentStatus
from bot.payments.fulfillment import fulfill_paid_order
from bot.payments.registry import PaymentRegistry
from bot.payments.stars import decode_payload
from bot.repositories.order import (
    create_order,
    get_order,
    get_order_with_product,
    set_invoice_data,
)
from bot.repositories.product import count_available_stock, get_product
from bot.repositories.user import upsert_user

router = Router(name="checkout")
log = logging.getLogger(__name__)


# ---- buy: pick provider, create invoice ---------------------------------


@router.callback_query(F.data.startswith("buy:"))
async def start_checkout(
    cb: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
    registry: PaymentRegistry,
) -> None:
    if cb.data is None or cb.from_user is None or cb.message is None:
        await cb.answer()
        return

    try:
        _, product_id_raw, provider_code = cb.data.split(":")
        product_id = int(product_id_raw)
    except ValueError:
        await cb.answer("Неверный запрос", show_alert=True)
        return

    product = await get_product(session, product_id)
    if product is None or not product.is_active:
        await cb.answer("Товар недоступен", show_alert=True)
        return

    provider = registry.get(provider_code)
    if provider is None:
        await cb.answer("Способ оплаты отключён", show_alert=True)
        return

    price = provider.price_for(product)
    if price is None:
        await cb.answer("Для этого товара нет такой валюты", show_alert=True)
        return

    if product.delivery_type == DeliveryType.AUTO:
        if await count_available_stock(session, product.id) <= 0:
            await cb.answer("Товар закончился", show_alert=True)
            return

    await upsert_user(
        session,
        user_id=cb.from_user.id,
        username=cb.from_user.username,
        full_name=cb.from_user.full_name,
    )
    order = await create_order(
        session,
        user_id=cb.from_user.id,
        product_id=product.id,
        provider=provider.code,
        currency=provider.currency,
        amount=Decimal(price),
    )

    try:
        invoice = await provider.create_invoice(
            bot=bot, order=order, product=product, user=cb.from_user
        )
    except Exception:
        log.exception("create_invoice failed (provider=%s)", provider.code)
        await cb.answer("Не удалось создать счёт. Попробуйте позже.", show_alert=True)
        # raise so the middleware rolls back the unused order
        raise

    await set_invoice_data(session, order, invoice.external_id, invoice.payment_url)

    if invoice.sent_inline:
        await cb.answer("Счёт отправлен в чат")
        return

    text = (
        f"🧾 <b>Счёт #{order.id}</b>\n\n"
        f"Товар: <b>{product.title}</b>\n"
        f"К оплате: <b>{_fmt_amount(order.amount, order.currency)}</b>\n"
        f"Способ: {provider.display_name}\n\n"
        "Откройте ссылку, оплатите, затем нажмите «Проверить оплату»."
    )
    await cb.message.answer(
        text,
        reply_markup=payment_kb(
            order_id=order.id,
            payment_url=invoice.payment_url,
            show_check=provider.supports_manual_check,
        ),
    )
    await cb.answer()


# ---- manual "check payment" ---------------------------------------------


@router.callback_query(F.data.startswith("check:"))
async def manual_check(
    cb: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
    registry: PaymentRegistry,
) -> None:
    if cb.data is None or cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    order_id = int(cb.data.split(":", 1)[1])
    order = await get_order(session, order_id)
    if order is None or order.user_id != cb.from_user.id:
        await cb.answer("Заказ не найден", show_alert=True)
        return

    if order.status == OrderStatus.DELIVERED:
        await cb.answer("Уже выдан ✅", show_alert=True)
        return
    if order.status == OrderStatus.AWAITING_DELIVERY:
        await cb.answer(
            "Оплата получена, ждите ручную выдачу.", show_alert=True
        )
        return
    if order.status != OrderStatus.PENDING_PAYMENT:
        await cb.answer(f"Заказ в статусе: {order.status.value}", show_alert=True)
        return

    provider = registry.get(order.provider)
    if provider is None or not provider.supports_manual_check:
        await cb.answer("Этот способ оплаты нельзя проверить вручную", show_alert=True)
        return

    try:
        status = await provider.verify(order)
    except Exception:
        log.exception("verify failed for order %s", order.id)
        await cb.answer("Не удалось связаться с провайдером, попробуйте позже",
                        show_alert=True)
        return

    if status == PaymentStatus.PAID:
        result = await fulfill_paid_order(session, bot, settings, order.id)
        if result.delivered:
            await cb.answer("✅ Оплачено и выдано")
        elif result.awaiting:
            await cb.answer("✅ Оплачено, ждите ручную выдачу", show_alert=True)
        else:
            await cb.answer("Заказ уже обработан")
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    if status in (PaymentStatus.EXPIRED, PaymentStatus.CANCELLED, PaymentStatus.FAILED):
        order.status = OrderStatus.CANCELLED
        await cb.answer(f"Счёт {status.value}", show_alert=True)
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    await cb.answer("Оплата пока не поступила. Попробуйте ещё раз.", show_alert=True)


# ---- user-side cancel ----------------------------------------------------


@router.callback_query(F.data.startswith("cancel:"))
async def cancel_invoice(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.data is None or cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    order_id = int(cb.data.split(":", 1)[1])
    order = await get_order(session, order_id)
    if order is None or order.user_id != cb.from_user.id:
        await cb.answer("Заказ не найден", show_alert=True)
        return
    if order.status == OrderStatus.PENDING_PAYMENT:
        order.status = OrderStatus.CANCELLED
        await cb.answer("Счёт отменён")
    else:
        await cb.answer(f"Уже {order.status.value}", show_alert=True)
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


# ---- Telegram Stars: pre-checkout and successful_payment ----------------


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery, session: AsyncSession) -> None:
    order_id = decode_payload(query.invoice_payload)
    if order_id is None:
        await query.answer(ok=False, error_message="Неверный счёт")
        return
    row = await get_order_with_product(session, order_id)
    if row is None:
        await query.answer(ok=False, error_message="Заказ не найден")
        return
    order, product = row
    if order.user_id != query.from_user.id:
        await query.answer(ok=False, error_message="Чужой счёт")
        return
    if order.provider != "stars":
        await query.answer(ok=False, error_message="Не Stars-счёт")
        return
    if int(order.amount) != query.total_amount:
        await query.answer(ok=False, error_message="Сумма изменилась")
        return
    if product.delivery_type == DeliveryType.AUTO:
        if await count_available_stock(session, product.id) <= 0:
            await query.answer(ok=False, error_message="Товар закончился")
            return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(
    message: Message,
    session: AsyncSession,
    bot: Bot,
    settings: Settings,
) -> None:
    payment = message.successful_payment
    user = message.from_user
    if payment is None or user is None:
        return

    order_id = decode_payload(payment.invoice_payload)
    if order_id is None:
        log.error("Bad invoice payload: %r", payment.invoice_payload)
        return

    order = await get_order(session, order_id)
    if order is None:
        log.error("Paid order %s not found", order_id)
        return

    # Stamp the Telegram charge id onto external_id for traceability.
    order.external_id = payment.telegram_payment_charge_id
    await fulfill_paid_order(session, bot, settings, order.id)
