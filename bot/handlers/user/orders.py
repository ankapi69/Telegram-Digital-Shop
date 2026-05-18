from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import OrderItemStatus, OrderStatus
from bot.keyboards.user import orders_pagination_kb
from bot.locales import translate
from bot.repositories.order import list_user_orders_page
from bot.utils.money import fmt_amount

router = Router(name="orders")


_PER_PAGE = 5

_STATUS_KEYS = {
    OrderStatus.PENDING_PAYMENT: "status_pending_payment",
    OrderStatus.AWAITING_DELIVERY: "status_awaiting_delivery",
    OrderStatus.DELIVERED: "status_delivered",
    OrderStatus.CANCELLED: "status_cancelled",
    OrderStatus.REFUNDED: "status_refunded",
}


@router.callback_query(F.data == "orders:nop")
async def nop(cb: CallbackQuery) -> None:
    await cb.answer()


@router.callback_query(F.data.startswith("orders:"))
async def show_orders(
    cb: CallbackQuery, session: AsyncSession, t=translate
) -> None:
    if cb.data is None or cb.from_user is None or cb.message is None:
        await cb.answer()
        return
    try:
        page = int(cb.data.split(":", 1)[1])
    except ValueError:
        await cb.answer()
        return

    orders, total = await list_user_orders_page(
        session, cb.from_user.id, page, _PER_PAGE
    )
    if total == 0:
        await cb.message.edit_text(t("orders_empty"), reply_markup=orders_pagination_kb(1, 1))
        await cb.answer()
        return

    pages = max(1, (total + _PER_PAGE - 1) // _PER_PAGE)
    page = max(1, min(page, pages))

    lines = [t("orders_title"), ""]
    for order in orders:
        status = t(_STATUS_KEYS.get(order.status, order.status.value))
        first_title = order.items[0].title_snapshot if order.items else "—"
        more = f" (+{len(order.items) - 1})" if len(order.items) > 1 else ""
        amount = fmt_amount(order.total_amount, order.currency)
        lines.append(
            t("order_line", id=order.id, title=first_title + more, amount=amount, status=status)
        )
        for item in order.items:
            if item.status == OrderItemStatus.DELIVERED and item.delivered_content:
                lines.append(f"  ↳ <code>{item.delivered_content}</code>")
    lines.append("")
    lines.append(t("order_page", page=page, pages=pages))

    try:
        await cb.message.edit_text("\n".join(lines), reply_markup=orders_pagination_kb(page, pages))
    except Exception:
        await cb.message.answer("\n".join(lines), reply_markup=orders_pagination_kb(page, pages))
    await cb.answer()
