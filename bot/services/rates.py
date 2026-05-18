from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import aiohttp
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.repositories import app_settings as settings_repo


COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=tether&vs_currencies=rub"
)

KEY_LIVE_RATE = "rub_per_usd_live"
KEY_LIVE_AT = "rub_per_usd_live_at"
KEY_PINNED_RATE = "rub_per_usd_pinned"


@dataclass(slots=True)
class RateInfo:
    rate: Decimal       # final effective rate (markup applied for live)
    pinned: bool
    source_rate: Decimal | None
    updated_at: datetime | None


class RatesService:
    """USDT/RUB rate provider. Picks pinned override, else live + markup."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        *,
        markup_pct: float,
        fallback: float,
        refresh_interval: int,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._markup = Decimal(str(markup_pct))
        self._fallback = Decimal(str(fallback))
        self._interval = max(60, refresh_interval)
        self._task: asyncio.Task[None] | None = None
        self._http: aiohttp.ClientSession | None = None

    # ---- public ----------------------------------------------------------

    async def get(self) -> RateInfo:
        async with self._sessionmaker() as session:
            return await self._read(session)

    async def get_rub_per_usd(self) -> Decimal:
        return (await self.get()).rate

    async def pin(self, rate: Decimal) -> None:
        async with self._sessionmaker() as session:
            await settings_repo.set(session, KEY_PINNED_RATE, str(rate))
            await session.commit()

    async def unpin(self) -> None:
        async with self._sessionmaker() as session:
            await settings_repo.delete(session, KEY_PINNED_RATE)
            await session.commit()

    async def refresh_once(self) -> Decimal | None:
        try:
            session = self._client()
            async with session.get(COINGECKO_URL, timeout=aiohttp.ClientTimeout(total=10)) as r:
                data = await r.json(content_type=None)
            rate = Decimal(str(data["tether"]["rub"]))
        except Exception:
            logger.warning("CoinGecko refresh failed", exc_info=True)
            return None
        async with self._sessionmaker() as s:
            await settings_repo.set(s, KEY_LIVE_RATE, str(rate))
            await settings_repo.set(
                s, KEY_LIVE_AT, datetime.now(timezone.utc).isoformat()
            )
            await s.commit()
        logger.info("USDT/RUB live rate refreshed: {}", rate)
        return rate

    # ---- lifecycle -------------------------------------------------------

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        if self._http is not None:
            await self._http.close()
            self._http = None

    # ---- internals -------------------------------------------------------

    def _client(self) -> aiohttp.ClientSession:
        if self._http is None or self._http.closed:
            self._http = aiohttp.ClientSession()
        return self._http

    async def _read(self, session: AsyncSession) -> RateInfo:
        pinned_raw = await settings_repo.get(session, KEY_PINNED_RATE)
        if pinned_raw is not None:
            return RateInfo(
                rate=Decimal(pinned_raw),
                pinned=True,
                source_rate=Decimal(pinned_raw),
                updated_at=None,
            )
        live_raw = await settings_repo.get(session, KEY_LIVE_RATE)
        live_at_raw = await settings_repo.get(session, KEY_LIVE_AT)
        if live_raw is None:
            return RateInfo(
                rate=self._fallback * (Decimal(1) + self._markup / Decimal(100)),
                pinned=False,
                source_rate=self._fallback,
                updated_at=None,
            )
        source = Decimal(live_raw)
        rate = source * (Decimal(1) + self._markup / Decimal(100))
        updated_at = (
            datetime.fromisoformat(live_at_raw) if live_at_raw else None
        )
        return RateInfo(
            rate=rate.quantize(Decimal("0.01")),
            pinned=False,
            source_rate=source,
            updated_at=updated_at,
        )

    async def _loop(self) -> None:
        # initial refresh on startup (don't block)
        await self.refresh_once()
        while True:
            try:
                await asyncio.sleep(self._interval)
                await self.refresh_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("rates loop iteration failed")
