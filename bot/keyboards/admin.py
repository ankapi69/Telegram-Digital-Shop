from __future__ import annotations

from decimal import Decimal

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models import DeliveryType, Order, Product


def admin_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Новый товар", callback_data="adm:new")
    kb.button(text="📋 Все товары", callback_data="adm:list")
    kb.button(text="📨 Ручная выдача", callback_data="adm:manual")
    kb.adjust(1)
    return kb.as_markup()


def products_list_kb(products: list[Product]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in products:
        mark = "🟢" if p.is_active else "⚪️"
        kb.button(text=f"{mark} {p.title}", callback_data=f"adm:p:{p.id}")
    kb.button(text="« Назад", callback_data="adm:menu")
    kb.adjust(1)
    return kb.as_markup()


def _fmt_price(value: Decimal | int | None, unit: str) -> str:
    if value is None:
        return "—"
    if isinstance(value, Decimal):
        value = value.normalize()
    return f"{value} {unit}"


def product_admin_kb(product: Product) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Название", callback_data=f"adm:edit:title:{product.id}")
    kb.button(text="📝 Описание", callback_data=f"adm:edit:description:{product.id}")

    kb.button(
        text=f"⭐ Stars: {_fmt_price(product.price_stars, '')}".strip(),
        callback_data=f"adm:edit:price_stars:{product.id}",
    )
    kb.button(
        text=f"₽ RUB: {_fmt_price(product.price_rub, '')}".strip(),
        callback_data=f"adm:edit:price_rub:{product.id}",
    )
    kb.button(
        text=f"₮ USDT: {_fmt_price(product.price_usdt, '')}".strip(),
        callback_data=f"adm:edit:price_usdt:{product.id}",
    )

    toggle = "🚫 Скрыть" if product.is_active else "✅ Опубликовать"
    kb.button(text=toggle, callback_data=f"adm:toggle:{product.id}")
    if product.delivery_type == DeliveryType.AUTO:
        kb.button(text="📥 Добавить выдачу", callback_data=f"adm:stock:{product.id}")
    kb.button(text="🗑 Удалить", callback_data=f"adm:del:{product.id}")
    kb.button(text="« К списку", callback_data="adm:list")
    kb.adjust(2, 1, 1, 1, 1, 1, 1, 1)
    return kb.as_markup()


def delivery_type_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Авто (из склада)", callback_data="adm:dtype:auto")
    kb.button(text="Ручная выдача", callback_data="adm:dtype:manual")
    kb.adjust(1)
    return kb.as_markup()


def pending_orders_kb(orders: list[Order]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for order in orders:
        kb.button(
            text=f"#{order.id} • {order.amount} {order.currency}",
            callback_data=f"adm:ord:{order.id}",
        )
    kb.button(text="« Назад", callback_data="adm:menu")
    kb.adjust(1)
    return kb.as_markup()


def order_fulfill_kb(order_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✉️ Выдать", callback_data=f"adm:fulfill:{order_id}")
    kb.button(text="« К списку", callback_data="adm:manual")
    kb.adjust(1)
    return kb.as_markup()
