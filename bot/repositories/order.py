from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Order, OrderStatus, Product


async def create_order(
    session: AsyncSession,
    *,
    user_id: int,
    product_id: int,
    provider: str,
    currency: str,
    amount: Decimal,
) -> Order:
    order = Order(
        user_id=user_id,
        product_id=product_id,
        provider=provider,
        currency=currency,
        amount=amount,
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


async def find_pending_by_external(
    session: AsyncSession, provider: str, external_id: str
) -> Order | None:
    stmt = select(Order).where(
        Order.provider == provider,
        Order.external_id == external_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def mark_delivered_manual(
    session: AsyncSession, order: Order, content: str
) -> None:
    order.status = OrderStatus.DELIVERED
    order.delivered_content = content
    order.delivered_at = datetime.now(timezone.utc)


async def set_invoice_data(
    session: AsyncSession,
    order: Order,
    external_id: str,
    payment_url: str | None,
) -> None:
    order.external_id = external_id
    order.payment_url = payment_url
    await session.flush()
