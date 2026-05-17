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


def product_admin_kb(product: Product) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Название", callback_data=f"adm:edit:title:{product.id}")
    kb.button(text="📝 Описание", callback_data=f"adm:edit:description:{product.id}")
    kb.button(text="💰 Цена", callback_data=f"adm:edit:price:{product.id}")
    toggle = "🚫 Скрыть" if product.is_active else "✅ Опубликовать"
    kb.button(text=toggle, callback_data=f"adm:toggle:{product.id}")
    if product.delivery_type == DeliveryType.AUTO:
        kb.button(text="📥 Добавить выдачу", callback_data=f"adm:stock:{product.id}")
    kb.button(text="🗑 Удалить", callback_data=f"adm:del:{product.id}")
    kb.button(text="« К списку", callback_data="adm:list")
    kb.adjust(2, 2, 1, 1, 1)
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
            text=f"#{order.id} • {order.price_stars}⭐",
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
