from __future__ import annotations

from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.repositories.product import coerce_decimal
from bot.services.rates import RatesService

router = Router(name="admin-rates")


class PinRate(StatesGroup):
    waiting = State()


def _kb(pinned: bool):
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Обновить с CoinGecko", callback_data="adm:rate:refresh")
    if pinned:
        kb.button(text="📌 Снять pin", callback_data="adm:rate:unpin")
    else:
        kb.button(text="📌 Pin курс вручную", callback_data="adm:rate:pin")
    kb.button(text="« Назад", callback_data="adm:menu")
    kb.adjust(1)
    return kb.as_markup()


async def _render(target, rates: RatesService) -> None:
    info = await rates.get()
    lines = ["📈 <b>Курс RUB / USD</b>", ""]
    lines.append(f"Текущий эффективный курс: <b>{info.rate.normalize():f} ₽</b>")
    if info.pinned:
        lines.append("Источник: <i>pin администратора</i>")
    elif info.source_rate is not None:
        lines.append(f"Источник: CoinGecko (≈ {info.source_rate.normalize():f} ₽) + маржа")
        if info.updated_at:
            lines.append(f"Обновлён: {info.updated_at.strftime('%Y-%m-%d %H:%M')}")
    else:
        lines.append("Источник: fallback из .env (CoinGecko ещё не отвечал)")
    text = "\n".join(lines)
    markup = _kb(info.pinned)
    try:
        await target.edit_text(text, reply_markup=markup)
    except Exception:
        await target.answer(text, reply_markup=markup)


@router.callback_query(F.data == "adm:rate")
async def show(cb: CallbackQuery, rates: RatesService) -> None:
    if cb.message is None:
        await cb.answer()
        return
    await _render(cb.message, rates)
    await cb.answer()


@router.callback_query(F.data == "adm:rate:refresh")
async def refresh(cb: CallbackQuery, rates: RatesService) -> None:
    if cb.message is None:
        await cb.answer()
        return
    result = await rates.refresh_once()
    await cb.answer("Обновлено" if result is not None else "CoinGecko не ответил", show_alert=True)
    await _render(cb.message, rates)


@router.callback_query(F.data == "adm:rate:pin")
async def pin_start(cb: CallbackQuery, state: FSMContext) -> None:
    if cb.message is None:
        await cb.answer()
        return
    await state.set_state(PinRate.waiting)
    await cb.message.answer("Введите курс (например, 95.5):")
    await cb.answer()


@router.message(PinRate.waiting, F.text)
async def pin_save(
    message: Message, state: FSMContext, rates: RatesService
) -> None:
    rate = coerce_decimal(message.text or "")
    if rate is None:
        await message.answer("Нужно положительное число.")
        return
    await rates.pin(rate)
    await state.clear()
    await _render(message, rates)


@router.callback_query(F.data == "adm:rate:unpin")
async def unpin(cb: CallbackQuery, rates: RatesService) -> None:
    if cb.message is None:
        await cb.answer()
        return
    await rates.unpin()
    await _render(cb.message, rates)
    await cb.answer("Pin снят")
