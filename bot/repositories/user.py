from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User


async def upsert_user(
    session: AsyncSession,
    user_id: int,
    username: str | None,
    full_name: str | None,
) -> User:
    """Insert a user row if missing, otherwise refresh profile fields.

    Two concurrent /start calls from the same user could race, but the
    worst case is a duplicate insert that violates the primary key — the
    surrounding session commit then rolls back and the next call wins.
    Acceptable for this domain.
    """
    user = await session.get(User, user_id)
    if user is None:
        user = User(id=user_id, username=username, full_name=full_name)
        session.add(user)
        await session.flush()
        return user
    user.username = username
    user.full_name = full_name
    return user
