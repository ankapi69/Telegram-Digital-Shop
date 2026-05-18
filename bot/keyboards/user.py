from __future__ import annotations

from decimal import Decimal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models import Category, Product
from bot.payments.base import PaymentProvider
from bot.utils.money import fmt_amount


def main_menu_kb(cart_count: int = 0) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Каталог", callback_data="catalog")
    cart_label = f"🧺 Корзина ({cart_count})" if cart_count else "🧺 Корзина"
    kb.button(text=cart_label, callback_data="cart")
    kb.button(text="📦 Мои заказы", callback_data="orders:1")
    kb.button(text="🆘 Поддержка", callback_data="support")
    kb.adjust(1)
    return kb.as_markup()


def categories_kb(
    categories: list[Category], products: list[Product], parent_id: int | None
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for cat in categories:
        kb.button(text=f"📂 {cat.name}", callback_data=f"cat:{cat.id}")
    for p in products:
        kb.button(text=p.title, callback_data=f"product:{p.id}")
    if parent_id is not None:
        kb.button(text="« Вверх", callback_data=f"cat:{parent_id}:up")
    else:
        kb.button(text="« В меню", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def product_kb(
    product: Product,
    providers: list[PaymentProvider],
    can_buy: bool,
    parent_cat_id: int | None,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if can_buy:
        kb.button(text="➕ В корзину", callback_data=f"cart:add:{product.id}")
        for provider in providers:
            price = provider.price_for(product)
            if price is None:
                continue
            kb.button(
                text=f"⚡ Купить · {provider.display_name} · {fmt_amount(price, provider.currency)}",
                callback_data=f"quickbuy:{product.id}:{provider.code}",
            )
    if parent_cat_id is not None:
        kb.button(text="« Назад", callback_data=f"cat:{parent_cat_id}")
    else:
        kb.button(text="« К каталогу", callback_data="catalog")
    kb.adjust(1)
    return kb.as_markup()


def cart_kb(
    lines: list[tuple[Product, int]],
    has_promo: bool,
    can_checkout: bool,
    currencies: list[str],
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for product, qty in lines:
        kb.row(
            InlineKeyboardButton(text=f"− {product.title}", callback_data=f"cart:dec:{product.id}"),
            InlineKeyboardButton(text=f"×{qty}", callback_data="cart:nop"),
            InlineKeyboardButton(text="+", callback_data=f"cart:inc:{product.id}"),
            InlineKeyboardButton(text="🗑", callback_data=f"cart:rm:{product.id}"),
        )
    if lines:
        kb.row(
            InlineKeyboardButton(
                text="🗑 Очистить", callback_data="cart:clear"
            ),
            InlineKeyboardButton(
                text="🏷 Промокод" if not has_promo else "🗑 Снять промо",
                callback_data="cart:promo",
            ),
        )
        if can_checkout:
            for currency in currencies:
                kb.button(text=f"💳 Оформить ({currency})", callback_data=f"checkout:{currency}")
    kb.button(text="« В меню", callback_data="back_to_menu")
    kb.adjust(1)
    return kb.as_markup()


def provider_pick_kb(providers: list[PaymentProvider]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in providers:
        kb.button(text=p.display_name, callback_data=f"pay:{p.code}")
    kb.button(text="« Назад", callback_data="cart")
    kb.adjust(1)
    return kb.as_markup()


def payment_kb(
    order_id: int, payment_url: str | None, show_check: bool
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if payment_url:
        rows.append([InlineKeyboardButton(text="💳 Оплатить", url=payment_url)])
    if show_check:
        rows.append([
            InlineKeyboardButton(
                text="🔄 Проверить оплату", callback_data=f"check:{order_id}"
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text="✖ Отменить", callback_data=f"cancel:{order_id}"
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="« В меню", callback_data="back_to_menu")]]
    )


def orders_pagination_kb(page: int, pages: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="‹", callback_data=f"orders:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{pages}", callback_data="orders:nop"))
    if page < pages:
        nav.append(InlineKeyboardButton(text="›", callback_data=f"orders:{page + 1}"))
    rows.append(nav)
    rows.append([InlineKeyboardButton(text="« В меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def support_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✖ Отмена", callback_data="back_to_menu")]]
    )
