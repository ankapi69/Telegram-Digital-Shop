from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import DeliveryType
from bot.keyboards.admin import admin_menu_kb, product_admin_kb
from bot.repositories.product import count_available_stock, get_product
from bot.repositories.stock import add_stock_items
from bot.states.admin import StockAdd

router = Router(name="admin-stock")

MAX_ITEMS_PER_BATCH = 1000
MAX_ITEM_LENGTH = 1024


@router.callback_query(F.data.startswith("adm:stock:"))
async def stock_start(
    cb: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    if cb.message is None or cb.data is None:
        await cb.answer()
        return
    product_id = int(cb.data.rsplit(":", 1)[1])
    product = await get_product(session, product_id)
    if product is None:
        await cb.answer("Не найдено", show_alert=True)
        return
    if product.delivery_type != DeliveryType.AUTO:
        await cb.answer("Только для автотовара", show_alert=True)
        return
    await state.set_state(StockAdd.waiting_items)
    await state.update_data(product_id=product_id)
    await cb.message.edit_text(
        f"Пришлите единицы выдачи для «{product.title}», по одной в строке.\n"
        f"Максимум {MAX_ITEMS_PER_BATCH} за раз."
    )
    await cb.answer()


@router.message(StockAdd.waiting_items, F.text)
async def stock_save(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    product_id = int(data.get("product_id", 0))
    raw_lines = (message.text or "").splitlines()
    items = [line.strip() for line in raw_lines if line.strip()]
    if not items:
        await message.answer("Не вижу ни одной строки. Попробуйте снова.")
        return
    if len(items) > MAX_ITEMS_PER_BATCH:
        await message.answer(
            f"Слишком много за раз. Максимум {MAX_ITEMS_PER_BATCH}."
        )
        return
    for line in items:
        if len(line) > MAX_ITEM_LENGTH:
            await message.answer(
                f"Слишком длинная строка (>{MAX_ITEM_LENGTH} символов). "
                "Разбейте на несколько."
            )
            return

    product = await get_product(session, product_id)
    if product is None or product.delivery_type != DeliveryType.AUTO:
        await state.clear()
        await message.answer("Товар недоступен.", reply_markup=admin_menu_kb())
        return

    added = await add_stock_items(session, product_id, items)
    await state.clear()
    available = await count_available_stock(session, product_id)
    await message.answer(
        f"✅ Добавлено: <b>{added}</b>. Всего в наличии: <b>{available}</b>.",
        reply_markup=product_admin_kb(product),
    )
