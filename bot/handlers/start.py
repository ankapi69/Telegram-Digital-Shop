from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.user import main_menu_kb
from bot.repositories.user import upsert_user

router = Router(name="start")


WELCOME = (
    "👋 Добро пожаловать в магазин!\n\n"
    "Здесь продаются цифровые товары: ссылки активации и аккаунты.\n"
    "Выберите действие в меню ниже."
)


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    user = message.from_user
    if user is None:
        return
    await upsert_user(
        session,
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
    )
    await message.answer(WELCOME, reply_markup=main_menu_kb())


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(cb: CallbackQuery) -> None:
    if cb.message is None:
        await cb.answer()
        return
    await cb.message.edit_text(WELCOME, reply_markup=main_menu_kb())
    await cb.answer()
