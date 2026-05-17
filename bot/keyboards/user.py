from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models import Product


def main_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Каталог", callback_data="catalog")
    kb.button(text="📦 Мои заказы", callback_data="orders")
    kb.adjust(1)
    return kb.as_markup()


def catalog_kb(products: list[Product]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for product in products:
        kb.button(
            text=f"{product.title} — {product.price_stars}⭐",
            callback_data=f"product:{product.id}",
        )
    kb.button(text="« Назад", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def product_kb(product_id: int, can_buy: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if can_buy:
        kb.button(text="💳 Купить", callback_data=f"buy:{product_id}")
    kb.button(text="« К каталогу", callback_data="catalog")
    kb.adjust(1)
    return kb.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="« В меню", callback_data="back_to_menu")]
        ]
    )
