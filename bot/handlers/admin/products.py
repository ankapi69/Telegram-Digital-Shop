from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import DeliveryType
from bot.keyboards.admin import (
    admin_menu_kb,
    delivery_type_kb,
    product_admin_kb,
    products_list_kb,
)
from bot.repositories.product import (
    count_available_stock,
    create_product,
    delete_product,
    get_product,
    list_all_products,
    update_product_field,
)
from bot.states.admin import ProductCreate, ProductEdit

router = Router(name="admin-products")

MAX_TITLE = 128
MAX_DESCRIPTION = 4000
MAX_PRICE_STARS = 1_000_000


def _product_card(product, available: int | None) -> str:
    status = "🟢 активен" if product.is_active else "⚪️ скрыт"
    dtype = (
        "🤖 авто" if product.delivery_type == DeliveryType.AUTO else "✋ ручная"
    )
    stock_line = (
        f"\n📦 В наличии: <b>{available}</b>" if available is not None else ""
    )
    return (
        f"<b>{product.title}</b>\n"
        f"#{product.id} • {dtype} • {status}\n\n"
        f"{product.description or '—'}\n\n"
        f"💰 Цена: <b>{product.price_stars}⭐</b>"
        f"{stock_line}"
    )


# ---- list / view ---------------------------------------------------------


