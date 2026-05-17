from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message, TelegramObject


class AdminFilter(Filter):
    def __init__(self, admin_ids: set[int]) -> None:
        self._admin_ids = admin_ids

    async def __call__(self, event: TelegramObject) -> bool:
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user
        return bool(user and user.id in self._admin_ids)
