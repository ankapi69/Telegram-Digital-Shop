from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.markdown import hbold
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import DeliveryType
from bot.keyboards.user import catalog_kb, product_kb
from bot.repositories.product import (
    count_available_stock,
    get_product,
    list_active_products,
)

router = Router(name="catalog")


@router.callback_query(F.data == "catalog")
async def show_catalog(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.message is None:
        await cb.answer()
        return
    products = await list_active_products(session)
    if not products:
        await cb.message.edit_text(
            "Каталог пока пуст. Загляните позже.",
            reply_markup=catalog_kb([]),
        )
    else:
        await cb.message.edit_text(
            "🛍 <b>Каталог</b>\n\nВыберите товар:",
            reply_markup=catalog_kb(products),
        )
    await cb.answer()


@router.callback_query(F.data.startswith("product:"))
async def show_product(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.message is None or cb.data is None:
        await cb.answer()
        return
    product_id = int(cb.data.split(":", 1)[1])
    product = await get_product(session, product_id)
    if product is None or not product.is_active:
        await cb.answer("Товар недоступен", show_alert=True)
        return

    available_line = ""
    can_buy = True
    if product.delivery_type == DeliveryType.AUTO:
        available = await count_available_stock(session, product.id)
        available_line = f"\n📦 В наличии: <b>{available}</b>"
        can_buy = available > 0
    else:
        available_line = "\n📨 Выдаётся вручную после оплаты"

    text = (
        f"{hbold(product.title)}\n\n"
        f"{product.description or '—'}\n\n"
        f"💰 Цена: <b>{product.price_stars}⭐</b>"
        f"{available_line}"
    )
    await cb.message.edit_text(text, reply_markup=product_kb(product.id, can_buy))
    await cb.answer()
