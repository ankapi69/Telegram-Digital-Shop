from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from bot.database.models import UserRole
from bot.repositories.user import upsert_user


_ROLE_FROM_CONFIG = {
    "superadmin": UserRole.SUPERADMIN,
    "manager": UserRole.MANAGER,
    "support": UserRole.SUPPORT,
}


class UserContextMiddleware(BaseMiddleware):
    """Resolves the acting user, refreshes their row, blocks banned ones.

    Runs after :class:`DbSessionMiddleware` so ``session`` is available.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None or isinstance(event, Update) and event.poll is not None:
            return await handler(event, data)

        session = data.get("session")
        settings = data.get("settings")
        if session is None or settings is None:
            return await handler(event, data)

        role_str = settings.role_of(tg_user.id)
        role_hint = _ROLE_FROM_CONFIG.get(role_str, UserRole.USER)
        user = await upsert_user(
            session,
            user_id=tg_user.id,
            username=tg_user.username,
            full_name=tg_user.full_name,
            role_hint=role_hint,
        )
        data["user"] = user
        data["role"] = user.role

        if user.is_banned:
            # Silently drop everything from banned users.
            return None
        return await handler(event, data)
