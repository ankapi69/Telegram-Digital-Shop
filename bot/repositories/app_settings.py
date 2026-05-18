from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import AppSetting


async def get(session: AsyncSession, key: str) -> str | None:
    row = await session.get(AppSetting, key)
    return row.value if row else None


async def set(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(AppSetting, key)
    if row is None:
        session.add(AppSetting(key=key, value=value))
    else:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)
    await session.flush()


async def delete(session: AsyncSession, key: str) -> None:
    row = await session.get(AppSetting, key)
    if row is not None:
        await session.delete(row)
