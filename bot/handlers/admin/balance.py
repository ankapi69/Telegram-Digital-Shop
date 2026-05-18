from __future__ import annotations

from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.locales import translate
from bot.repositories import wallet as wallet_repo
from bot.repositories.product import coerce_decimal
from bot.repositories.user import find_user
from bot.states.admin import AdminBalanceAdjust, AdminUserSearchForBalance
from bot.utils.money import fmt_amount

router = Router(name="admin-balance")


def _menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔎 Найти по ID/@username", callback_data="adm:bal:find")
    kb.button(text="« Назад", callback_data="adm:menu")
    kb.adjust(1)
    return kb.as_markup()


def _user_kb(user_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Изменить баланс", callback_data=f"adm:bal:edit:{user_id}")
    kb.button(text="« Назад", callback_data="adm:bal")
    kb.adjust(1)
    return kb.as_markup()


@router.callback_query(F.data == "adm:bal")
async def menu(cb: CallbackQuery) -> None:
    if cb.message is None:
        await cb.answer()
        return
    text = "💰 <b>Балансы пользователей</b>\n\nНайдите пользователя по Telegram ID или @username."
    try:
        await cb.message.edit_text(text, reply_markup=_menu_kb())
    except Exception:
        await cb.message.answer(text, reply_markup=_menu_kb())
    await cb.answer()


@router.callback_query(F.data == "adm:bal:find")
async def find_prompt(cb: CallbackQuery, state: FSMContext) -> None:
    if cb.message is None:
        await cb.answer()
        return
    await state.set_state(AdminUserSearchForBalance.query)
    await cb.message.answer("ID или @username:")
    await cb.answer()


@router.message(AdminUserSearchForBalance.query, F.text)
async def find_apply(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    user = await find_user(session, message.text or "")
    await state.clear()
    if user is None:
        await message.answer("Пользователь не найден.")
        return
    balance = await wallet_repo.get_balance(session, user.id)
    await message.answer(
        _user_card(user, balance), reply_markup=_user_kb(user.id)
    )


def _user_card(user, balance) -> str:
    return (
        f"👤 <b>{user.full_name or user.username or user.id}</b>\n"
        f"ID <code>{user.id}</code>  @{user.username or '—'}\n"
        f"Роль: <i>{user.role.value}</i>\n"
        f"Баланс: <b>{fmt_amount(balance, 'USD')}</b>"
    )


@router.callback_query(F.data.startswith("adm:bal:edit:"))
async def edit_start(
    cb: CallbackQuery, state: FSMContext, t=translate
) -> None:
    if cb.data is None or cb.message is None:
        await cb.answer()
        return
    target_id = int(cb.data.rsplit(":", 1)[1])
    await state.set_state(AdminBalanceAdjust.amount)
    await state.update_data(target_id=target_id)
    await cb.message.answer(t("admin_balance_prompt"))
    await cb.answer()


@router.message(AdminBalanceAdjust.amount, F.text)
async def edit_amount(
    message: Message, state: FSMContext, t=translate
) -> None:
    raw = (message.text or "").strip().replace(",", ".")
    try:
        delta = Decimal(raw)
    except (ArithmeticError, ValueError):
        await message.answer(t("admin_balance_invalid"))
        return
    if delta == 0:
        await message.answer(t("admin_balance_invalid"))
        return
    await state.update_data(delta=str(delta))
    await state.set_state(AdminBalanceAdjust.comment)
    await message.answer(t("admin_balance_comment"))


@router.message(AdminBalanceAdjust.comment, F.text)
async def edit_apply(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    t=translate,
) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    target_id = int(data["target_id"])
    delta = Decimal(data["delta"])
    raw_comment = (message.text or "").strip()
    comment = None if raw_comment == "-" else raw_comment[:256]

    entry = await wallet_repo.admin_adjust(
        session,
        target_user_id=target_id,
        delta=delta,
        admin_id=message.from_user.id,
        comment=comment,
    )
    await state.clear()
    if entry is None:
        await message.answer(t("admin_balance_insufficient"))
        return

    new_balance = await wallet_repo.get_balance(session, target_id)
    await message.answer(
        t("admin_balance_done", amount=fmt_amount(new_balance, "USD"))
    )

    # Notify the user about the adjustment.
    try:
        from aiogram import Bot
        bot: Bot = message.bot  # type: ignore[assignment]
        sign = "+" if delta > 0 else "−"
        note = f" — {comment}" if comment else ""
        await bot.send_message(
            target_id,
            f"💰 Администратор изменил ваш баланс: "
            f"{sign}{fmt_amount(abs(delta), 'USD')}{note}\n"
            f"Текущий баланс: <b>{fmt_amount(new_balance, 'USD')}</b>",
        )
    except Exception:
        pass
