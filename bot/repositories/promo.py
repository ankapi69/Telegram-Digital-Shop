from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Promo


async def get_by_code(session: AsyncSession, code: str) -> Promo | None:
    stmt = select(Promo).where(Promo.code == code.strip().upper())
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_all(session: AsyncSession) -> list[Promo]:
    return list((await session.execute(select(Promo).order_by(Promo.id))).scalars().all())


async def create_promo(session: AsyncSession, **fields: object) -> Promo:
    promo = Promo(**fields)
    session.add(promo)
    await session.flush()
    return promo


async def delete_promo(session: AsyncSession, promo_id: int) -> bool:
    promo = await session.get(Promo, promo_id)
    if promo is None:
        return False
    await session.delete(promo)
    return True


def is_usable(promo: Promo) -> bool:
    if not promo.is_active:
        return False
    if promo.expires_at is not None and promo.expires_at < datetime.now(timezone.utc):
        return False
    if promo.max_uses is not None and promo.used_count >= promo.max_uses:
        return False
    return True


async def increment_use(session: AsyncSession, code: str) -> None:
    promo = await get_by_code(session, code)
    if promo is None:
        return
    promo.used_count += 1
