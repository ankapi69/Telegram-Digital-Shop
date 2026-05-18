from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Order, OrderItem, OrderStatus, User


_PAID_STATUSES = (OrderStatus.AWAITING_DELIVERY, OrderStatus.DELIVERED)


async def revenue_by_day(
    session: AsyncSession, days: int = 14
) -> list[tuple[str, str, Decimal]]:
    """Return (date, currency, sum(total_amount)) bucketed by paid_at."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    bucket = func.date(Order.paid_at).label("d")
    stmt = (
        select(bucket, Order.currency, func.sum(Order.total_amount))
        .where(
            Order.status.in_(_PAID_STATUSES),
            Order.paid_at.is_not(None),
            Order.paid_at >= since,
        )
        .group_by(bucket, Order.currency)
        .order_by(bucket.desc(), Order.currency)
    )
    return [
        (str(d), c, Decimal(s))
        for d, c, s in (await session.execute(stmt)).all()
    ]


async def top_products(
    session: AsyncSession, limit: int = 10, days: int = 30
) -> list[tuple[str, int, Decimal, str]]:
    """Top products by revenue: (title, qty_sold, revenue, currency)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(
            OrderItem.title_snapshot,
            func.sum(OrderItem.quantity),
            func.sum(OrderItem.unit_price * OrderItem.quantity),
            Order.currency,
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.status.in_(_PAID_STATUSES), Order.paid_at >= since)
        .group_by(OrderItem.title_snapshot, Order.currency)
        .order_by(func.sum(OrderItem.unit_price * OrderItem.quantity).desc())
        .limit(limit)
    )
    return [
        (t, int(q), Decimal(r), c)
        for t, q, r, c in (await session.execute(stmt)).all()
    ]


async def dau(session: AsyncSession) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    stmt = select(func.count(User.id)).where(User.last_seen_at >= since)
    return int((await session.execute(stmt)).scalar_one())


async def total_users(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count(User.id)))).scalar_one())


async def banned_users(session: AsyncSession) -> int:
    return int(
        (
            await session.execute(
                select(func.count(User.id)).where(User.is_banned.is_(True))
            )
        ).scalar_one()
    )
