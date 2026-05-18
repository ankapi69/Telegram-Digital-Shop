from __future__ import annotations

from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import PromoType
from bot.keyboards.admin import promo_kb, promos_list_kb
from bot.repositories import promo as promo_repo
from bot.repositories.product import coerce_decimal
from bot.states.admin import PromoCreate

router = Router(name="admin-promo")


def _card(promo) -> str:
    val = (
        f"{promo.value.normalize():f}%"
        if promo.discount_type == PromoType.PERCENT
        else f"{promo.value.normalize():f} {promo.currency or 'любая валюта'}"
    )
    return (
        f"🏷 <b>{promo.code}</b>\n"
        f"Скидка: {val}\n"
        f"Использований: {promo.used_count}"
        + (f" / {promo.max_uses}" if promo.max_uses else "")
        + f"\nАктивен: {'да' if promo.is_active else 'нет'}"
    )


@router.callback_query(F.data == "adm:promo:list")
async def list_promos(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.message is None:
        await cb.answer()
        return
    promos = await promo_repo.list_all(session)
    try:
        await cb.message.edit_text(
            "🏷 <b>Промокоды</b>", reply_markup=promos_list_kb(promos)
        )
    except Exception:
        await cb.message.answer(
            "🏷 <b>Промокоды</b>", reply_markup=promos_list_kb(promos)
        )
    await cb.answer()


@router.callback_query(F.data == "adm:promo:new")
async def new_promo(cb: CallbackQuery, state: FSMContext) -> None:
    if cb.message is None:
        await cb.answer()
        return
    await state.set_state(PromoCreate.code)
    await cb.message.edit_text("Код промокода (буквы/цифры):")
    await cb.answer()


@router.message(PromoCreate.code, F.text)
async def set_code(message: Message, state: FSMContext) -> None:
    code = (message.text or "").strip().upper()
    if not code or len(code) > 64 or not code.replace("-", "").replace("_", "").isalnum():
        await message.answer("Только буквы/цифры/-/_ , до 64.")
        return
    await state.update_data(code=code)
    await state.set_state(PromoCreate.discount_type)
    kb = InlineKeyboardBuilder()
    kb.button(text="Процент", callback_data="adm:ptype:percent")
    kb.button(text="Фикс", callback_data="adm:ptype:fixed")
    kb.adjust(1)
    await message.answer("Тип скидки:", reply_markup=kb.as_markup())


@router.callback_query(PromoCreate.discount_type, F.data.startswith("adm:ptype:"))
async def set_type(cb: CallbackQuery, state: FSMContext) -> None:
    if cb.data is None or cb.message is None:
        await cb.answer()
        return
    raw = cb.data.rsplit(":", 1)[1]
    try:
        dtype = PromoType(raw)
    except ValueError:
        await cb.answer()
        return
    await state.update_data(discount_type=dtype.value)
    await state.set_state(PromoCreate.value)
    prompt = "Размер скидки (1..100):" if dtype == PromoType.PERCENT else (
        "Размер скидки (число):"
    )
    await cb.message.edit_text(prompt)
    await cb.answer()


@router.message(PromoCreate.value, F.text)
async def set_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    dtype = PromoType(data["discount_type"])
    v = coerce_decimal(message.text or "")
    if v is None:
        await message.answer("Нужно положительное число.")
        return
    if dtype == PromoType.PERCENT and v > Decimal(100):
        await message.answer("Макс 100%.")
        return
    await state.update_data(value=str(v))
    if dtype == PromoType.PERCENT:
        await state.set_state(PromoCreate.max_uses)
        await message.answer("Лимит использований (число или «-»):")
        return
    await state.set_state(PromoCreate.currency)
    await message.answer("Валюта (XTR / RUB / USDT, «-» для любой):")


@router.message(PromoCreate.currency, F.text)
async def set_currency(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().upper()
    cur: str | None = None if raw == "-" else raw
    if cur is not None and cur not in {"XTR", "RUB", "USDT"}:
        await message.answer("XTR / RUB / USDT / «-».")
        return
    await state.update_data(currency=cur)
    await state.set_state(PromoCreate.max_uses)
    await message.answer("Лимит использований (число или «-»):")


@router.message(PromoCreate.max_uses, F.text)
async def set_max(message: Message, state: FSMContext, session: AsyncSession) -> None:
    raw = (message.text or "").strip()
    max_uses: int | None
    if raw == "-":
        max_uses = None
    elif raw.isdigit() and int(raw) > 0:
        max_uses = int(raw)
    else:
        await message.answer("Число или «-».")
        return
    data = await state.get_data()
    promo = await promo_repo.create_promo(
        session,
        code=data["code"],
        discount_type=PromoType(data["discount_type"]),
        value=Decimal(data["value"]),
        currency=data.get("currency"),
        max_uses=max_uses,
    )
    await state.clear()
    await message.answer("✅ Создан\n\n" + _card(promo), reply_markup=promo_kb(promo))


@router.callback_query(F.data.startswith("adm:promo:tog:"))
async def toggle(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.data is None or cb.message is None:
        await cb.answer()
        return
    pid = int(cb.data.rsplit(":", 1)[1])
    promo = await session.get(__import__("bot.database.models", fromlist=["Promo"]).Promo, pid)
    if promo is None:
        await cb.answer()
        return
    promo.is_active = not promo.is_active
    try:
        await cb.message.edit_text(_card(promo), reply_markup=promo_kb(promo))
    except Exception:
        pass
    await cb.answer()


@router.callback_query(F.data.startswith("adm:promo:del:"))
async def delete(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.data is None or cb.message is None:
        await cb.answer()
        return
    pid = int(cb.data.rsplit(":", 1)[1])
    await promo_repo.delete_promo(session, pid)
    promos = await promo_repo.list_all(session)
    try:
        await cb.message.edit_text(
            "🏷 <b>Промокоды</b>", reply_markup=promos_list_kb(promos)
        )
    except Exception:
        pass
    await cb.answer("Удалён")


@router.callback_query(F.data.regexp(r"^adm:promo:\d+$"))
async def view(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.data is None or cb.message is None:
        await cb.answer()
        return
    pid = int(cb.data.rsplit(":", 1)[1])
    promo = await session.get(__import__("bot.database.models", fromlist=["Promo"]).Promo, pid)
    if promo is None:
        await cb.answer()
        return
    try:
        await cb.message.edit_text(_card(promo), reply_markup=promo_kb(promo))
    except Exception:
        await cb.message.answer(_card(promo), reply_markup=promo_kb(promo))
    await cb.answer()
