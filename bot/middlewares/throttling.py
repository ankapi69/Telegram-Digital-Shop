import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update


def _user_id_from_update(update: Update) -> int | None:
    for event in (
        update.message,
        update.edited_message,
        update.channel_post,
        update.edited_channel_post,
        update.callback_query,
        update.inline_query,
        update.chosen_inline_result,
        update.shipping_query,
        update.pre_checkout_query,
        update.poll_answer,
        update.my_chat_member,
        update.chat_member,
        update.chat_join_request,
    ):
        if event is None:
            continue
        user = getattr(event, "from_user", None)
        if user is not None:
            return user.id
    return None


class ThrottlingMiddleware(BaseMiddleware):
    """In-memory per-user rate limit. Silently drops too-fast updates.

    Suitable for a single worker. For horizontal scaling switch to a Redis
    based limiter (token bucket / leaky bucket on the same Redis used for
    FSM storage).
    """

    def __init__(self, rate: float = 0.5, capacity: int = 100_000) -> None:
        self._rate = rate
        self._capacity = capacity
        self._last_seen: OrderedDict[int, float] = OrderedDict()

    def _hit(self, user_id: int) -> bool:
        now = time.monotonic()
        last = self._last_seen.get(user_id)
        self._last_seen[user_id] = now
        self._last_seen.move_to_end(user_id)
        if len(self._last_seen) > self._capacity:
            self._last_seen.popitem(last=False)
        return last is not None and (now - last) < self._rate

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id: int | None = None
        if isinstance(event, Update):
            user_id = _user_id_from_update(event)
        if user_id is not None and self._hit(user_id):
            return None
        return await handler(event, data)
