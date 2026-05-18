from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.admin import user_card_kb, users_list_kb
from bot.repositories.user import find_user, list_recent_users, set_banned
from bot.states.admin import UserSearch

router = Router(name="admin-users")


def _card(user) -> str:
    return (
        f"👤 <b>{user.full_name or user.username or user.id}</b>\n"
        f"ID <code>{user.id}</code> @ {user.username or '—'}\n"
        f"Роль: <i>{user.role.value}</i>\n"
        f"Статус: {'🚫 заблокирован' if user.is_banned else '✅ активен'}\n"
        f"Последняя активность: {user.last_seen_at or '—'}"
    )


@router.callback_query(F.data == "adm:users")
async def list_users(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.message is None:
        await cb.answer()
        return
    users = await list_recent_users(session, limit=20)
    try:
        await cb.message.edit_text(
            "👤 <b>Пользователи (последние 20)</b>",
            reply_markup=users_list_kb(users),
        )
    except Exception:
        await cb.message.answer(
            "👤 <b>Пользователи (последние 20)</b>",
            reply_markup=users_list_kb(users),
        )
    await cb.answer()


@router.callback_query(F.data == "adm:u:find")
async def find_start(cb: CallbackQuery, state: FSMContext) -> None:
    if cb.message is None:
        await cb.answer()
        return
    await state.set_state(UserSearch.query)
    await cb.message.edit_text("ID или @username:")
    await cb.answer()


@router.message(UserSearch.query, F.text)
async def find_apply(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    user = await find_user(session, message.text or "")
    await state.clear()
    if user is None:
        await message.answer("Не найден.")
        return
    await message.answer(_card(user), reply_markup=user_card_kb(user))


@router.callback_query(F.data.regexp(r"^adm:u:\d+$"))
async def view_user(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.data is None or cb.message is None:
        await cb.answer()
        return
    uid = int(cb.data.rsplit(":", 1)[1])
    user = await find_user(session, str(uid))
    if user is None:
        await cb.answer()
        return
    try:
        await cb.message.edit_text(_card(user), reply_markup=user_card_kb(user))
    except Exception:
        await cb.message.answer(_card(user), reply_markup=user_card_kb(user))
    await cb.answer()


@router.callback_query(F.data.startswith("adm:u:ban:"))
async def ban_user(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.data is None or cb.message is None:
        await cb.answer()
        return
    uid = int(cb.data.rsplit(":", 1)[1])
    user = await set_banned(session, uid, True)
    if user is None:
        await cb.answer()
        return
    try:
        await cb.message.edit_text(_card(user), reply_markup=user_card_kb(user))
    except Exception:
        pass
    await cb.answer("Заблокирован")


@router.callback_query(F.data.startswith("adm:u:unban:"))
async def unban_user(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.data is None or cb.message is None:
        await cb.answer()
        return
    uid = int(cb.data.rsplit(":", 1)[1])
    user = await set_banned(session, uid, False)
    if user is None:
        await cb.answer()
        return
    try:
        await cb.message.edit_text(_card(user), reply_markup=user_card_kb(user))
    except Exception:
        pass
    await cb.answer("Разблокирован")
