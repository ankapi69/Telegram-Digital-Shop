from __future__ import annotations

from decimal import Decimal

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.user import back_to_menu_kb, payment_kb
from bot.locales import translate
from bot.payments.base import PaymentProvider
from bot.payments.registry import PaymentRegistry
from bot.repositories import order as order_repo
from bot.repositories import wallet as wallet_repo
from bot.repositories.product import coerce_decimal
from bot.services.rates import RatesService
from bot.utils.money import fmt_amount

router = Router(name="balance")


class Topup(StatesGroup):
    waiting_amount = State()


MIN_TOPUP = Decimal("0.5")
MAX_TOPUP = Decimal("5000")
PRESET_AMOUNTS = (Decimal("1"), Decimal("5"), Decimal("10"),
                  Decimal("25"), Decimal("50"), Decimal("100"))

# Provider codes that take USD ≈ USDT 1:1.
USD_PROVIDERS = {"cryptobot"}
# Provider codes that invoice in RUB; topup amount is converted via rate.
RUB_PROVIDERS = {"lava"}


# ---- keyboards (local — depend on dynamic rate) -------------------------


def _topup_provider_kb(providers: list[PaymentProvider]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in providers:
        if p.code in USD_PROVIDERS:
            kb.button(text=f"💵 {p.display_name} ($)", callback_data=f"topup:p:{p.code}")
        elif p.code in RUB_PROVIDERS:
            kb.button(text=f"₽ {p.display_name} (RUB)", callback_data=f"topup:p:{p.code}")
    kb.button(text="« Назад", callback_data="balance")
    kb.adjust(1)
    return kb.as_markup()


def _topup_amounts_kb(provider_code: str, rate: Decimal | None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for usd in PRESET_AMOUNTS:
        if rate is not None:
            rub = (usd * rate).quantize(Decimal("0.01"))
            label = f"${int(usd)}  ≈ {rub.normalize():f} ₽"
        else:
            label = f"${int(usd)}"
        kb.button(text=label, callback_data=f"topup:f:{provider_code}:{usd}")
    kb.button(text="✏️ Другая сумма ($)", callback_data=f"topup:c:{provider_code}")
    kb.button(text="« Назад", callback_data="topup:new")
    kb.adjust(1)
    return kb.as_markup()


# ---- screens -------------------------------------------------------------


@router.callback_query(F.data == "balance")
async def show_balance(
    cb: CallbackQuery, session: AsyncSession, t=translate
) -> None:
    if cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    balance = await wallet_repo.get_balance(session, cb.from_user.id)
    entries = await wallet_repo.list_entries(session, cb.from_user.id, limit=5)

    lines = [t("balance_title"), "", t("balance_amount", amount=fmt_amount(balance, "USD"))]
    if entries:
        lines.append("")
        lines.append(t("balance_history_header"))
        for e in entries:
            sign = "+" if e.delta > 0 else "−"
            lines.append(
                f"  {sign} {fmt_amount(abs(e.delta), 'USD')} · "
                f"{e.kind.value}"
                + (f" · {e.comment}" if e.comment else "")
            )
    else:
        lines.append("")
        lines.append(t("balance_history_empty"))

    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Пополнить", callback_data="topup:new")
    kb.button(text="« В меню", callback_data="back_to_menu")
    kb.adjust(1)
    try:
        await cb.message.edit_text("\n".join(lines), reply_markup=kb.as_markup())
    except Exception:
        await cb.message.answer("\n".join(lines), reply_markup=kb.as_markup())
    await cb.answer()


@router.callback_query(F.data == "topup:new")
async def pick_provider(
    cb: CallbackQuery, registry: PaymentRegistry, t=translate
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    providers = [
        p for p in registry.all()
        if p.code in USD_PROVIDERS or p.code in RUB_PROVIDERS
    ]
    if not providers:
        await cb.answer(t("balance_topup_no_provider"), show_alert=True)
        return
    try:
        await cb.message.edit_text(
            "Выберите способ пополнения:",
            reply_markup=_topup_provider_kb(providers),
        )
    except Exception:
        await cb.message.answer(
            "Выберите способ пополнения:",
            reply_markup=_topup_provider_kb(providers),
        )
    await cb.answer()


@router.callback_query(F.data.startswith("topup:p:"))
async def pick_amount(
    cb: CallbackQuery,
    registry: PaymentRegistry,
    rates: RatesService,
    t=translate,
) -> None:
    if cb.data is None or cb.message is None:
        await cb.answer()
        return
    code = cb.data.rsplit(":", 1)[1]
    if registry.get(code) is None:
        await cb.answer()
        return
    rate = None
    if code in RUB_PROVIDERS:
        rate = (await rates.get()).rate
    header = "Введите сумму пополнения в долларах:"
    if rate is not None:
        header = (
            f"Курс: <b>{rate.normalize():f} ₽ / $</b>\n\n"
            "Выберите или введите сумму в долларах:"
        )
    try:
        await cb.message.edit_text(header, reply_markup=_topup_amounts_kb(code, rate))
    except Exception:
        await cb.message.answer(header, reply_markup=_topup_amounts_kb(code, rate))
    await cb.answer()


@router.callback_query(F.data.startswith("topup:f:"))
async def fixed_amount(
    cb: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
    registry: PaymentRegistry,
    rates: RatesService,
    t=translate,
) -> None:
    if cb.data is None or cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    parts = cb.data.split(":")
    if len(parts) != 4:
        await cb.answer()
        return
    code = parts[2]
    try:
        usd = Decimal(parts[3])
    except (ArithmeticError, ValueError):
        await cb.answer()
        return
    await _create_topup_invoice(
        cb.message, cb.from_user, session, bot, registry, rates, code, usd, t
    )
    await cb.answer()


@router.callback_query(F.data.startswith("topup:c:"))
async def custom_amount_prompt(
    cb: CallbackQuery, state: FSMContext, t=translate
) -> None:
    if cb.data is None or cb.message is None:
        await cb.answer()
        return
    code = cb.data.rsplit(":", 1)[1]
    await state.set_state(Topup.waiting_amount)
    await state.update_data(provider_code=code)
    await cb.message.answer(t("balance_topup_prompt"))
    await cb.answer()


@router.message(Topup.waiting_amount, F.text)
async def custom_amount_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    registry: PaymentRegistry,
    rates: RatesService,
    t=translate,
) -> None:
    if message.from_user is None:
        return
    usd = coerce_decimal(message.text or "")
    if usd is None or usd < MIN_TOPUP or usd > MAX_TOPUP:
        await message.answer(t("balance_topup_invalid"))
        return
    data = await state.get_data()
    code = str(data.get("provider_code", ""))
    await state.clear()
    await _create_topup_invoice(
        message, message.from_user, session, bot, registry, rates, code, usd, t
    )


# ---- invoice creation ---------------------------------------------------


async def _create_topup_invoice(
    target,
    tg_user,
    session: AsyncSession,
    bot: Bot,
    registry: PaymentRegistry,
    rates: RatesService,
    provider_code: str,
    usd: Decimal,
    t,
) -> None:
    provider = registry.get(provider_code)
    if provider is None:
        await target.answer(t("balance_topup_no_provider"), reply_markup=back_to_menu_kb())
        return

    # Resolve the invoice amount in provider's currency.
    if provider_code in RUB_PROVIDERS:
        rate = (await rates.get()).rate
        invoice_amount = (usd * rate).quantize(Decimal("0.01"))
    else:
        invoice_amount = usd

    order = await order_repo.create_topup_order(
        session,
        user_id=tg_user.id,
        provider=provider.code,
        currency=provider.currency,
        amount=invoice_amount,
    )
    order.credited_amount = usd  # what the wallet receives after payment

    try:
        invoice = await provider.create_invoice(
            bot=bot, order=order, product=None, user=tg_user
        )
    except Exception:
        logger.exception("topup invoice failed (provider={})", provider.code)
        raise

    await order_repo.set_invoice_data(session, order, invoice.external_id, invoice.payment_url)

    summary = (
        f"🧾 Счёт на пополнение #{order.id}\n\n"
        f"Сумма к зачислению: <b>{fmt_amount(usd, 'USD')}</b>\n"
        f"К оплате: <b>{fmt_amount(invoice_amount, provider.currency)}</b>\n"
        f"Способ: {provider.display_name}\n\n"
        "Откройте ссылку, оплатите, затем нажмите «Проверить оплату»."
    )
    await target.answer(
        summary,
        reply_markup=payment_kb(
            order_id=order.id,
            payment_url=invoice.payment_url,
            show_check=provider.supports_manual_check,
        ),
    )
