from __future__ import annotations

import json

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User
from bot.keyboards.admin import broadcast_confirm_kb
from bot.services.broadcast import Broadcaster
from bot.states.admin import Broadcast

router = Router(name="admin-broadcast")


@router.callback_query(F.data == "adm:bcast")
async def start(cb: CallbackQuery, state: FSMContext) -> None:
    if cb.message is None:
        await cb.answer()
        return
    await state.set_state(Broadcast.waiting_text)
    await cb.message.edit_text(
        "Введите текст рассылки (HTML поддерживается):"
    )
    await cb.answer()


@router.message(Broadcast.waiting_text, F.text)
async def got_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text or len(text) > 3500:
        await message.answer("1..3500.")
        return
    await state.update_data(text=text)
    await state.set_state(Broadcast.waiting_photo)
    await message.answer("Прикрепите фото или отправьте «-» чтобы пропустить:")


@router.message(Broadcast.waiting_photo, F.photo)
async def got_photo(message: Message, state: FSMContext) -> None:
    if not message.photo:
        return
    await state.update_data(photo_file_id=message.photo[-1].file_id)
    await state.set_state(Broadcast.waiting_button)
    await message.answer(
        'Кнопка под сообщением в формате <code>Текст|https://url</code> или «-»:'
    )


@router.message(Broadcast.waiting_photo, F.text)
async def skip_photo(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw != "-":
        await message.answer("Пришлите фото или «-».")
        return
    await state.update_data(photo_file_id=None)
    await state.set_state(Broadcast.waiting_button)
    await message.answer(
        'Кнопка под сообщением в формате <code>Текст|https://url</code> или «-»:'
    )


@router.message(Broadcast.waiting_button, F.text)
async def got_button(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    button: tuple[str, str] | None = None
    if raw != "-":
        if "|" not in raw:
            await message.answer("Формат: Текст|URL")
            return
        text, url = raw.split("|", 1)
        text = text.strip()
        url = url.strip()
        if not text or not url.startswith(("http://", "https://", "tg://")):
            await message.answer("URL должен начинаться с http(s):// или tg://")
            return
        button = (text, url)
    await state.update_data(button=button)
    data = await state.get_data()
    preview = data["text"]
    if button:
        preview += f"\n\n[кнопка] {button[0]} → {button[1]}"
    if data.get("photo_file_id"):
        preview = "[фото]\n" + preview
    await state.set_state(Broadcast.confirm)
    await message.answer(
        "Превью:\n\n" + preview, reply_markup=broadcast_confirm_kb()
    )


@router.callback_query(Broadcast.confirm, F.data == "adm:bcast:go")
async def go(
    cb: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    broadcaster: Broadcaster,
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    data = await state.get_data()
    await state.clear()
    text = data["text"]
    photo = data.get("photo_file_id")
    button = data.get("button")
    markup: InlineKeyboardMarkup | None = None
    if button:
        markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=button[0], url=button[1])]]
        )

    stmt = select(User.id).where(User.is_banned.is_(False))
    user_ids = list((await session.execute(stmt)).scalars().all())
    await cb.message.edit_text(f"🚀 Старт ({len(user_ids)} получателей)…")
    result = await broadcaster.broadcast_text(
        user_ids, text, photo_file_id=photo, reply_markup=markup
    )
    await cb.message.answer(
        f"✅ Готово. Отправлено: {result.sent}, ошибок: {result.failed}"
    )
    await cb.answer()
