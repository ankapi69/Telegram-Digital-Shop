from __future__ import annotations

from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.user import cart_kb
from bot.locales import translate
from bot.payments.registry import PaymentRegistry
from bot.repositories import product as product_repo
from bot.services.cart import CartLine, CartService
from bot.services.promo import apply_promo
from bot.states.admin import CartPromo
from bot.utils.money import fmt_amount

router = Router(name="cart")


async def _render_cart(
    cb: CallbackQuery | Message,
    cart: CartService,
    session: AsyncSession,
    registry: PaymentRegistry,
    user_id: int,
    t,
) -> None:
    lines: list[CartLine] = await cart.get(user_id)
    target = cb.message if isinstance(cb, CallbackQuery) else cb
    if not lines:
        if isinstance(cb, CallbackQuery):
            await target.edit_text(t("cart_empty"), reply_markup=cart_kb([], False, False, []))
        else:
            await target.answer(t("cart_empty"), reply_markup=cart_kb([], False, False, []))
        return

    products = []
    for line in lines:
        product = await product_repo.get_product(session, line.product_id)
        if product is None:
            await cart.remove(user_id, line.product_id)
            continue
        products.append((product, line.quantity))

    if not products:
        await target.edit_text(t("cart_empty"), reply_markup=cart_kb([], False, False, []))
        return

    # Compute subtotal in each currency that ALL products support.
    currency_totals: dict[str, Decimal] = {}
    for provider in registry.all():
        cur = provider.currency
        if cur in currency_totals:
            continue
        total = Decimal(0)
        ok = True
        for product, qty in products:
            price = provider.price_for(product)
            if price is None:
                ok = False
                break
            total += Decimal(price) * qty
        if ok:
            currency_totals[cur] = total

    promo_code = await cart.get_promo(user_id)

    text_lines = [t("cart_title"), ""]
    for product, qty in products:
        text_lines.append(f"• <b>{product.title}</b> ×{qty}")
    text_lines.append("")
    for cur, subtotal in currency_totals.items():
        promo_app = await apply_promo(session, promo_code, subtotal, cur)
        if promo_app:
            text_lines.append(
                t("cart_total", amount=fmt_amount(promo_app.total_after, cur))
                + f" "
                + t(
                    "cart_promo_active",
                    code=promo_code,
                    discount=fmt_amount(promo_app.discount, cur),
                )
            )
        else:
            text_lines.append(t("cart_total", amount=fmt_amount(subtotal, cur)))

    if not currency_totals:
        text_lines.append(t("no_providers"))

    markup = cart_kb(
        products,
        has_promo=bool(promo_code),
        can_checkout=bool(currency_totals),
        currencies=list(currency_totals.keys()),
    )
    text = "\n".join(text_lines)
    if isinstance(cb, CallbackQuery):
        try:
            await target.edit_text(text, reply_markup=markup)
        except Exception:
            await target.answer(text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.callback_query(F.data == "cart")
async def show_cart(
    cb: CallbackQuery,
    cart: CartService,
    session: AsyncSession,
    registry: PaymentRegistry,
    t=translate,
) -> None:
    if cb.from_user is None:
        await cb.answer()
        return
    await _render_cart(cb, cart, session, registry, cb.from_user.id, t)
    await cb.answer()


@router.callback_query(F.data.startswith("cart:add:"))
async def add_to_cart(
    cb: CallbackQuery,
    cart: CartService,
    session: AsyncSession,
    t=translate,
) -> None:
    if cb.data is None or cb.from_user is None:
        await cb.answer()
        return
    product_id = int(cb.data.rsplit(":", 1)[1])
    product = await product_repo.get_product(session, product_id)
    if product is None or not product.is_active:
        await cb.answer(t("out_of_stock"), show_alert=True)
        return
    try:
        await cart.add(cb.from_user.id, product_id, +1)
    except ValueError:
        await cb.answer("Лимит позиций", show_alert=True)
        return
    await cb.answer(t("cart_added"))


@router.callback_query(F.data.startswith("cart:inc:"))
async def inc(cb: CallbackQuery, cart: CartService, session: AsyncSession,
              registry: PaymentRegistry, t=translate) -> None:
    if cb.data is None or cb.from_user is None:
        await cb.answer()
        return
    pid = int(cb.data.rsplit(":", 1)[1])
    try:
        await cart.add(cb.from_user.id, pid, +1)
    except ValueError:
        await cb.answer("Лимит", show_alert=True)
        return
    await _render_cart(cb, cart, session, registry, cb.from_user.id, t)
    await cb.answer()


@router.callback_query(F.data.startswith("cart:dec:"))
async def dec(cb: CallbackQuery, cart: CartService, session: AsyncSession,
              registry: PaymentRegistry, t=translate) -> None:
    if cb.data is None or cb.from_user is None:
        await cb.answer()
        return
    pid = int(cb.data.rsplit(":", 1)[1])
    await cart.add(cb.from_user.id, pid, -1)
    await _render_cart(cb, cart, session, registry, cb.from_user.id, t)
    await cb.answer()


@router.callback_query(F.data.startswith("cart:rm:"))
async def rm(cb: CallbackQuery, cart: CartService, session: AsyncSession,
             registry: PaymentRegistry, t=translate) -> None:
    if cb.data is None or cb.from_user is None:
        await cb.answer()
        return
    pid = int(cb.data.rsplit(":", 1)[1])
    await cart.remove(cb.from_user.id, pid)
    await _render_cart(cb, cart, session, registry, cb.from_user.id, t)
    await cb.answer(t("cart_removed"))


@router.callback_query(F.data == "cart:clear")
async def clear(cb: CallbackQuery, cart: CartService, session: AsyncSession,
                registry: PaymentRegistry, t=translate) -> None:
    if cb.from_user is None:
        await cb.answer()
        return
    await cart.clear(cb.from_user.id)
    await _render_cart(cb, cart, session, registry, cb.from_user.id, t)
    await cb.answer(t("cart_cleared"))


@router.callback_query(F.data == "cart:nop")
async def nop(cb: CallbackQuery) -> None:
    await cb.answer()


@router.callback_query(F.data == "cart:promo")
async def promo_toggle(
    cb: CallbackQuery,
    cart: CartService,
    state: FSMContext,
    session: AsyncSession,
    registry: PaymentRegistry,
    t=translate,
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    if await cart.get_promo(cb.from_user.id):
        await cart.set_promo(cb.from_user.id, None)
        await _render_cart(cb, cart, session, registry, cb.from_user.id, t)
        await cb.answer("Промо снято")
        return
    await state.set_state(CartPromo.waiting_code)
    await cb.message.answer(t("cart_promo_prompt"))
    await cb.answer()


@router.message(CartPromo.waiting_code, F.text)
async def promo_input(
    message: Message,
    state: FSMContext,
    cart: CartService,
    session: AsyncSession,
    registry: PaymentRegistry,
    t=translate,
) -> None:
    if message.from_user is None:
        return
    raw = (message.text or "").strip().upper()
    if raw == "/CANCEL":
        await state.clear()
        await _render_cart(message, cart, session, registry, message.from_user.id, t)
        return
    # Validate against any currency present in cart.
    lines = await cart.get(message.from_user.id)
    valid = False
    for provider in registry.all():
        # Cheap sanity check by trying to apply against a tiny amount.
        from bot.services.promo import apply_promo
        promo = await apply_promo(session, raw, Decimal("1000"), provider.currency)
        if promo:
            valid = True
            break
    if not valid:
        await message.answer(t("cart_promo_invalid"))
        return
    await cart.set_promo(message.from_user.id, raw)
    await state.clear()
    await message.answer(t("cart_promo_applied"))
    await _render_cart(message, cart, session, registry, message.from_user.id, t)
