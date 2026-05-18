from __future__ import annotations

import asyncio
import signal
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from alembic import command
from alembic.config import Config as AlembicConfig
from loguru import logger
from redis.asyncio import Redis

from bot.config import Settings, get_settings
from bot.database.engine import build_engine, build_sessionmaker
from bot.handlers import register as register_handlers
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.i18n import I18nMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.middlewares.user_context import UserContextMiddleware
from bot.payments.registry import build_registry
from bot.services.broadcast import Broadcaster
from bot.services.cache import TTLCache
from bot.services.cart import CartService
from bot.services.catalog import CatalogService
from bot.services.notifier import Notifier
from bot.services.support import SupportService
from bot.utils.logging import configure_logging
from bot.webhook import build_webhook_app, run_webhook_server


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_migrations(database_url: str) -> None:
    """Run ``alembic upgrade head``. Must be called from a sync context —
    Alembic's online mode opens its own event loop in env.py."""
    cfg = AlembicConfig(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")


async def _build_storage(settings: Settings, redis: Redis | None):
    if redis is not None:
        return RedisStorage(redis=redis)
    return MemoryStorage()


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    engine = build_engine(settings.database_url)
    sessionmaker = build_sessionmaker(engine)

    redis: Redis | None = None
    if settings.redis_url:
        redis = Redis.from_url(settings.redis_url, decode_responses=False)
        try:
            await redis.ping()
        except Exception:
            logger.warning("Redis unavailable, falling back to in-memory")
            redis = None

    storage = await _build_storage(settings, redis)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    registry = build_registry(settings)
    notifier = Notifier(
        bot, admin_ids=settings.admin_ids, notify_group_id=settings.notify_group_id
    )
    cache = TTLCache(redis, default_ttl=settings.catalog_cache_ttl)
    catalog = CatalogService(cache)
    cart = CartService(redis, ttl=settings.cart_ttl_seconds)
    broadcaster = Broadcaster(bot, rate_per_sec=settings.broadcast_rate_per_sec)
    support = SupportService(bot=bot, group_id=settings.support_group_id, redis=redis)

    dp = Dispatcher(storage=storage)
    dp["settings"] = settings
    dp["registry"] = registry
    dp["notifier"] = notifier
    dp["catalog"] = catalog
    dp["cart"] = cart
    dp["broadcaster"] = broadcaster
    dp["support"] = support

    dp.update.middleware(ThrottlingMiddleware(rate=settings.throttle_rate))
    dp.update.middleware(DbSessionMiddleware(sessionmaker))
    dp.update.middleware(UserContextMiddleware())
    dp.update.middleware(I18nMiddleware())

    register_handlers(dp, settings)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    webhook_runner = None
    if settings.webhook_enabled:
        app = build_webhook_app(registry, sessionmaker, bot, notifier, settings)
        if app.router.routes():
            webhook_runner = await run_webhook_server(
                app, settings.webhook_host, settings.webhook_port
            )
        else:
            logger.info("webhook server skipped: no providers expose webhooks")

    logger.info("bot starting (providers: {})", [p.code for p in registry.all()])
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        polling = asyncio.create_task(
            dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
        )
        stop_task = asyncio.create_task(stop_event.wait())
        done, pending = await asyncio.wait(
            {polling, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        for task in done:
            exc = task.exception()
            if exc is not None:
                raise exc
    finally:
        if webhook_runner is not None:
            await webhook_runner.cleanup()
        await registry.aclose()
        await dp.storage.close()
        await bot.session.close()
        if redis is not None:
            await redis.aclose()
        await engine.dispose()
        logger.info("bot stopped cleanly")
