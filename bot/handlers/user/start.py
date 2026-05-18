from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.user import main_menu_kb
from bot.locales import translate
from bot.repositories import wallet as wallet_repo
from bot.services.cart import CartService

router = Router(name="start")


async def _cart_count(cart: CartService, user_id: int) -> int:
    lines = await cart.get(user_id)
    return sum(line.quantity for line in lines)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    cart: CartService,
    state: FSMContext,
    session: AsyncSession,
    t=translate,
) -> None:
    await state.clear()
    if message.from_user is None:
        return
    count = await _cart_count(cart, message.from_user.id)
    balance = await wallet_repo.get_balance(session, message.from_user.id)
    await message.answer(t("menu_title"), reply_markup=main_menu_kb(count, balance))


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(
    cb: CallbackQuery,
    cart: CartService,
    state: FSMContext,
    session: AsyncSession,
    t=translate,
) -> None:
    await state.clear()
    if cb.message is None or cb.from_user is None:
        await cb.answer()
        return
    count = await _cart_count(cart, cb.from_user.id)
    balance = await wallet_repo.get_balance(session, cb.from_user.id)
    markup = main_menu_kb(count, balance)
    try:
        await cb.message.edit_text(t("menu_title"), reply_markup=markup)
    except Exception:
        await cb.message.answer(t("menu_title"), reply_markup=markup)
    await cb.answer()
