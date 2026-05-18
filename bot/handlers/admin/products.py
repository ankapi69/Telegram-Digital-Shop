from __future__ import annotations

from decimal import Decimal

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import DeliveryType
from bot.keyboards.admin import (
    admin_menu_kb,
    category_pick_kb,
    delivery_type_kb,
    product_admin_kb,
    products_list_kb,
)
from bot.repositories import category as cat_repo
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
from bot.services.catalog import CatalogService
from bot.states.admin import ProductCreate, ProductEdit

router = Router(name="admin-products")

MAX_TITLE = 128
MAX_DESCRIPTION = 4000
MAX_PRICE_STARS = 1_000_000
MAX_PRICE_FIAT = Decimal("1000000")
MAX_PRICE_CRYPTO = Decimal("1000000")


def _product_card(product, available: int | None) -> str:
    status = "🟢 активен" if product.is_active else "⚪️ скрыт"
    dtype = "🤖 авто" if product.delivery_type == DeliveryType.AUTO else "✋ ручная"
    photo = "🖼" if product.photo_file_id else "—"
    stock_line = f"\n📦 В наличии: <b>{available}</b>" if available is not None else ""
    prices = []
    if product.price_stars is not None:
        prices.append(f"  • ⭐ Stars: <b>{product.price_stars}</b>")
    if product.price_rub is not None:
        prices.append(f"  • ₽ RUB: <b>{product.price_rub.normalize():f}</b>")
    if product.price_usdt is not None:
        prices.append(f"  • ₮ USDT: <b>{product.price_usdt.normalize():f}</b>")
    if not prices:
        prices.append("  ⚠️ цены не заданы — товар нельзя купить")
    return (
        f"<b>{product.title}</b>\n"
        f"#{product.id} • {dtype} • {status} • фото: {photo}\n\n"
        f"{product.description or '—'}\n\n"
        f"💰 Цены:\n" + "\n".join(prices) + stock_line
    )


