from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.database.models import UserRole


_ROLE_RANK = {
    UserRole.USER: 0,
    UserRole.SUPPORT: 1,
    UserRole.MANAGER: 2,
    UserRole.SUPERADMIN: 3,
}


def _user_role(data_role: UserRole | None, ids_role: UserRole) -> UserRole:
    """Pick the stronger role between DB row and config-derived hint."""
    if data_role is None:
        return ids_role
    return data_role if _ROLE_RANK[data_role] >= _ROLE_RANK[ids_role] else ids_role


class RoleFilter(Filter):
    """Pass when the actor has at least ``min_role``.

    Reads ``role`` from middleware data (set by ``UserContextMiddleware``)
    so ban/role changes take effect without restart.
    """

    def __init__(self, min_role: UserRole) -> None:
        self._min = _ROLE_RANK[min_role]

    async def __call__(
        self, event: TelegramObject, role: UserRole | None = None, **_: object
    ) -> bool:
        if role is None:
            return False
        return _ROLE_RANK.get(role, -1) >= self._min


AdminFilter = lambda: RoleFilter(UserRole.SUPPORT)      # any staff
ManagerFilter = lambda: RoleFilter(UserRole.MANAGER)    # manager+
SuperadminFilter = lambda: RoleFilter(UserRole.SUPERADMIN)


class SupportGroupFilter(Filter):
    """Match only messages coming from the configured support group chat."""

    def __init__(self, group_id: int) -> None:
        self._group_id = group_id

    async def __call__(self, event: TelegramObject) -> bool:
        if not self._group_id:
            return False
        if isinstance(event, Message):
            return event.chat.id == self._group_id
        if isinstance(event, CallbackQuery) and event.message is not None:
            return event.message.chat.id == self._group_id
        return False
