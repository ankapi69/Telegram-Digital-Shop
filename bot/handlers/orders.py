from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import OrderStatus
from bot.keyboards.user import _fmt_amount, back_to_menu_kb
from bot.repositories.order import list_user_orders
from bot.repositories.product import get_product

router = Router(name="orders")


STATUS_LABELS: dict[OrderStatus, str] = {
    OrderStatus.PENDING_PAYMENT: "ожидает оплаты",
    OrderStatus.AWAITING_DELIVERY: "ожидает выдачи",
    OrderStatus.DELIVERED: "выдан",
    OrderStatus.CANCELLED: "отменён",
    OrderStatus.REFUNDED: "возвращён",
}


@router.callback_query(F.data == "orders")
async def show_orders(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.message is None or cb.from_user is None:
        await cb.answer()
        return

    orders = await list_user_orders(session, cb.from_user.id)
    if not orders:
        await cb.message.edit_text(
            "У вас пока нет заказов.", reply_markup=back_to_menu_kb()
        )
        await cb.answer()
        return

    lines = ["📦 <b>Ваши заказы</b>", ""]
    for order in orders:
        product = await get_product(session, order.product_id)
        title = product.title if product else f"товар #{order.product_id}"
        status = STATUS_LABELS.get(order.status, order.status.value)
        amount = _fmt_amount(order.amount, order.currency)
        lines.append(f"#{order.id} • {title} • {amount} • <i>{status}</i>")
        if order.delivered_content and order.status == OrderStatus.DELIVERED:
            lines.append(f"  ↳ <code>{order.delivered_content}</code>")

    await cb.message.edit_text("\n".join(lines), reply_markup=back_to_menu_kb())
    await cb.answer()
