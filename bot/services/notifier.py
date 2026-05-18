from __future__ import annotations

from typing import Iterable

from aiogram import Bot
from loguru import logger


class Notifier:
    """Pushes ops messages to admins and group chats."""

    def __init__(
        self,
        bot: Bot,
        *,
        admin_ids: Iterable[int],
        notify_group_id: int = 0,
    ) -> None:
        self._bot = bot
        self._admin_ids = list(admin_ids)
        self._group = notify_group_id

    async def notify_admins(self, text: str) -> None:
        for uid in self._admin_ids:
            try:
                await self._bot.send_message(uid, text)
            except Exception:
                logger.warning("failed to notify admin {}", uid)

    async def notify_group(self, text: str) -> None:
        if not self._group:
            return
        try:
            await self._bot.send_message(self._group, text)
        except Exception:
            logger.warning("failed to notify notify_group_id={}", self._group)

    async def announce_new_order(
        self, *, order_id: int, user_id: int, summary: str
    ) -> None:
        text = (
            f"🆕 <b>Заказ #{order_id}</b>\n"
            f"Пользователь: <code>{user_id}</code>\n\n"
            f"{summary}"
        )
        await self.notify_group(text)

    async def announce_manual(
        self, *, order_id: int, item_id: int, title: str, user_id: int
    ) -> None:
        text = (
            f"📨 Ручная выдача (заказ #{order_id} / позиция #{item_id})\n"
            f"Товар: <b>{title}</b>\n"
            f"Покупатель: <code>{user_id}</code>"
        )
        await self.notify_admins(text)
        await self.notify_group(text)
