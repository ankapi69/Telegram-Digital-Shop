from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import DeliveryType
from bot.keyboards.admin import admin_menu_kb, product_admin_kb
from bot.repositories.product import count_available_stock, get_product
from bot.repositories.stock import add_stock_items
from bot.services.catalog import CatalogService
from bot.states.admin import StockAdd
from bot.utils.csv_import import parse_stock_csv

router = Router(name="admin-stock")

MAX_ITEMS = 5000
MAX_LEN = 1024


@router.callback_query(F.data.startswith("adm:stock:"))
async def start(
    cb: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    if cb.message is None or cb.data is None:
        await cb.answer()
        return
    pid = int(cb.data.rsplit(":", 1)[1])
    product = await get_product(session, pid)
    if product is None or product.delivery_type != DeliveryType.AUTO:
        await cb.answer("Только для авто-товара", show_alert=True)
        return
    await state.set_state(StockAdd.waiting_items)
    await state.update_data(product_id=pid)
    await cb.message.edit_text(
        f"Пришлите единицы выдачи для «{product.title}»: текстом (по одной в строке) "
        f"или CSV-файлом (первая колонка). Лимит {MAX_ITEMS} за раз."
    )
    await cb.answer()


@router.message(StockAdd.waiting_items, F.document)
async def save_csv(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    catalog: CatalogService,
) -> None:
    if message.document is None:
        return
    if message.document.file_size and message.document.file_size > 5 * 1024 * 1024:
        await message.answer("Файл больше 5 МБ.")
        return
    file = await bot.download(message.document)
    if file is None:
        await message.answer("Не удалось скачать.")
        return
    try:
        items = parse_stock_csv(file.read(), max_items=MAX_ITEMS, max_length=MAX_LEN)
    except ValueError as e:
        await message.answer(str(e))
        return
    await _commit(message, state, session, catalog, items)


@router.message(StockAdd.waiting_items, F.text)
async def save_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    catalog: CatalogService,
) -> None:
    items = [
        line.strip()
        for line in (message.text or "").splitlines()
        if line.strip()
    ]
    if not items:
        await message.answer("Пусто.")
        return
    if len(items) > MAX_ITEMS:
        await message.answer(f"Макс {MAX_ITEMS}.")
        return
    if any(len(x) > MAX_LEN for x in items):
        await message.answer(f"Строка длиннее {MAX_LEN}.")
        return
    await _commit(message, state, session, catalog, items)


async def _commit(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    catalog: CatalogService,
    items: list[str],
) -> None:
    data = await state.get_data()
    pid = int(data.get("product_id", 0))
    product = await get_product(session, pid)
    if product is None or product.delivery_type != DeliveryType.AUTO:
        await state.clear()
        await message.answer("Товар недоступен.")
        return
    added = await add_stock_items(session, pid, items)
    await state.clear()
    await catalog.invalidate()
    available = await count_available_stock(session, pid)
    await message.answer(
        f"✅ Добавлено: <b>{added}</b>. Всего: <b>{available}</b>.",
        reply_markup=product_admin_kb(product),
    )
