from decimal import Decimal

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
    coerce_decimal,
    count_available_stock,
    create_product,
    delete_product,
    get_product,
    has_any_price,
    list_all_products,
    update_product_field,
)
from bot.states.admin import ProductCreate, ProductEdit

router = Router(name="admin-products")

MAX_TITLE = 128
MAX_DESCRIPTION = 4000
MAX_PRICE_STARS = 1_000_000
MAX_PRICE_FIAT = Decimal("1000000")  # rubles
MAX_PRICE_CRYPTO = Decimal("1000000")  # USDT


def _product_card(product, available: int | None) -> str:
    status = "🟢 активен" if product.is_active else "⚪️ скрыт"
    dtype = (
        "🤖 авто" if product.delivery_type == DeliveryType.AUTO else "✋ ручная"
    )
    stock_line = (
        f"\n📦 В наличии: <b>{available}</b>" if available is not None else ""
    )
    price_lines = []
    if product.price_stars is not None:
        price_lines.append(f"  • ⭐ Stars: <b>{product.price_stars}</b>")
    if product.price_rub is not None:
        price_lines.append(f"  • ₽ RUB: <b>{product.price_rub.normalize():f}</b>")
    if product.price_usdt is not None:
        price_lines.append(f"  • ₮ USDT: <b>{product.price_usdt.normalize():f}</b>")
    if not price_lines:
        price_lines.append("  ⚠️ цены не заданы — товар нельзя купить")

    return (
        f"<b>{product.title}</b>\n"
        f"#{product.id} • {dtype} • {status}\n\n"
        f"{product.description or '—'}\n\n"
        "💰 Цены:\n"
        + "\n".join(price_lines)
        + stock_line
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
    if not product.is_active and not has_any_price(product):
        await cb.answer(
            "Сначала задайте хотя бы одну цену, потом публикуйте.", show_alert=True
        )
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
    await cb.message.edit_text("Введите название товара (до 128 символов):")
    await cb.answer()


@router.message(ProductCreate.title, F.text)
async def create_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title or len(title) > MAX_TITLE:
        await message.answer(f"От 1 до {MAX_TITLE} символов.")
        return
    await state.update_data(title=title)
    await state.set_state(ProductCreate.description)
    await message.answer(
        "Введите описание (до 4000 символов, «-» для пустого):"
    )


@router.message(ProductCreate.description, F.text)
async def create_description(message: Message, state: FSMContext) -> None:
    desc = (message.text or "").strip()
    if desc == "-":
        desc = ""
    if len(desc) > MAX_DESCRIPTION:
        await message.answer(f"Максимум {MAX_DESCRIPTION} символов.")
        return
    await state.update_data(description=desc)
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
        delivery_type=dtype,
    )
    await state.clear()
    available = 0 if dtype == DeliveryType.AUTO else None
    await cb.message.edit_text(
        "✅ Товар создан.  Теперь задайте хотя бы одну цену.\n\n"
        + _product_card(product, available),
        reply_markup=product_admin_kb(product),
    )
    await cb.answer()


# ---- edit flow -----------------------------------------------------------


_EDIT_PROMPTS = {
    "title": (ProductEdit.waiting_title, "Введите новое название:"),
    "description": (
        ProductEdit.waiting_description,
        "Введите новое описание («-» чтобы очистить):",
    ),
    "price_stars": (
        ProductEdit.waiting_price_stars,
        "Введите цену в Telegram Stars (целое число, «-» чтобы убрать):",
    ),
    "price_rub": (
        ProductEdit.waiting_price_rub,
        "Введите цену в рублях (например 100 или 99.50, «-» чтобы убрать):",
    ),
    "price_usdt": (
        ProductEdit.waiting_price_usdt,
        "Введите цену в USDT (например 5.5, «-» чтобы убрать):",
    ),
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
    target_state, prompt = _EDIT_PROMPTS[field]
    await state.set_state(target_state)
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


@router.message(ProductEdit.waiting_price_stars, F.text)
async def edit_price_stars(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    raw = (message.text or "").strip()
    if raw == "-":
        await _apply_edit(message, state, session, "price_stars", None)
        return
    if not raw.isdigit():
        await message.answer("Нужно целое число больше нуля или «-».")
        return
    value = int(raw)
    if value <= 0 or value > MAX_PRICE_STARS:
        await message.answer(f"От 1 до {MAX_PRICE_STARS}.")
        return
    await _apply_edit(message, state, session, "price_stars", value)


@router.message(ProductEdit.waiting_price_rub, F.text)
async def edit_price_rub(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await _edit_decimal(
        message, state, session, "price_rub", MAX_PRICE_FIAT
    )


@router.message(ProductEdit.waiting_price_usdt, F.text)
async def edit_price_usdt(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await _edit_decimal(
        message, state, session, "price_usdt", MAX_PRICE_CRYPTO
    )


async def _edit_decimal(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    field: str,
    max_value: Decimal,
) -> None:
    raw = (message.text or "").strip()
    if raw == "-":
        await _apply_edit(message, state, session, field, None)
        return
    value = coerce_decimal(raw)
    if value is None or value > max_value:
        await message.answer(
            f"Нужно положительное число до {max_value} или «-», чтобы убрать."
        )
        return
    await _apply_edit(message, state, session, field, value)


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