@router.callback_query(F.data == "adm:list")
async def list_products(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.message is None:
        await cb.answer()
        return
    products = await list_all_products(session)
    if not products:
        await cb.message.edit_text(
            "Товаров пока нет.", reply_markup=admin_menu_kb()
        )
    else:
        await cb.message.edit_text(
            "📋 <b>Все товары</b>", reply_markup=products_list_kb(products)
        )
    await cb.answer()


@router.callback_query(F.data.startswith("adm:p:"))
async def view_product(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.message is None or cb.data is None:
        await cb.answer()
        return
    product_id = int(cb.data.rsplit(":", 1)[1])
    product = await get_product(session, product_id)
    if product is None:
        await cb.answer("Не найдено", show_alert=True)
        return
    available = (
        await count_available_stock(session, product.id)
        if product.delivery_type == DeliveryType.AUTO
        else None
    )
    await cb.message.edit_text(
        _product_card(product, available), reply_markup=product_admin_kb(product)
    )
    await cb.answer()


@router.callback_query(F.data.startswith("adm:toggle:"))
async def toggle_active(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.message is None or cb.data is None:
        await cb.answer()
        return
    product_id = int(cb.data.rsplit(":", 1)[1])
    product = await get_product(session, product_id)
    if product is None:
        await cb.answer("Не найдено", show_alert=True)
        return
    product.is_active = not product.is_active
    await session.flush()
    available = (
        await count_available_stock(session, product.id)
        if product.delivery_type == DeliveryType.AUTO
        else None
    )
    await cb.message.edit_text(
        _product_card(product, available), reply_markup=product_admin_kb(product)
    )
    await cb.answer("Готово")


@router.callback_query(F.data.startswith("adm:del:"))
async def delete(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.message is None or cb.data is None:
        await cb.answer()
        return
    product_id = int(cb.data.rsplit(":", 1)[1])
    deleted = await delete_product(session, product_id)
    if not deleted:
        await cb.answer("Не найдено", show_alert=True)
        return
    products = await list_all_products(session)
    if products:
        await cb.message.edit_text(
            "📋 <b>Все товары</b>", reply_markup=products_list_kb(products)
        )
    else:
        await cb.message.edit_text(
            "Товаров пока нет.", reply_markup=admin_menu_kb()
        )
    await cb.answer("Удалено")


# ---- create flow ---------------------------------------------------------


@router.callback_query(F.data == "adm:new")
async def new_product(cb: CallbackQuery, state: FSMContext) -> None:
    if cb.message is None:
        await cb.answer()
        return
    await state.set_state(ProductCreate.title)
    await cb.message.edit_text(
        "Введите название товара (до 128 символов):"
    )
    await cb.answer()


@router.message(ProductCreate.title, F.text)
async def create_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title or len(title) > MAX_TITLE:
        await message.answer(f"Название должно быть от 1 до {MAX_TITLE} символов.")
        return
    await state.update_data(title=title)
    await state.set_state(ProductCreate.description)
    await message.answer("Введите описание (до 4000 символов, можно «-» если без описания):")


@router.message(ProductCreate.description, F.text)
async def create_description(message: Message, state: FSMContext) -> None:
    desc = (message.text or "").strip()
    if desc == "-":
        desc = ""
    if len(desc) > MAX_DESCRIPTION:
        await message.answer(f"Слишком длинно. Максимум {MAX_DESCRIPTION} символов.")
        return
    await state.update_data(description=desc)
    await state.set_state(ProductCreate.price)
    await message.answer("Введите цену в Telegram Stars (целое число, например 50):")


@router.message(ProductCreate.price, F.text)
async def create_price(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Нужно целое число больше нуля.")
        return
    price = int(raw)
    if price <= 0 or price > MAX_PRICE_STARS:
        await message.answer(f"Цена должна быть от 1 до {MAX_PRICE_STARS}.")
        return
    await state.update_data(price=price)
    await state.set_state(ProductCreate.delivery_type)
    await message.answer("Выберите тип выдачи:", reply_markup=delivery_type_kb())


@router.callback_query(ProductCreate.delivery_type, F.data.startswith("adm:dtype:"))
async def create_delivery(
    cb: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    if cb.message is None or cb.data is None:
        await cb.answer()
        return
    dtype_raw = cb.data.rsplit(":", 1)[1]
    try:
        dtype = DeliveryType(dtype_raw)
    except ValueError:
        await cb.answer("Неверный тип", show_alert=True)
        return
    data = await state.get_data()
    product = await create_product(
        session,
        title=data["title"],
        description=data.get("description", ""),
        price_stars=int(data["price"]),
        delivery_type=dtype,
    )
    await state.clear()
    available = 0 if dtype == DeliveryType.AUTO else None
    await cb.message.edit_text(
        "✅ Товар создан.\n\n" + _product_card(product, available),
        reply_markup=product_admin_kb(product),
    )
    await cb.answer()


# ---- edit flow -----------------------------------------------------------


_EDIT_PROMPTS = {
    "title": ("waiting_title", "Введите новое название:"),
    "description": ("waiting_description", "Введите новое описание («-» чтобы очистить):"),
    "price": ("waiting_price", "Введите новую цену (в Stars):"),
}


@router.callback_query(F.data.startswith("adm:edit:"))
async def edit_start(cb: CallbackQuery, state: FSMContext) -> None:
    if cb.message is None or cb.data is None:
        await cb.answer()
        return
    _, _, field, product_id_raw = cb.data.split(":")
    if field not in _EDIT_PROMPTS:
        await cb.answer("Нельзя редактировать это поле", show_alert=True)
        return
    state_name, prompt = _EDIT_PROMPTS[field]
    await state.set_state(getattr(ProductEdit, state_name))
    await state.update_data(product_id=int(product_id_raw))
    await cb.message.edit_text(prompt)
    await cb.answer()


@router.message(ProductEdit.waiting_title, F.text)
async def edit_title(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    title = (message.text or "").strip()
    if not title or len(title) > MAX_TITLE:
        await message.answer(f"От 1 до {MAX_TITLE} символов.")
        return
    await _apply_edit(message, state, session, "title", title)


@router.message(ProductEdit.waiting_description, F.text)
async def edit_description(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    desc = (message.text or "").strip()
    if desc == "-":
        desc = ""
    if len(desc) > MAX_DESCRIPTION:
        await message.answer(f"Максимум {MAX_DESCRIPTION} символов.")
        return
    await _apply_edit(message, state, session, "description", desc)


@router.message(ProductEdit.waiting_price, F.text)
async def edit_price(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Нужно целое число.")
        return
    price = int(raw)
    if price <= 0 or price > MAX_PRICE_STARS:
        await message.answer(f"От 1 до {MAX_PRICE_STARS}.")
        return
    await _apply_edit(message, state, session, "price_stars", price)


async def _apply_edit(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    field: str,
    value: object,
) -> None:
    data = await state.get_data()
    product_id = int(data.get("product_id", 0))
    product = await update_product_field(session, product_id, field, value)
    await state.clear()
    if product is None:
        await message.answer("Товар уже удалён.", reply_markup=admin_menu_kb())
        return
    available = (
        await count_available_stock(session, product.id)
        if product.delivery_type == DeliveryType.AUTO
        else None
    )
    await message.answer(
        "✅ Обновлено.\n\n" + _product_card(product, available),
        reply_markup=product_admin_kb(product),
    )
