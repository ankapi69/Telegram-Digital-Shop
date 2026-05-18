from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Iterable

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup
from loguru import logger


@dataclass(slots=True)
class BroadcastResult:
    sent: int
    failed: int


class Broadcaster:
    """Sends a message to many users at a bounded rate.

    Telegram's hard limit is 30 msg/sec globally — we stay below that and
    back off on ``Too Many Requests``.
    """

    def __init__(self, bot: Bot, rate_per_sec: int = 25) -> None:
        self._bot = bot
        self._rate = max(1, rate_per_sec)

    async def broadcast_text(
        self,
        user_ids: Iterable[int],
        text: str,
        photo_file_id: str | None = None,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> BroadcastResult:
        sent = 0
        failed = 0
        delay = 1.0 / self._rate
        for uid in user_ids:
            try:
                if photo_file_id:
                    await self._bot.send_photo(
                        uid, photo_file_id, caption=text, reply_markup=reply_markup
                    )
                else:
                    await self._bot.send_message(
                        uid, text, reply_markup=reply_markup, disable_web_page_preview=True
                    )
                sent += 1
            except TelegramRetryAfter as e:
                logger.warning("broadcast retry-after {}s", e.retry_after)
                await asyncio.sleep(float(e.retry_after))
                # retry once
                try:
                    if photo_file_id:
                        await self._bot.send_photo(
                            uid, photo_file_id, caption=text, reply_markup=reply_markup
                        )
                    else:
                        await self._bot.send_message(
                            uid, text, reply_markup=reply_markup
                        )
                    sent += 1
                except Exception:
                    failed += 1
            except Exception:
                failed += 1
            await asyncio.sleep(delay)
        return BroadcastResult(sent=sent, failed=failed)