@router.callback_query(F.data == "adm:list")
async def list_products(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.message is None:
        await cb.answer()
        return
    products = await list_all_products(session)
    if not products:
        try:
            await cb.message.edit_text("Товаров нет.")
        except Exception:
            pass
    else:
        try:
            await cb.message.edit_text(
                "📋 <b>Товары</b>", reply_markup=products_list_kb(products)
            )
        except Exception:
            await cb.message.answer(
                "📋 <b>Товары</b>", reply_markup=products_list_kb(products)
            )
    await cb.answer()


@router.callback_query(F.data.startswith("adm:p:"))
async def view_product(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.message is None or cb.data is None:
        await cb.answer()
        return
    pid = int(cb.data.rsplit(":", 1)[1])
    product = await get_product(session, pid)
    if product is None:
        await cb.answer("Нет", show_alert=True)
        return
    available = (
        await count_available_stock(session, product.id)
        if product.delivery_type == DeliveryType.AUTO
        else None
    )
    try:
        await cb.message.edit_text(
            _product_card(product, available), reply_markup=product_admin_kb(product)
        )
    except Exception:
        await cb.message.answer(
            _product_card(product, available), reply_markup=product_admin_kb(product)
        )
    await cb.answer()


@router.callback_query(F.data.startswith("adm:toggle:"))
async def toggle_active(
    cb: CallbackQuery, session: AsyncSession, catalog: CatalogService
) -> None:
    if cb.message is None or cb.data is None:
        await cb.answer()
        return
    pid = int(cb.data.rsplit(":", 1)[1])
    product = await get_product(session, pid)
    if product is None:
        await cb.answer("Нет", show_alert=True)
        return
    if not product.is_active and not has_any_price(product):
        await cb.answer("Сначала задайте цену", show_alert=True)
        return
    product.is_active = not product.is_active
    await session.flush()
    await catalog.invalidate()
    available = (
        await count_available_stock(session, product.id)
        if product.delivery_type == DeliveryType.AUTO
        else None
    )
    try:
        await cb.message.edit_text(
            _product_card(product, available), reply_markup=product_admin_kb(product)
        )
    except Exception:
        pass
    await cb.answer("Готово")


@router.callback_query(F.data.startswith("adm:stock_vis:"))
async def toggle_stock_visibility(
    cb: CallbackQuery, session: AsyncSession
) -> None:
    if cb.message is None or cb.data is None:
        await cb.answer()
        return
    pid = int(cb.data.rsplit(":", 1)[1])
    product = await get_product(session, pid)
    if product is None:
        await cb.answer()
        return
    product.show_stock = not product.show_stock
    await session.flush()
    available = (
        await count_available_stock(session, product.id)
        if product.delivery_type == DeliveryType.AUTO
        else None
    )
    try:
        await cb.message.edit_text(
            _product_card(product, available), reply_markup=product_admin_kb(product)
        )
    except Exception:
        pass
    await cb.answer()


@router.callback_query(F.data.startswith("adm:del:"))
async def delete(
    cb: CallbackQuery, session: AsyncSession, catalog: CatalogService
) -> None:
    if cb.data is None or cb.message is None:
        await cb.answer()
        return
    pid = int(cb.data.rsplit(":", 1)[1])
    if not await delete_product(session, pid):
        await cb.answer("Нет", show_alert=True)
        return
    await catalog.invalidate()
    products = await list_all_products(session)
    try:
        await cb.message.edit_text(
            "📋 <b>Товары</b>" if products else "Товаров нет.",
            reply_markup=products_list_kb(products) if products else None,
        )
    except Exception:
        pass
    await cb.answer("Удалено")


# ---- create flow ---------------------------------------------------------


@router.callback_query(F.data == "adm:new")
async def new_product(cb: CallbackQuery, state: FSMContext) -> None:
    if cb.message is None:
        await cb.answer()
        return
    await state.set_state(ProductCreate.title)
    await cb.message.edit_text("Название товара (до 128):")
    await cb.answer()


@router.message(ProductCreate.title, F.text)
async def create_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not title or len(title) > MAX_TITLE:
        await message.answer(f"1..{MAX_TITLE} символов.")
        return
    await state.update_data(title=title)
    await state.set_state(ProductCreate.description)
    await message.answer("Описание (или «-»):")


@router.message(ProductCreate.description, F.text)
async def create_description(message: Message, state: FSMContext) -> None:
    desc = (message.text or "").strip()
    if desc == "-":
        desc = ""
    if len(desc) > MAX_DESCRIPTION:
        await message.answer(f"Макс {MAX_DESCRIPTION}.")
        return
    await state.update_data(description=desc)
    await state.set_state(ProductCreate.delivery_type)
    await message.answer("Тип выдачи:", reply_markup=delivery_type_kb())


@router.callback_query(ProductCreate.delivery_type, F.data.startswith("adm:dtype:"))
async def create_delivery(
    cb: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    catalog: CatalogService,
) -> None:
    if cb.message is None or cb.data is None:
        await cb.answer()
        return
    try:
        dtype = DeliveryType(cb.data.rsplit(":", 1)[1])
    except ValueError:
        await cb.answer()
        return
    data = await state.get_data()
    product = await create_product(
        session,
        title=data["title"],
        description=data.get("description", ""),
        delivery_type=dtype,
        category_id=None,
    )
    await state.clear()
    await catalog.invalidate()
    available = 0 if dtype == DeliveryType.AUTO else None
    try:
        await cb.message.edit_text(
            "✅ Создан. Задайте цены / категорию.\n\n" + _product_card(product, available),
            reply_markup=product_admin_kb(product),
        )
    except Exception:
        await cb.message.answer(
            _product_card(product, available), reply_markup=product_admin_kb(product)
        )
    await cb.answer()


# ---- edit ----------------------------------------------------------------


_EDIT_PROMPTS = {
    "title": (ProductEdit.waiting_title, "Новое название:"),
    "description": (ProductEdit.waiting_description, "Новое описание («-» очистить):"),
    "price_stars": (ProductEdit.waiting_price_stars, "Цена в Stars (целое, «-» снять):"),
    "price_rub": (ProductEdit.waiting_price_rub, "Цена в RUB («-» снять):"),
    "price_usdt": (ProductEdit.waiting_price_usdt, "Цена в USDT («-» снять):"),
    "photo": (ProductEdit.waiting_photo, "Пришлите фото (или «-» убрать):"),
    "manual_template": (
        ProductEdit.waiting_manual_template,
        "Шаблон ручной выдачи (текст; «-» снять):",
    ),
}


@router.callback_query(F.data.startswith("adm:edit:"))
async def edit_start(
    cb: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    if cb.message is None or cb.data is None:
        await cb.answer()
        return
    _, _, field, pid_raw = cb.data.split(":")
    pid = int(pid_raw)
    if field == "category":
        cats = await cat_repo.list_all(session)
        await cb.message.edit_text(
            "Выберите категорию:", reply_markup=category_pick_kb(cats, pid)
        )
        await cb.answer()
        return
    if field not in _EDIT_PROMPTS:
        await cb.answer()
        return
    target_state, prompt = _EDIT_PROMPTS[field]
    await state.set_state(target_state)
    await state.update_data(product_id=pid)
    await cb.message.edit_text(prompt)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:setcat:"))
async def set_category(
    cb: CallbackQuery, session: AsyncSession, catalog: CatalogService
) -> None:
    if cb.data is None or cb.message is None:
        await cb.answer()
        return
    _, _, pid_raw, cat_raw = cb.data.split(":")
    pid = int(pid_raw)
    cat_id = int(cat_raw) or None
    product = await update_product_field(session, pid, "category_id", cat_id)
    await catalog.invalidate()
    if product is None:
        await cb.answer("Нет", show_alert=True)
        return
    available = (
        await count_available_stock(session, product.id)
        if product.delivery_type == DeliveryType.AUTO
        else None
    )
    try:
        await cb.message.edit_text(
            _product_card(product, available), reply_markup=product_admin_kb(product)
        )
    except Exception:
        pass
    await cb.answer()


@router.message(ProductEdit.waiting_title, F.text)
async def edit_title(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    catalog: CatalogService,
) -> None:
    value = (message.text or "").strip()
    if not value or len(value) > MAX_TITLE:
        await message.answer(f"1..{MAX_TITLE}.")
        return
    await _apply(message, state, session, catalog, "title", value)


@router.message(ProductEdit.waiting_description, F.text)
async def edit_desc(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    catalog: CatalogService,
) -> None:
    raw = (message.text or "").strip()
    if raw == "-":
        raw = ""
    if len(raw) > MAX_DESCRIPTION:
        await message.answer(f"Макс {MAX_DESCRIPTION}.")
        return
    await _apply(message, state, session, catalog, "description", raw)


@router.message(ProductEdit.waiting_manual_template, F.text)
async def edit_manual_template(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    catalog: CatalogService,
) -> None:
    raw = (message.text or "").strip()
    value: str | None = None if raw == "-" else raw
    if value is not None and len(value) > MAX_DESCRIPTION:
        await message.answer(f"Макс {MAX_DESCRIPTION}.")
        return
    await _apply(message, state, session, catalog, "manual_template", value)


@router.message(ProductEdit.waiting_photo, F.photo)
async def edit_photo(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    catalog: CatalogService,
) -> None:
    if not message.photo:
        return
    file_id = message.photo[-1].file_id
    await _apply(message, state, session, catalog, "photo_file_id", file_id)


@router.message(ProductEdit.waiting_photo, F.text)
async def edit_photo_clear(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    catalog: CatalogService,
) -> None:
    if (message.text or "").strip() != "-":
        await message.answer("Пришлите фото или «-».")
        return
    await _apply(message, state, session, catalog, "photo_file_id", None)


@router.message(ProductEdit.waiting_price_stars, F.text)
async def edit_price_stars(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    catalog: CatalogService,
) -> None:
    raw = (message.text or "").strip()
    if raw == "-":
        await _apply(message, state, session, catalog, "price_stars", None)
        return
    if not raw.isdigit():
        await message.answer("Нужно целое или «-».")
        return
    v = int(raw)
    if v <= 0 or v > MAX_PRICE_STARS:
        await message.answer(f"1..{MAX_PRICE_STARS}.")
        return
    await _apply(message, state, session, catalog, "price_stars", v)


@router.message(ProductEdit.waiting_price_rub, F.text)
async def edit_price_rub(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    catalog: CatalogService,
) -> None:
    await _decimal(message, state, session, catalog, "price_rub", MAX_PRICE_FIAT)


@router.message(ProductEdit.waiting_price_usdt, F.text)
async def edit_price_usdt(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    catalog: CatalogService,
) -> None:
    await _decimal(message, state, session, catalog, "price_usdt", MAX_PRICE_CRYPTO)


async def _decimal(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    catalog: CatalogService,
    field: str,
    cap: Decimal,
) -> None:
    raw = (message.text or "").strip()
    if raw == "-":
        await _apply(message, state, session, catalog, field, None)
        return
    v = coerce_decimal(raw)
    if v is None or v > cap:
        await message.answer(f"1..{cap} или «-».")
        return
    await _apply(message, state, session, catalog, field, v)


async def _apply(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    catalog: CatalogService,
    field: str,
    value: object,
) -> None:
    data = await state.get_data()
    pid = int(data.get("product_id", 0))
    product = await update_product_field(session, pid, field, value)
    await state.clear()
    if product is None:
        await message.answer("Уже удалён.")
        return
    await catalog.invalidate()
    available = (
        await count_available_stock(session, product.id)
        if product.delivery_type == DeliveryType.AUTO
        else None
    )
    await message.answer(
        _product_card(product, available), reply_markup=product_admin_kb(product)
    )
