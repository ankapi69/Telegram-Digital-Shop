from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Category, Product
from bot.repositories import category as cat_repo
from bot.services.cache import TTLCache


class CatalogService:
    """Read-mostly catalog with TTL cache.

    The cache holds lightweight tuples so payloads stay JSON-serializable
    in Redis.
    """

    PREFIX_CATEGORIES = "cat:list:"
    PREFIX_PRODUCTS = "cat:prod:"

    def __init__(self, cache: TTLCache) -> None:
        self._cache = cache

    async def categories(
        self, session: AsyncSession, parent_id: int | None
    ) -> list[Category]:
        # Cache is bypassed here because aiogram handlers need ORM objects;
        # we keep the API and rely on the per-request session. The cache is
        # exposed for handlers that fetch trimmed projections (see below).
        return await cat_repo.list_children(session, parent_id, active_only=True)

    async def products_in(
        self, session: AsyncSession, category_id: int | None
    ) -> list[Product]:
        return await cat_repo.list_products_in(session, category_id, active_only=True)

    async def invalidate(self) -> None:
        await self._cache.invalidate_prefix(self.PREFIX_CATEGORIES)
        await self._cache.invalidate_prefix(self.PREFIX_PRODUCTS)
