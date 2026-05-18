from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.database.models import (
    DeliveryType,
    LedgerKind,
    Order,
    OrderItem,
    OrderItemStatus,
    OrderKind,
    OrderStatus,
    Product,
)
from bot.locales import translate as t
from bot.repositories import promo as promo_repo
from bot.repositories import wallet as wallet_repo
from bot.repositories.stock import reserve_one
from bot.utils.money import fmt_amount

if TYPE_CHECKING:
    from aiogram import Bot

    from bot.services.notifier import Notifier


class FulfillResult:
    __slots__ = ("delivered_items", "pending_items", "already_done")

    def __init__(self, *, delivered: int, pending: int, already_done: bool) -> None:
        self.delivered_items = delivered
        self.pending_items = pending
        self.already_done = already_done

    @property
    def delivered(self) -> bool:
        return self.delivered_items > 0 and self.pending_items == 0

    @property
    def awaiting(self) -> bool:
        return self.pending_items > 0


async def fulfill_paid_order(
    session: AsyncSession,
    bot: "Bot",
    notifier: "Notifier",
    order_id: int,
) -> FulfillResult:
    """Idempotently process a paid order: deliver auto items, queue manual ones.

    Uses compare-and-swap on Order.status to make sure only one writer
    progresses a given order out of ``PENDING_PAYMENT``.
    """
    claim = await session.execute(
        update(Order)
        .where(Order.id == order_id, Order.status == OrderStatus.PENDING_PAYMENT)
        .values(status=OrderStatus.AWAITING_DELIVERY, paid_at=datetime.now(timezone.utc))
        .execution_options(synchronize_session=False)
    )
    if claim.rowcount != 1:
        return FulfillResult(delivered=0, pending=0, already_done=True)

    stmt = select(Order).where(Order.id == order_id).options(selectinload(Order.items))
    order = (await session.execute(stmt)).scalar_one()

    # TOP-UP orders: credit wallet (in USD), mark delivered, notify user.
    if order.kind == OrderKind.TOPUP:
        credit_usd = order.credited_amount or order.total_amount
        await wallet_repo.credit(
            session,
            user_id=order.user_id,
            amount=credit_usd,
            kind=LedgerKind.TOPUP,
            ref_order_id=order.id,
            comment=f"topup via {order.provider}",
        )
        order.status = OrderStatus.DELIVERED
        order.delivered_at = datetime.now(timezone.utc)
        try:
            new_balance = await wallet_repo.get_balance(session, order.user_id)
            await bot.send_message(
                order.user_id,
                "✅ Баланс пополнен на "
                f"<b>{fmt_amount(credit_usd, 'USD')}</b>.\n"
                f"Текущий баланс: <b>{fmt_amount(new_balance, 'USD')}</b>",
            )
        except Exception:
            logger.exception("topup notify failed for order {}", order.id)
        return FulfillResult(delivered=1, pending=0, already_done=False)

    if order.promo_code:
        await promo_repo.increment_use(session, order.promo_code)

    delivered_lines: list[str] = []
    pending_titles: list[tuple[OrderItem, str]] = []
    for item in order.items:
        product = await session.get(Product, item.product_id)
        if product is None:
            continue
        # Multi-quantity auto: reserve one stock unit per quantity, concat.
        if product.delivery_type == DeliveryType.AUTO:
            contents: list[str] = []
            for _ in range(item.quantity):
                reserved = await reserve_one(session, product.id, item.id)
                if reserved is None:
                    break
                contents.append(reserved.content)
            if len(contents) == item.quantity:
                item.delivered_content = "\n".join(contents)
                item.status = OrderItemStatus.DELIVERED
                item.delivered_at = datetime.now(timezone.utc)
                delivered_lines.append(f"<b>{item.title_snapshot}</b> ×{item.quantity}\n<code>{item.delivered_content}</code>")
            else:
                pending_titles.append((item, product.title))
        else:
            if product.manual_template:
                item.delivered_content = product.manual_template
                item.status = OrderItemStatus.DELIVERED
                item.delivered_at = datetime.now(timezone.utc)
                delivered_lines.append(
                    f"<b>{item.title_snapshot}</b>\n<code>{product.manual_template}</code>"
                )
            else:
                pending_titles.append((item, product.title))

    # Roll up order state.
    if not any(i.status != OrderItemStatus.DELIVERED for i in order.items):
        order.status = OrderStatus.DELIVERED
        order.delivered_at = datetime.now(timezone.utc)
    else:
        order.status = OrderStatus.AWAITING_DELIVERY

    # Send messages.
    if delivered_lines:
        try:
            await bot.send_message(
                order.user_id,
                "✅ <b>Оплата получена</b>\n\n" + "\n\n".join(delivered_lines),
            )
        except Exception:
            logger.exception("failed to deliver order {}", order.id)

    if pending_titles:
        names = ", ".join(title for _, title in pending_titles)
        try:
            await bot.send_message(
                order.user_id,
                f"✅ Оплата получена.\n\nТовары «{names}» выдаются вручную, "
                "администратор пришлёт их в этот чат.",
            )
        except Exception:
            logger.warning("failed to notify user {} about manual", order.user_id)
        for item, title in pending_titles:
            await notifier.announce_manual(
                order_id=order.id,
                item_id=item.id,
                title=title,
                user_id=order.user_id,
            )

    # Receipt.
    if delivered_lines or pending_titles:
        try:
            await _send_receipt(bot, order)
        except Exception:
            logger.exception("receipt send failed for order {}", order.id)

    return FulfillResult(
        delivered=len(delivered_lines),
        pending=len(pending_titles),
        already_done=False,
    )


async def _send_receipt(bot: "Bot", order: Order) -> None:
    items_lines = [
        f"• {it.title_snapshot} ×{it.quantity} — "
        f"{fmt_amount(it.unit_price * it.quantity, order.currency)}"
        for it in order.items
    ]
    if order.discount_amount:
        items_lines.append(
            f"Скидка: −{fmt_amount(order.discount_amount, order.currency)}"
        )
    text = t(
        "receipt",
        order_id=order.id,
        date=order.paid_at.strftime("%Y-%m-%d %H:%M") if order.paid_at else "",
        total=fmt_amount(order.total_amount, order.currency),
        provider=order.provider,
        items="\n".join(items_lines),
    )
    await bot.send_message(order.user_id, text)
