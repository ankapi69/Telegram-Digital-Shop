from __future__ import annotations

import asyncio
import logging
import signal

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage

from bot.config import Settings, get_settings
from bot.database.engine import build_engine, build_sessionmaker
from bot.database.models import Base
from bot.handlers import register as register_handlers
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.payments.registry import build_registry
from bot.utils.logging import configure_logging
from bot.webhook import build_webhook_app, run_webhook_server

log = logging.getLogger(__name__)


async def _build_storage(settings: Settings):
    if settings.redis_url:
        return RedisStorage.from_url(settings.redis_url)
    return MemoryStorage()


async def _init_schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    engine = build_engine(settings.database_url)
    await _init_schema(engine)
    sessionmaker = build_sessionmaker(engine)

    storage = await _build_storage(settings)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    registry = build_registry(settings)

    dp = Dispatcher(storage=storage)
    dp["settings"] = settings
    dp["registry"] = registry

    dp.update.middleware(ThrottlingMiddleware(rate=settings.throttle_rate))
    dp.update.middleware(DbSessionMiddleware(sessionmaker))

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
        app = build_webhook_app(registry, sessionmaker, bot, settings)
        if app.router.routes():
            webhook_runner = await run_webhook_server(
                app, settings.webhook_host, settings.webhook_port
            )
        else:
            log.info("webhook server skipped: no providers expose webhooks")

    log.info("Bot is starting (providers: %s)", [p.code for p in registry.all()])
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
        await engine.dispose()
        log.info("Bot stopped cleanly")
