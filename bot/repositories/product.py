from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import DeliveryType, Product, StockItem


async def create_product(
    session: AsyncSession,
    *,
    title: str,
    description: str,
    delivery_type: DeliveryType,
) -> Product:
    product = Product(
        title=title,
        description=description,
        delivery_type=delivery_type,
    )
    session.add(product)
    await session.flush()
    return product


async def get_product(session: AsyncSession, product_id: int) -> Product | None:
    return await session.get(Product, product_id)


async def list_active_products(session: AsyncSession) -> list[Product]:
    stmt = (
        select(Product)
        .where(Product.is_active.is_(True))
        .order_by(Product.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_all_products(session: AsyncSession) -> list[Product]:
    stmt = select(Product).order_by(Product.id)
    return list((await session.execute(stmt)).scalars().all())


async def count_available_stock(session: AsyncSession, product_id: int) -> int:
    stmt = select(func.count(StockItem.id)).where(
        StockItem.product_id == product_id,
        StockItem.is_sold.is_(False),
    )
    return int((await session.execute(stmt)).scalar_one())


# Whitelisted writable columns to avoid arbitrary attribute updates.
_EDITABLE_FIELDS = {
    "title",
    "description",
    "is_active",
    "price_stars",
    "price_rub",
    "price_usdt",
}


async def update_product_field(
    session: AsyncSession,
    product_id: int,
    field: str,
    value: object,
) -> Product | None:
    if field not in _EDITABLE_FIELDS:
        raise ValueError(f"Field {field!r} is not editable")
    product = await session.get(Product, product_id)
    if product is None:
        return None
    setattr(product, field, value)
    await session.flush()
    return product


async def delete_product(session: AsyncSession, product_id: int) -> bool:
    product = await session.get(Product, product_id)
    if product is None:
        return False
    await session.delete(product)
    return True


def has_any_price(product: Product) -> bool:
    return any(
        v is not None
        for v in (product.price_stars, product.price_rub, product.price_usdt)
    )


def coerce_decimal(raw: str) -> Decimal | None:
    """Parse a user-entered decimal, or ``None`` if invalid/negative."""
    try:
        value = Decimal(raw.replace(",", ".").strip())
    except (ArithmeticError, ValueError):
        return None
    if value <= 0:
        return None
    return value
