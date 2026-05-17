from __future__ import annotations

from decimal import Decimal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models import Product
from bot.payments.base import PaymentProvider


def main_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Каталог", callback_data="catalog")
    kb.button(text="📦 Мои заказы", callback_data="orders")
    kb.adjust(1)
    return kb.as_markup()


def catalog_kb(products: list[Product]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for product in products:
        kb.button(text=product.title, callback_data=f"product:{product.id}")
    kb.button(text="« Назад", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def _fmt_amount(amount: Decimal, currency: str) -> str:
    if currency == "XTR":
        return f"{int(amount)} ⭐"
    if currency == "RUB":
        return f"{amount.normalize():f} ₽"
    return f"{amount.normalize():f} {currency}"


def product_kb(
    product: Product,
    providers: list[PaymentProvider],
    can_buy: bool,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if can_buy:
        for provider in providers:
            price = provider.price_for(product)
            if price is None:
                continue
            label = (
                f"💳 {provider.display_name} · {_fmt_amount(price, provider.currency)}"
            )
            kb.button(text=label, callback_data=f"buy:{product.id}:{provider.code}")
    kb.button(text="« К каталогу", callback_data="catalog")
    kb.adjust(1)
    return kb.as_markup()


def payment_kb(
    order_id: int,
    payment_url: str | None,
    show_check: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if payment_url:
        rows.append([InlineKeyboardButton(text="💳 Оплатить", url=payment_url)])
    if show_check:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Проверить оплату",
                    callback_data=f"check:{order_id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="✖ Отменить", callback_data=f"cancel:{order_id}"
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="« В меню", callback_data="back_to_menu")]
        ]
    )
