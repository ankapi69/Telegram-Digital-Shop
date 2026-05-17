from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Order, OrderStatus, Product


async def create_order(
    session: AsyncSession,
    *,
    user_id: int,
    product_id: int,
    price_stars: int,
) -> Order:
    order = Order(
        user_id=user_id,
        product_id=product_id,
        price_stars=price_stars,
        status=OrderStatus.PENDING_PAYMENT,
    )
    session.add(order)
    await session.flush()
    return order


async def get_order(session: AsyncSession, order_id: int) -> Order | None:
    return await session.get(Order, order_id)


async def get_order_with_product(
    session: AsyncSession, order_id: int
) -> tuple[Order, Product] | None:
    stmt = (
        select(Order, Product)
        .join(Product, Product.id == Order.product_id)
        .where(Order.id == order_id)
    )
    row = (await session.execute(stmt)).first()
    return (row[0], row[1]) if row else None


async def list_awaiting_delivery(session: AsyncSession) -> list[Order]:
    stmt = (
        select(Order)
        .where(Order.status == OrderStatus.AWAITING_DELIVERY)
        .order_by(Order.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_user_orders(session: AsyncSession, user_id: int) -> list[Order]:
    stmt = (
        select(Order)
        .where(Order.user_id == user_id)
        .order_by(Order.id.desc())
        .limit(20)
    )
    return list((await session.execute(stmt)).scalars().all())


async def mark_delivered(
    session: AsyncSession, order: Order, content: str
) -> None:
    order.status = OrderStatus.DELIVERED
    order.delivered_content = content
    order.delivered_at = datetime.now(timezone.utc)


async def mark_awaiting_delivery(
    session: AsyncSession, order: Order, charge_id: str | None
) -> None:
    order.status = OrderStatus.AWAITING_DELIVERY
    order.payment_charge_id = charge_id
