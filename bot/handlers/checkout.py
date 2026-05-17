import json
import logging

from aiogram import Bot, F, Router
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.database.models import DeliveryType
from bot.repositories.order import (
    create_order,
    mark_awaiting_delivery,
    mark_delivered,
)
from bot.repositories.product import count_available_stock, get_product
from bot.repositories.stock import reserve_one
from bot.repositories.user import upsert_user

router = Router(name="checkout")
log = logging.getLogger(__name__)


def _build_payload(product_id: int) -> str:
    return json.dumps({"p": product_id})


def _parse_payload(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return int(data["p"])
    except (ValueError, TypeError, KeyError):
        return None


@router.callback_query(F.data.startswith("buy:"))
async def start_checkout(
    cb: CallbackQuery, session: AsyncSession, bot: Bot
) -> None:
    if cb.data is None or cb.from_user is None or cb.message is None:
        await cb.answer()
        return

    product_id = int(cb.data.split(":", 1)[1])
    product = await get_product(session, product_id)
    if product is None or not product.is_active:
        await cb.answer("Товар недоступен", show_alert=True)
        return

    if product.delivery_type == DeliveryType.AUTO:
        available = await count_available_stock(session, product.id)
        if available <= 0:
            await cb.answer("К сожалению, товар закончился", show_alert=True)
            return

    try:
        await bot.send_invoice(
            chat_id=cb.from_user.id,
            title=product.title[:32] or "Товар",
            description=(product.description or product.title)[:255],
            payload=_build_payload(product.id),
            provider_token="",  # Telegram Stars
            currency="XTR",
            prices=[
                LabeledPrice(label=product.title[:32], amount=product.price_stars)
            ],
        )
    except Exception:
        log.exception("Failed to send invoice for product %s", product.id)
        await cb.answer("Не удалось создать счёт. Попробуйте позже.", show_alert=True)
        return

    await cb.answer("Счёт отправлен")


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery, session: AsyncSession) -> None:
    product_id = _parse_payload(query.invoice_payload)
    if product_id is None:
        await query.answer(ok=False, error_message="Неверный счёт")
        return

    product = await get_product(session, product_id)
    if product is None or not product.is_active:
        await query.answer(ok=False, error_message="Товар недоступен")
        return
    if product.price_stars != query.total_amount:
        await query.answer(ok=False, error_message="Цена изменилась, обновите счёт")
        return

    # AUTO stock can vanish between invoice and pre_checkout. We try our best
    # here, but the final authority is on_successful_payment where the row is
    # actually reserved.
    if product.delivery_type == DeliveryType.AUTO:
        available = await count_available_stock(session, product.id)
        if available <= 0:
            await query.answer(ok=False, error_message="Товар закончился")
            return

    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(
    message: Message, session: AsyncSession, bot: Bot, settings: Settings
) -> None:
    payment = message.successful_payment
    user = message.from_user
    if payment is None or user is None:
        return

    product_id = _parse_payload(payment.invoice_payload)
    if product_id is None:
        log.error("Bad invoice payload: %r", payment.invoice_payload)
        return

    product = await get_product(session, product_id)
    if product is None:
        log.error("Paid product %s vanished", product_id)
        return

    await upsert_user(
        session, user_id=user.id, username=user.username, full_name=user.full_name
    )
    order = await create_order(
        session,
        user_id=user.id,
        product_id=product.id,
        price_stars=payment.total_amount,
    )
    order.payment_charge_id = payment.telegram_payment_charge_id

    if product.delivery_type == DeliveryType.AUTO:
        item = await reserve_one(session, product.id, order.id)
        if item is None:
            await mark_awaiting_delivery(
                session, order, payment.telegram_payment_charge_id
            )
            await message.answer(
                "⚠️ Товар закончился прямо перед оплатой. "
                "Администратор свяжется для возврата или ручной выдачи."
            )
            await _notify_admins(
                bot,
                settings,
                f"⚠️ Заказ #{order.id}: товар «{product.title}» закончился, "
                f"оплата прошла. Нужен возврат или ручная выдача.",
            )
            return

        await mark_delivered(session, order, item.content)
        await message.answer(
            "✅ Оплата получена!\n\n"
            f"Ваш товар «{product.title}»:\n"
            f"<code>{item.content}</code>"
        )
        return

    # Manual flow.
    await mark_awaiting_delivery(session, order, payment.telegram_payment_charge_id)
    await message.answer(
        "✅ Оплата получена!\n\n"
        f"Товар «{product.title}» выдаётся вручную. "
        "Администратор пришлёт его сюда в ближайшее время."
    )
    await _notify_admins(
        bot,
        settings,
        f"📨 Новый ручной заказ #{order.id}\n"
        f"Товар: {product.title}\n"
        f"Пользователь: {user.id} (@{user.username or '—'})",
    )


async def _notify_admins(bot: Bot, settings: Settings, text: str) -> None:
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            log.warning("Failed to notify admin %s", admin_id, exc_info=True)
