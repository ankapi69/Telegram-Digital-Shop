from __future__ import annotations

import json
from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import Message
from loguru import logger
from redis.asyncio import Redis


@dataclass(slots=True)
class SupportService:
    """Bridges user messages to a support group chat.

    Each user message is forwarded into the group. We remember
    ``forwarded_message_id → user_id`` in Redis so an admin replying to
    the forwarded message lets us forward their reply back to the original
    user.
    """

    bot: Bot
    group_id: int
    redis: Redis | None
    ttl: int = 7 * 86_400

    @property
    def enabled(self) -> bool:
        return bool(self.group_id)

    def _key(self, message_id: int) -> str:
        return f"sup:fwd:{self.group_id}:{message_id}"

    async def forward_from_user(self, message: Message) -> bool:
        if not self.enabled:
            return False
        user = message.from_user
        if user is None:
            return False
        try:
            forwarded = await self.bot.forward_message(
                chat_id=self.group_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
        except Exception:
            logger.exception("support forward failed")
            return False

        header = (
            f"👤 <code>{user.id}</code> "
            f"@{user.username or '—'} ({user.full_name})"
        )
        try:
            await self.bot.send_message(
                self.group_id, header, reply_to_message_id=forwarded.message_id
            )
        except Exception:
            pass

        if self.redis is not None:
            try:
                await self.redis.set(
                    self._key(forwarded.message_id),
                    json.dumps({"user_id": user.id}),
                    ex=self.ttl,
                )
            except Exception:
                pass
        return True

    async def reply_back(self, group_msg: Message) -> bool:
        """Called when an admin replies to a forwarded message in the group."""
        if not self.enabled or self.redis is None or group_msg.reply_to_message is None:
            return False
        key = self._key(group_msg.reply_to_message.message_id)
        try:
            raw = await self.redis.get(key)
        except Exception:
            return False
        if not raw:
            return False
        try:
            data = json.loads(raw)
            user_id = int(data["user_id"])
        except (ValueError, KeyError, TypeError):
            return False
        try:
            await self.bot.copy_message(
                chat_id=user_id,
                from_chat_id=group_msg.chat.id,
                message_id=group_msg.message_id,
            )
            return True
        except Exception:
            logger.exception("support reply failed (user={})", user_id)
            return False
