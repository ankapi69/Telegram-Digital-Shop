from __future__ import annotations

import json
from dataclasses import dataclass

from redis.asyncio import Redis


@dataclass(slots=True)
class CartLine:
    product_id: int
    quantity: int


class CartService:
    """Per-user cart stored in Redis (with TTL) or in-process as fallback."""

    MAX_LINES = 20
    MAX_QTY = 99

    def __init__(self, redis: Redis | None, ttl: int = 86_400) -> None:
        self._redis = redis
        self._ttl = ttl
        self._fallback: dict[int, dict[int, int]] = {}
        self._fallback_promo: dict[int, str] = {}

    def _key(self, user_id: int) -> str:
        return f"cart:{user_id}"

    def _promo_key(self, user_id: int) -> str:
        return f"cart:{user_id}:promo"

    # ---- low-level storage ----------------------------------------------

    async def _load(self, user_id: int) -> dict[int, int]:
        if self._redis is None:
            return dict(self._fallback.get(user_id, {}))
        try:
            raw = await self._redis.get(self._key(user_id))
        except Exception:
            return dict(self._fallback.get(user_id, {}))
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return {int(k): int(v) for k, v in data.items()}
        except (ValueError, TypeError):
            return {}

    async def _save(self, user_id: int, contents: dict[int, int]) -> None:
        if not contents:
            await self.clear(user_id)
            return
        payload = json.dumps({str(k): v for k, v in contents.items()})
        if self._redis is None:
            self._fallback[user_id] = dict(contents)
            return
        try:
            await self._redis.set(self._key(user_id), payload, ex=self._ttl)
        except Exception:
            self._fallback[user_id] = dict(contents)

    # ---- public API ------------------------------------------------------

    async def get(self, user_id: int) -> list[CartLine]:
        contents = await self._load(user_id)
        return [CartLine(product_id=pid, quantity=qty) for pid, qty in contents.items() if qty > 0]

    async def add(self, user_id: int, product_id: int, delta: int = 1) -> int:
        contents = await self._load(user_id)
        if product_id not in contents and len(contents) >= self.MAX_LINES:
            raise ValueError("cart limit reached")
        new_qty = max(0, min(self.MAX_QTY, contents.get(product_id, 0) + delta))
        if new_qty == 0:
            contents.pop(product_id, None)
        else:
            contents[product_id] = new_qty
        await self._save(user_id, contents)
        return new_qty

    async def remove(self, user_id: int, product_id: int) -> None:
        contents = await self._load(user_id)
        contents.pop(product_id, None)
        await self._save(user_id, contents)

    async def clear(self, user_id: int) -> None:
        if self._redis is None:
            self._fallback.pop(user_id, None)
            self._fallback_promo.pop(user_id, None)
            return
        try:
            await self._redis.delete(self._key(user_id), self._promo_key(user_id))
        except Exception:
            self._fallback.pop(user_id, None)
            self._fallback_promo.pop(user_id, None)

    async def set_promo(self, user_id: int, code: str | None) -> None:
        if self._redis is None:
            if code is None:
                self._fallback_promo.pop(user_id, None)
            else:
                self._fallback_promo[user_id] = code
            return
        try:
            if code is None:
                await self._redis.delete(self._promo_key(user_id))
            else:
                await self._redis.set(self._promo_key(user_id), code, ex=self._ttl)
        except Exception:
            pass

    async def get_promo(self, user_id: int) -> str | None:
        if self._redis is None:
            return self._fallback_promo.get(user_id)
        try:
            raw = await self._redis.get(self._promo_key(user_id))
        except Exception:
            return self._fallback_promo.get(user_id)
        if raw is None:
            return None
        return raw.decode() if isinstance(raw, bytes) else str(raw)
