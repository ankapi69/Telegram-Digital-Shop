from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import (
    Order,
    OrderItem,
    OrderItemStatus,
    OrderKind,
    OrderStatus,
    Product,
)


async def create_order(
    session: AsyncSession,
    *,
    user_id: int,
    provider: str,
    currency: str,
    subtotal: Decimal,
    discount: Decimal,
    total: Decimal,
    promo_code: str | None,
    items: Iterable[tuple[Product, int, Decimal]],
    kind: OrderKind = OrderKind.PURCHASE,
) -> Order:
    order = Order(
        user_id=user_id,
        provider=provider,
        currency=currency,
        subtotal_amount=subtotal,
        discount_amount=discount,
        total_amount=total,
        promo_code=promo_code,
        status=OrderStatus.PENDING_PAYMENT,
        kind=kind,
    )
    for product, qty, unit_price in items:
        order.items.append(
            OrderItem(
                product_id=product.id,
                title_snapshot=product.title,
                quantity=qty,
                unit_price=unit_price,
            )
        )
    session.add(order)
    await session.flush()
    return order


async def create_topup_order(
    session: AsyncSession,
    *,
    user_id: int,
    provider: str,
    currency: str,
    amount: Decimal,
) -> Order:
    order = Order(
        user_id=user_id,
        provider=provider,
        currency=currency,
        subtotal_amount=amount,
        discount_amount=Decimal("0"),
        total_amount=amount,
        promo_code=None,
        status=OrderStatus.PENDING_PAYMENT,
        kind=OrderKind.TOPUP,
    )
    session.add(order)
    await session.flush()
    return order


async def get_order(session: AsyncSession, order_id: int) -> Order | None:
    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items))
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def find_pending_by_external(
    session: AsyncSession, provider: str, external_id: str
) -> Order | None:
    stmt = (
        select(Order)
        .where(Order.provider == provider, Order.external_id == external_id)
        .options(selectinload(Order.items))
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_user_orders_page(
    session: AsyncSession, user_id: int, page: int, per_page: int = 5
) -> tuple[list[Order], int]:
    total = int(
        (
            await session.execute(
                select(func.count(Order.id)).where(Order.user_id == user_id)
            )
        ).scalar_one()
    )
    stmt = (
        select(Order)
        .where(Order.user_id == user_id)
        .options(selectinload(Order.items))
        .order_by(Order.id.desc())
        .offset(max(0, page - 1) * per_page)
        .limit(per_page)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return rows, total


async def list_pending_manual_items(session: AsyncSession) -> list[OrderItem]:
    """Items that have been paid for but still need manual delivery."""
    stmt = (
        select(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            OrderItem.status == OrderItemStatus.PENDING,
            Order.status == OrderStatus.AWAITING_DELIVERY,
        )
        .order_by(OrderItem.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_order_item(session: AsyncSession, item_id: int) -> OrderItem | None:
    return await session.get(OrderItem, item_id)


async def set_invoice_data(
    session: AsyncSession,
    order: Order,
    external_id: str,
    payment_url: str | None,
) -> None:
    order.external_id = external_id
    order.payment_url = payment_url
    await session.flush()


async def mark_item_delivered(
    session: AsyncSession, item: OrderItem, content: str
) -> None:
    item.status = OrderItemStatus.DELIVERED
    item.delivered_content = content
    item.delivered_at = datetime.now(timezone.utc)


async def refresh_order_state(session: AsyncSession, order: Order) -> None:
    """Roll up item statuses into the parent Order status."""
    pending = [i for i in order.items if i.status != OrderItemStatus.DELIVERED]
    if not pending:
        order.status = OrderStatus.DELIVERED
        order.delivered_at = datetime.now(timezone.utc)
    else:
        order.status = OrderStatus.AWAITING_DELIVERY
