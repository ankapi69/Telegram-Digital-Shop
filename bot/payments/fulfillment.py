from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import DeliveryType, Order, OrderStatus, Product
from bot.repositories.stock import reserve_one

if TYPE_CHECKING:
    from aiogram import Bot

    from bot.config import Settings


log = logging.getLogger(__name__)


class FulfillResult:
    __slots__ = ("delivered", "awaiting", "already_done")

    def __init__(self, *, delivered: bool, awaiting: bool, already_done: bool) -> None:
        self.delivered = delivered
        self.awaiting = awaiting
        self.already_done = already_done


async def fulfill_paid_order(
    session: AsyncSession,
    bot: "Bot",
    settings: "Settings",
    order_id: int,
) -> FulfillResult:
    """Idempotently transition ``PENDING_PAYMENT`` → delivered or awaiting.

    Concurrent callers (e.g. webhook + manual "check payment" button at
    the same time) race on a compare-and-swap UPDATE: only the writer
    that flips the status from ``PENDING_PAYMENT`` proceeds.  All others
    short-circuit with ``already_done=True``.
    """
    claim = await session.execute(
        update(Order)
        .where(
            Order.id == order_id,
            Order.status == OrderStatus.PENDING_PAYMENT,
        )
        .values(status=OrderStatus.AWAITING_DELIVERY)
        .execution_options(synchronize_session=False)
    )
    if claim.rowcount != 1:
        log.info("order %s already fulfilled, skipping", order_id)
        return FulfillResult(delivered=False, awaiting=False, already_done=True)

    order = await session.get(Order, order_id)
    assert order is not None
    product = await session.get(Product, order.product_id)
    if product is None:
        log.error("order %s references missing product %s", order_id, order.product_id)
        return FulfillResult(delivered=False, awaiting=True, already_done=False)

    if product.delivery_type == DeliveryType.AUTO:
        item = await reserve_one(session, product.id, order.id)
        if item is None:
            await _notify_admins(
                bot,
                settings,
                f"⚠️ Заказ #{order.id}: оплата прошла, но товар «{product.title}» "
                f"кончился. Нужен возврат или ручная выдача.",
            )
            try:
                await bot.send_message(
                    order.user_id,
                    "⚠️ Оплата получена, но товар закончился прямо перед "
                    "выдачей. Администратор свяжется с вами.",
                )
            except Exception:
                log.warning(
                    "Failed to notify user %s about out-of-stock", order.user_id
                )
            return FulfillResult(delivered=False, awaiting=True, already_done=False)

        order.status = OrderStatus.DELIVERED
        order.delivered_content = item.content
        order.delivered_at = datetime.now(timezone.utc)
        try:
            await bot.send_message(
                order.user_id,
                "✅ Оплата получена!\n\n"
                f"Ваш товар «{product.title}»:\n"
                f"<code>{item.content}</code>",
            )
        except Exception:
            log.exception(
                "Failed to deliver auto product to user %s", order.user_id
            )
        return FulfillResult(delivered=True, awaiting=False, already_done=False)

    # MANUAL delivery — leave the order in AWAITING_DELIVERY for admin.
    try:
        await bot.send_message(
            order.user_id,
            "✅ Оплата получена!\n\n"
            f"Товар «{product.title}» выдаётся вручную. "
            "Администратор пришлёт его в ближайшее время.",
        )
    except Exception:
        log.warning(
            "Failed to notify user %s about manual fulfillment", order.user_id
        )
    await _notify_admins(
        bot,
        settings,
        f"📨 Новый ручной заказ #{order.id}\n"
        f"Товар: {product.title}\n"
        f"Покупатель: <code>{order.user_id}</code>",
    )
    return FulfillResult(delivered=False, awaiting=True, already_done=False)


async def _notify_admins(bot: "Bot", settings: "Settings", text: str) -> None:
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            log.warning("Failed to notify admin %s", admin_id, exc_info=True)
