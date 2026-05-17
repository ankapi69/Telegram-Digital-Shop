from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.admin import admin_menu_kb

router = Router(name="admin-menu")


ADMIN_HEADER = "🛠 <b>Админ-панель</b>\n\nВыберите действие:"


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(ADMIN_HEADER, reply_markup=admin_menu_kb())


@router.callback_query(F.data == "adm:menu")
async def admin_menu(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if cb.message is None:
        await cb.answer()
        return
    await cb.message.edit_text(ADMIN_HEADER, reply_markup=admin_menu_kb())
    await cb.answer()
