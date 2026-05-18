from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User, UserRole


async def upsert_user(
    session: AsyncSession,
    user_id: int,
    username: str | None,
    full_name: str | None,
    role_hint: UserRole = UserRole.USER,
) -> User:
    user = await session.get(User, user_id)
    now = datetime.now(timezone.utc)
    if user is None:
        user = User(
            id=user_id,
            username=username,
            full_name=full_name,
            role=role_hint,
            last_seen_at=now,
        )
        session.add(user)
        await session.flush()
        return user
    user.username = username
    user.full_name = full_name
    user.last_seen_at = now
    # Promote role only if config grants a stronger one; never demote here.
    if _role_rank(role_hint) > _role_rank(user.role):
        user.role = role_hint
    return user


def _role_rank(role: UserRole) -> int:
    return {
        UserRole.USER: 0,
        UserRole.SUPPORT: 1,
        UserRole.MANAGER: 2,
        UserRole.SUPERADMIN: 3,
    }[role]


async def set_banned(session: AsyncSession, user_id: int, banned: bool) -> User | None:
    user = await session.get(User, user_id)
    if user is None:
        return None
    user.is_banned = banned
    return user


async def list_recent_users(session: AsyncSession, limit: int = 50) -> list[User]:
    stmt = select(User).order_by(User.last_seen_at.desc().nullslast()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def find_user(session: AsyncSession, query: str) -> User | None:
    """Lookup by numeric id or by exact @username (case-insensitive)."""
    query = query.strip().lstrip("@")
    if query.isdigit():
        return await session.get(User, int(query))
    stmt = select(User).where(User.username.ilike(query)).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()
