from __future__ import annotations

from decimal import Decimal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models import (
    Category,
    DeliveryType,
    OrderItem,
    Product,
    Promo,
    User,
    UserRole,
)


def admin_menu_kb(role: UserRole) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if role in (UserRole.MANAGER, UserRole.SUPERADMIN):
        kb.button(text="➕ Новый товар", callback_data="adm:new")
        kb.button(text="📋 Товары", callback_data="adm:list")
        kb.button(text="🗂 Категории", callback_data="adm:cat:list")
        kb.button(text="📨 Ручная выдача", callback_data="adm:manual")
    if role == UserRole.SUPERADMIN:
        kb.button(text="🏷 Промокоды", callback_data="adm:promo:list")
        kb.button(text="📊 Статистика", callback_data="adm:stats")
        kb.button(text="📣 Рассылка", callback_data="adm:bcast")
    if role in (UserRole.SUPPORT, UserRole.MANAGER, UserRole.SUPERADMIN):
        kb.button(text="👤 Пользователи", callback_data="adm:users")
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


def _fmt_price(value, unit: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, Decimal):
        return f"{value.normalize():f}{unit}"
    return f"{value}{unit}"


def product_admin_kb(product: Product) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Название", callback_data=f"adm:edit:title:{product.id}")
    kb.button(text="📝 Описание", callback_data=f"adm:edit:description:{product.id}")
    kb.button(text="🖼 Фото", callback_data=f"adm:edit:photo:{product.id}")
    kb.button(text="🗂 Категория", callback_data=f"adm:edit:category:{product.id}")

    kb.button(
        text=f"⭐ {_fmt_price(product.price_stars)}",
        callback_data=f"adm:edit:price_stars:{product.id}",
    )
    kb.button(
        text=f"₽ {_fmt_price(product.price_rub)}",
        callback_data=f"adm:edit:price_rub:{product.id}",
    )
    kb.button(
        text=f"₮ {_fmt_price(product.price_usdt)}",
        callback_data=f"adm:edit:price_usdt:{product.id}",
    )

    if product.delivery_type == DeliveryType.AUTO:
        kb.button(text="📥 Добавить выдачу", callback_data=f"adm:stock:{product.id}")
    else:
        kb.button(text="📄 Шаблон выдачи", callback_data=f"adm:edit:manual_template:{product.id}")

    show_stock = "👁 Скрыть остаток" if product.show_stock else "👁 Показать остаток"
    kb.button(text=show_stock, callback_data=f"adm:stock_vis:{product.id}")
    toggle = "🚫 Скрыть" if product.is_active else "✅ Опубликовать"
    kb.button(text=toggle, callback_data=f"adm:toggle:{product.id}")
    kb.button(text="🗑 Удалить", callback_data=f"adm:del:{product.id}")
    kb.button(text="« К списку", callback_data="adm:list")
    kb.adjust(2, 2, 1, 1, 1, 1, 1, 1, 1, 1)
    return kb.as_markup()


def delivery_type_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Авто (из склада)", callback_data="adm:dtype:auto")
    kb.button(text="Ручная выдача", callback_data="adm:dtype:manual")
    kb.adjust(1)
    return kb.as_markup()


def categories_admin_kb(categories: list[Category]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for c in categories:
        prefix = "📂" if c.parent_id is None else "  └"
        kb.button(text=f"{prefix} {c.name}", callback_data=f"adm:cat:{c.id}")
    kb.button(text="➕ Новая категория", callback_data="adm:cat:new")
    kb.button(text="« Назад", callback_data="adm:menu")
    kb.adjust(1)
    return kb.as_markup()


def category_admin_kb(category: Category) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Имя", callback_data=f"adm:cat:rename:{category.id}")
    if category.parent_id is None:
        kb.button(text="➕ Подкатегория", callback_data=f"adm:cat:sub:{category.id}")
    kb.button(text="🗑 Удалить", callback_data=f"adm:cat:del:{category.id}")
    kb.button(text="« К списку", callback_data="adm:cat:list")
    kb.adjust(1)
    return kb.as_markup()


def category_pick_kb(
    categories: list[Category], product_id: int
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="(без категории)", callback_data=f"adm:setcat:{product_id}:0")
    for c in categories:
        prefix = "📂" if c.parent_id is None else "  └"
        kb.button(text=f"{prefix} {c.name}", callback_data=f"adm:setcat:{product_id}:{c.id}")
    kb.button(text="« Назад", callback_data=f"adm:p:{product_id}")
    kb.adjust(1)
    return kb.as_markup()


def pending_items_kb(items: list[OrderItem]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for it in items:
        kb.button(
            text=f"#{it.order_id}·{it.id} {it.title_snapshot}",
            callback_data=f"adm:item:{it.id}",
        )
    kb.button(text="« Назад", callback_data="adm:menu")
    kb.adjust(1)
    return kb.as_markup()


def item_fulfill_kb(item_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✉️ Выдать", callback_data=f"adm:fulfill:{item_id}")
    kb.button(text="« К списку", callback_data="adm:manual")
    kb.adjust(1)
    return kb.as_markup()


def promos_list_kb(promos: list[Promo]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in promos:
        mark = "🟢" if p.is_active else "⚪️"
        kb.button(text=f"{mark} {p.code}", callback_data=f"adm:promo:{p.id}")
    kb.button(text="➕ Новый", callback_data="adm:promo:new")
    kb.button(text="« Назад", callback_data="adm:menu")
    kb.adjust(1)
    return kb.as_markup()


def promo_kb(promo: Promo) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    toggle = "🚫 Выкл" if promo.is_active else "✅ Вкл"
    kb.button(text=toggle, callback_data=f"adm:promo:tog:{promo.id}")
    kb.button(text="🗑 Удалить", callback_data=f"adm:promo:del:{promo.id}")
    kb.button(text="« К списку", callback_data="adm:promo:list")
    kb.adjust(1)
    return kb.as_markup()


def users_list_kb(users: list[User]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for u in users:
        flag = "🚫" if u.is_banned else "✅"
        kb.button(text=f"{flag} {u.full_name or u.username or u.id}", callback_data=f"adm:u:{u.id}")
    kb.button(text="🔎 Найти", callback_data="adm:u:find")
    kb.button(text="« Назад", callback_data="adm:menu")
    kb.adjust(1)
    return kb.as_markup()


def user_card_kb(user: User) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if user.is_banned:
        kb.button(text="✅ Разблокировать", callback_data=f"adm:u:unban:{user.id}")
    else:
        kb.button(text="🚫 Заблокировать", callback_data=f"adm:u:ban:{user.id}")
    kb.button(text="« К списку", callback_data="adm:users")
    kb.adjust(1)
    return kb.as_markup()


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🚀 Разослать", callback_data="adm:bcast:go")
    kb.button(text="✖ Отмена", callback_data="adm:menu")
    kb.adjust(1)
    return kb.as_markup()
