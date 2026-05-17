from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.payments.base import PaymentProvider, PaymentStatus
from bot.payments.fulfillment import fulfill_paid_order
from bot.repositories.order import find_pending_by_external

if TYPE_CHECKING:
    from aiogram import Bot

    from bot.config import Settings
    from bot.payments.registry import PaymentRegistry


log = logging.getLogger(__name__)


def _make_handler(
    provider: PaymentProvider,
    sessionmaker: async_sessionmaker[AsyncSession],
    bot: "Bot",
    settings: "Settings",
):
    async def handler(request: web.Request) -> web.Response:
        body = await request.read()
        event = await provider.parse_webhook(dict(request.headers), body)
        if event is None:
            return web.Response(status=400, text="bad request")

        if event.status != PaymentStatus.PAID:
            return web.Response(status=200, text="ignored")

        async with sessionmaker() as session:
            order = await find_pending_by_external(
                session, provider.code, event.external_id
            )
            if order is None:
                # Either the order was already fulfilled (and the upstream
                # is retrying) or the external_id doesn't belong to us.
                # 200 either way so the provider stops retrying.
                log.info(
                    "webhook for %s/%s: no pending order",
                    provider.code,
                    event.external_id,
                )
                return web.Response(status=200, text="ignored")
            try:
                await fulfill_paid_order(session, bot, settings, order.id)
                await session.commit()
            except Exception:
                await session.rollback()
                log.exception(
                    "fulfillment failed for order %s via %s",
                    order.id,
                    provider.code,
                )
                return web.Response(status=500, text="error")
        return web.Response(status=200, text="ok")

    return handler


def build_webhook_app(
    registry: "PaymentRegistry",
    sessionmaker: async_sessionmaker[AsyncSession],
    bot: "Bot",
    settings: "Settings",
) -> web.Application:
    app = web.Application()
    for provider in registry.all():
        if not provider.supports_webhook:
            continue
        path = f"{settings.webhook_base_path.rstrip('/')}/{provider.code}"
        app.router.add_post(path, _make_handler(provider, sessionmaker, bot, settings))
        log.info("registered webhook route %s", path)
    return app


async def run_webhook_server(
    app: web.Application, host: str, port: int
) -> web.AppRunner:
    """Start the webhook HTTP server. Caller must ``await runner.cleanup()``
    on shutdown."""
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    log.info("webhook server listening on %s:%s", host, port)
    return runner
