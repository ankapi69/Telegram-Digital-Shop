from __future__ import annotations

import logging
from decimal import Decimal

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import DeliveryType, OrderStatus
from bot.keyboards.user import payment_kb, provider_pick_kb
from bot.locales import translate
from bot.payments.base import PaymentStatus
from bot.payments.fulfillment import fulfill_paid_order
from bot.payments.registry import PaymentRegistry
from bot.payments.stars import decode_payload
from bot.repositories import order as order_repo
from bot.repositories import product as product_repo
from bot.repositories import wallet as wallet_repo
from bot.services.cart import CartService
from bot.services.checkout import CheckoutError, build_quote, materialize_order
from bot.services.notifier import Notifier
from bot.services.wallet import InsufficientFunds, pay_with_balance
from bot.utils.money import fmt_amount

router = Router(name="checkout")


# ---- "Купить сейчас" одним кликом ---------------------------------------


@router.callback_query(F.data.startswith("quickbuy:"))
async def quick_buy(
    cb: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
    registry: PaymentRegistry,
    t=translate,
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

    provider = registry.get(provider_code)
    product = await product_repo.get_product(session, product_id)
    if provider is None or product is None or not product.is_active:
        await cb.answer(t("invoice_provider_off"), show_alert=True)
        return
    if provider.price_for(product) is None:
        await cb.answer(t("no_providers"), show_alert=True)
        return

    from bot.services.cart import CartLine

    try:
        quote = await build_quote(
            session,
            provider=provider,
            cart_lines=[CartLine(product_id=product.id, quantity=1)],
            promo_code=None,
        )
    except CheckoutError as e:
        await cb.answer(str(e), show_alert=True)
        return

    await _create_invoice_and_send(cb, bot, session, quote, cb.from_user, t)
    await cb.answer()


# ---- Корзино-based чекаут -----------------------------------------------


@router.callback_query(F.data.startswith("checkout:"))
async def checkout(
    cb: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
    cart: CartService,
    registry: PaymentRegistry,
    t=translate,
) -> None:
    if cb.data is None or cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    currency = cb.data.split(":", 1)[1]
    providers = [p for p in registry.all() if p.currency == currency]
    if not providers:
        await cb.answer(t("invoice_provider_off"), show_alert=True)
        return
    # If one provider for the currency — proceed directly, else ask.
    if len(providers) == 1:
        await _proceed_with_provider(cb, session, bot, cart, registry, providers[0].code, t)
        return
    await cb.message.edit_text(t("cart_pick_provider"), reply_markup=provider_pick_kb(providers))
    # Stash chosen currency in callback flow via FSM? Use callback `pay:<code>` next.
    await cb.answer()


@router.callback_query(F.data.startswith("pay:"))
async def chosen_provider(
    cb: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
    cart: CartService,
    registry: PaymentRegistry,
    t=translate,
) -> None:
    if cb.data is None or cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    provider_code = cb.data.split(":", 1)[1]
    await _proceed_with_provider(cb, session, bot, cart, registry, provider_code, t)


async def _proceed_with_provider(
    cb: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
    cart: CartService,
    registry: PaymentRegistry,
    provider_code: str,
    t,
) -> None:
    provider = registry.get(provider_code)
    if provider is None or cb.from_user is None:
        await cb.answer(t("invoice_provider_off"), show_alert=True)
        return
    lines = await cart.get(cb.from_user.id)
    if not lines:
        await cb.answer(t("cart_empty"), show_alert=True)
        return
    promo_code = await cart.get_promo(cb.from_user.id)
    try:
        quote = await build_quote(
            session, provider=provider, cart_lines=lines, promo_code=promo_code
        )
    except CheckoutError as e:
        await cb.answer(str(e), show_alert=True)
        return

    user = cb.from_user
    order = await _create_invoice_and_send(cb, bot, session, quote, user, t)
    if order is not None:
        await cart.clear(user.id)


async def _create_invoice_and_send(
    cb: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    quote,
    tg_user,
    t,
):
    order = await materialize_order(session, user_id=tg_user.id, quote=quote)
    try:
        invoice = await quote.provider.create_invoice(
            bot=bot, order=order, product=None, user=tg_user
        )
    except Exception:
        logger.exception("create_invoice failed (provider={})", quote.provider.code)
        # Bubble up so middleware rolls back the unused order.
        raise

    await order_repo.set_invoice_data(session, order, invoice.external_id, invoice.payment_url)

    if invoice.sent_inline:
        await cb.message.answer(t("paid_inline_sent"))
        return order

    items_text = "\n".join(
        f"• {p.title} ×{qty}" for (p, qty, _price) in quote.lines
    )
    discount_line = (
        t("discount_line", discount=fmt_amount(quote.discount, quote.provider.currency))
        if quote.discount > 0 else ""
    )
    text = t(
        "checkout_invoice",
        order_id=order.id,
        items=items_text,
        total=fmt_amount(quote.total, quote.provider.currency),
        discount_line=discount_line,
        provider=quote.provider.display_name,
    )
    await cb.message.answer(
        text,
        reply_markup=payment_kb(
            order_id=order.id,
            payment_url=invoice.payment_url,
            show_check=quote.provider.supports_manual_check,
        ),
    )
    return order


# ---- Pay from wallet -----------------------------------------------------


@router.callback_query(F.data == "paybal")
async def pay_from_balance(
    cb: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
    cart: CartService,
    registry: PaymentRegistry,
    notifier: Notifier,
    t=translate,
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    balance_provider = registry.get("balance")
    if balance_provider is None:
        await cb.answer(t("invoice_provider_off"), show_alert=True)
        return
    lines = await cart.get(cb.from_user.id)
    if not lines:
        await cb.answer(t("cart_empty"), show_alert=True)
        return
    promo_code = await cart.get_promo(cb.from_user.id)
    try:
        quote = await build_quote(
            session, provider=balance_provider,
            cart_lines=lines, promo_code=promo_code,
        )
    except CheckoutError as e:
        await cb.answer(str(e), show_alert=True)
        return

    try:
        result = await pay_with_balance(session, user_id=cb.from_user.id, quote=quote)
    except InsufficientFunds:
        await cb.answer(t("balance_insufficient"), show_alert=True)
        return
    except CheckoutError as e:
        await cb.answer(str(e), show_alert=True)
        return

    await fulfill_paid_order(session, bot, notifier, result.order.id)
    await cart.clear(cb.from_user.id)

    await cb.message.answer(
        t("balance_paid", amount=fmt_amount(result.new_balance, "USD"))
    )
    await cb.answer()


# ---- Manual check ---------------------------------------------------------


@router.callback_query(F.data.startswith("check:"))
async def manual_check(
    cb: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
    registry: PaymentRegistry,
    notifier: Notifier,
    t=translate,
) -> None:
    if cb.data is None or cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    order_id = int(cb.data.split(":", 1)[1])
    order = await order_repo.get_order(session, order_id)
    if order is None or order.user_id != cb.from_user.id:
        await cb.answer("Заказ не найден", show_alert=True)
        return
    if order.status == OrderStatus.DELIVERED:
        await cb.answer(t("paid_already"), show_alert=True)
        return
    if order.status == OrderStatus.AWAITING_DELIVERY:
        await cb.answer(t("paid_awaiting"), show_alert=True)
        return
    if order.status != OrderStatus.PENDING_PAYMENT:
        await cb.answer(f"Статус: {order.status.value}", show_alert=True)
        return
    provider = registry.get(order.provider)
    if provider is None or not provider.supports_manual_check:
        await cb.answer(t("invoice_provider_off"), show_alert=True)
        return
    try:
        status = await provider.verify(order)
    except Exception:
        logger.exception("verify failed for order {}", order.id)
        await cb.answer("Не удалось связаться с провайдером", show_alert=True)
        return

    if status == PaymentStatus.PAID:
        result = await fulfill_paid_order(session, bot, notifier, order.id)
        if result.delivered:
            await cb.answer(t("paid_already"))
        elif result.awaiting:
            await cb.answer(t("paid_awaiting"), show_alert=True)
        else:
            await cb.answer()
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return
    if status in (PaymentStatus.EXPIRED, PaymentStatus.CANCELLED, PaymentStatus.FAILED):
        order.status = OrderStatus.CANCELLED
        await cb.answer(t("paid_expired", status=status.value), show_alert=True)
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return
    await cb.answer(t("paid_not_yet"), show_alert=True)


@router.callback_query(F.data.startswith("cancel:"))
async def cancel_invoice(
    cb: CallbackQuery, session: AsyncSession, t=translate
) -> None:
    if cb.data is None or cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    order_id = int(cb.data.split(":", 1)[1])
    order = await order_repo.get_order(session, order_id)
    if order is None or order.user_id != cb.from_user.id:
        await cb.answer("Не найден", show_alert=True)
        return
    if order.status == OrderStatus.PENDING_PAYMENT:
        order.status = OrderStatus.CANCELLED
        await cb.answer(t("invoice_cancelled"))
    else:
        await cb.answer(order.status.value, show_alert=True)
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


# ---- Stars: pre_checkout + successful_payment ---------------------------


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, session: AsyncSession) -> None:
    order_id = decode_payload(query.invoice_payload)
    if order_id is None:
        await query.answer(ok=False, error_message="Неверный счёт")
        return
    order = await order_repo.get_order(session, order_id)
    if order is None or order.user_id != query.from_user.id:
        await query.answer(ok=False, error_message="Заказ не найден")
        return
    if order.provider != "stars":
        await query.answer(ok=False, error_message="Не Stars-счёт")
        return
    if int(order.total_amount) != query.total_amount:
        await query.answer(ok=False, error_message="Сумма изменилась")
        return
    # Verify per-item stock availability for AUTO items at the last moment.
    for item in order.items:
        product = await product_repo.get_product(session, item.product_id)
        if product is None or not product.is_active:
            await query.answer(ok=False, error_message="Товар недоступен")
            return
        if product.delivery_type == DeliveryType.AUTO:
            available = await product_repo.count_available_stock(session, product.id)
            if available < item.quantity:
                await query.answer(ok=False, error_message="Товар закончился")
                return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(
    message: Message,
    session: AsyncSession,
    bot: Bot,
    notifier: Notifier,
) -> None:
    payment = message.successful_payment
    user = message.from_user
    if payment is None or user is None:
        return
    order_id = decode_payload(payment.invoice_payload)
    if order_id is None:
        return
    order = await order_repo.get_order(session, order_id)
    if order is None:
        return
    order.external_id = payment.telegram_payment_charge_id
    await fulfill_paid_order(session, bot, notifier, order.id)
