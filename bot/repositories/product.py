from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import DeliveryType, Product, StockItem


async def create_product(
    session: AsyncSession,
    *,
    title: str,
    description: str,
    price_stars: int,
    delivery_type: DeliveryType,
) -> Product:
    product = Product(
        title=title,
        description=description,
        price_stars=price_stars,
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


async def update_product_field(
    session: AsyncSession,
    product_id: int,
    field: str,
    value: object,
) -> Product | None:
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
