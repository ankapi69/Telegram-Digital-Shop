from __future__ import annotations

import time
from typing import Any

from redis.asyncio import Redis


class TTLCache:
    """Two-tier cache: tries Redis first, falls back to per-process memory.

    Suitable for hot catalog reads. Cache entries are JSON-encoded strings
    when stored in Redis, ``Any`` Python objects when stored in-process.
    """

    def __init__(self, redis: Redis | None, default_ttl: int = 60) -> None:
        self._redis = redis
        self._ttl = default_ttl
        self._mem: dict[str, tuple[float, Any]] = {}

    async def get(self, key: str) -> Any | None:
        now = time.monotonic()
        entry = self._mem.get(key)
        if entry is not None:
            expires_at, value = entry
            if expires_at > now:
                return value
            self._mem.pop(key, None)
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
        except Exception:
            return None
        if raw is None:
            return None
        import json
        try:
            return json.loads(raw)
        except ValueError:
            return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        ttl = ttl or self._ttl
        self._mem[key] = (time.monotonic() + ttl, value)
        if self._redis is None:
            return
        try:
            import json
            await self._redis.set(key, json.dumps(value, default=str), ex=ttl)
        except Exception:
            pass

    async def invalidate(self, *keys: str) -> None:
        for k in keys:
            self._mem.pop(k, None)
        if self._redis is not None:
            try:
                await self._redis.delete(*keys)
            except Exception:
                pass

    async def invalidate_prefix(self, prefix: str) -> None:
        for k in list(self._mem):
            if k.startswith(prefix):
                self._mem.pop(k, None)
        if self._redis is None:
            return
        try:
            async for k in self._redis.scan_iter(match=f"{prefix}*"):
                await self._redis.delete(k)
        except Exception:
            pass
