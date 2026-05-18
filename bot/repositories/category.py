from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Category, Product


async def create_category(
    session: AsyncSession, *, name: str, parent_id: int | None
) -> Category:
    category = Category(name=name, parent_id=parent_id)
    session.add(category)
    await session.flush()
    return category


async def get_category(session: AsyncSession, category_id: int) -> Category | None:
    return await session.get(Category, category_id)


async def list_children(
    session: AsyncSession, parent_id: int | None, active_only: bool = True
) -> list[Category]:
    stmt = select(Category).where(
        Category.parent_id.is_(parent_id) if parent_id is None
        else Category.parent_id == parent_id
    )
    if active_only:
        stmt = stmt.where(Category.is_active.is_(True))
    stmt = stmt.order_by(Category.sort_order, Category.id)
    return list((await session.execute(stmt)).scalars().all())


async def list_all(session: AsyncSession) -> list[Category]:
    stmt = select(Category).order_by(Category.parent_id.nullsfirst(), Category.sort_order, Category.id)
    return list((await session.execute(stmt)).scalars().all())


async def list_products_in(
    session: AsyncSession, category_id: int | None, active_only: bool = True
) -> list[Product]:
    stmt = select(Product).where(
        Product.category_id.is_(category_id) if category_id is None
        else Product.category_id == category_id
    )
    if active_only:
        stmt = stmt.where(Product.is_active.is_(True))
    stmt = stmt.order_by(Product.id)
    return list((await session.execute(stmt)).scalars().all())


async def has_descendants(session: AsyncSession, category_id: int) -> bool:
    stmt = select(func.count(Category.id)).where(Category.parent_id == category_id)
    return bool((await session.execute(stmt)).scalar_one())


async def update_category(
    session: AsyncSession, category_id: int, **fields: object
) -> Category | None:
    cat = await session.get(Category, category_id)
    if cat is None:
        return None
    for key, value in fields.items():
        if hasattr(cat, key):
            setattr(cat, key, value)
    return cat


async def delete_category(session: AsyncSession, category_id: int) -> bool:
    cat = await session.get(Category, category_id)
    if cat is None:
        return False
    await session.delete(cat)
    return True
