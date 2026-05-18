from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.database.models import User
from bot.locales import DEFAULT_LOCALE, translate


class I18nMiddleware(BaseMiddleware):
    """Injects a ``t(key, **kwargs)`` callable bound to the user's locale."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("user")
        locale = user.locale if user else DEFAULT_LOCALE
        data["locale"] = locale
        data["t"] = partial(translate, locale=locale)
        return await handler(event, data)
