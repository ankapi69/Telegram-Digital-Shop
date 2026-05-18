from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import StockItem


async def add_stock_items(
    session: AsyncSession, product_id: int, contents: list[str]
) -> int:
    items = [StockItem(product_id=product_id, content=line) for line in contents]
    session.add_all(items)
    await session.flush()
    return len(items)


async def reserve_one(
    session: AsyncSession, product_id: int, order_item_id: int
) -> StockItem | None:
    """Atomically claim one unsold stock row for the given order item.

    Compare-and-swap UPDATE — safe on SQLite and Postgres alike.
    """
    for _ in range(32):
        pick = (
            select(StockItem.id)
            .where(
                StockItem.product_id == product_id,
                StockItem.is_sold.is_(False),
            )
            .order_by(StockItem.id)
            .limit(1)
        )
        candidate_id = (await session.execute(pick)).scalar_one_or_none()
        if candidate_id is None:
            return None
        claim = (
            update(StockItem)
            .where(
                StockItem.id == candidate_id,
                StockItem.is_sold.is_(False),
            )
            .values(is_sold=True, order_item_id=order_item_id)
            .execution_options(synchronize_session=False)
        )
        result = await session.execute(claim)
        if result.rowcount == 1:
            await session.flush()
            return await session.get(StockItem, candidate_id)
    return None
