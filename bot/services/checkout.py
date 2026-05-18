from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import DeliveryType, Order, Product
from bot.payments.base import PaymentProvider
from bot.repositories import order as order_repo
from bot.repositories import product as product_repo
from bot.services.cart import CartLine
from bot.services.promo import PromoApplication, apply_promo


@dataclass(slots=True)
class CheckoutQuote:
    provider: PaymentProvider
    lines: list[tuple[Product, int, Decimal]]  # product, qty, unit_price
    subtotal: Decimal
    discount: Decimal
    total: Decimal
    promo: PromoApplication | None


class CheckoutError(Exception):
    pass


async def build_quote(
    session: AsyncSession,
    *,
    provider: PaymentProvider,
    cart_lines: list[CartLine],
    promo_code: str | None,
) -> CheckoutQuote:
    if not cart_lines:
        raise CheckoutError("Корзина пуста")

    lines: list[tuple[Product, int, Decimal]] = []
    subtotal = Decimal(0)
    for line in cart_lines:
        product = await product_repo.get_product(session, line.product_id)
        if product is None or not product.is_active:
            raise CheckoutError(f"Товар недоступен (#{line.product_id})")
        unit_price = provider.price_for(product)
        if unit_price is None:
            raise CheckoutError(
                f"Товар «{product.title}» не продаётся через {provider.display_name}"
            )
        if product.delivery_type == DeliveryType.AUTO:
            available = await product_repo.count_available_stock(session, product.id)
            if available < line.quantity:
                raise CheckoutError(
                    f"Недостаточно «{product.title}»: в наличии {available}"
                )
        lines.append((product, line.quantity, Decimal(unit_price)))
        subtotal += Decimal(unit_price) * line.quantity

    promo = await apply_promo(session, promo_code, subtotal, provider.currency)
    discount = promo.discount if promo else Decimal(0)
    total = subtotal - discount
    if total < 0:
        total = Decimal(0)
    return CheckoutQuote(
        provider=provider,
        lines=lines,
        subtotal=subtotal,
        discount=discount,
        total=total,
        promo=promo,
    )


async def materialize_order(
    session: AsyncSession,
    *,
    user_id: int,
    quote: CheckoutQuote,
) -> Order:
    return await order_repo.create_order(
        session,
        user_id=user_id,
        provider=quote.provider.code,
        currency=quote.provider.currency,
        subtotal=quote.subtotal,
        discount=quote.discount,
        total=quote.total,
        promo_code=quote.promo.promo.code if quote.promo else None,
        items=quote.lines,
    )
