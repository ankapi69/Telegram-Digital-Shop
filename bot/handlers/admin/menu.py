from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database.models import UserRole
from bot.keyboards.admin import admin_menu_kb
from bot.locales import translate

router = Router(name="admin-menu")


@router.message(Command("admin"))
async def cmd_admin(
    message: Message, state: FSMContext, role: UserRole, t=translate
) -> None:
    await state.clear()
    await message.answer(t("admin_menu"), reply_markup=admin_menu_kb(role))


@router.callback_query(F.data == "adm:menu")
async def admin_menu(
    cb: CallbackQuery, state: FSMContext, role: UserRole, t=translate
) -> None:
    await state.clear()
    if cb.message is None:
        await cb.answer()
        return
    try:
        await cb.message.edit_text(t("admin_menu"), reply_markup=admin_menu_kb(role))
    except Exception:
        await cb.message.answer(t("admin_menu"), reply_markup=admin_menu_kb(role))
    await cb.answer()
