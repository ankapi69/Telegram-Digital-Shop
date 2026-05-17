import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import OrderStatus
from bot.keyboards.admin import (
    admin_menu_kb,
    order_fulfill_kb,
    pending_orders_kb,
)
from bot.repositories.order import (
    get_order_with_product,
    list_awaiting_delivery,
    mark_delivered,
)
from bot.states.admin import ManualFulfill

router = Router(name="admin-orders")
log = logging.getLogger(__name__)

MAX_CONTENT_LENGTH = 4000


@router.callback_query(F.data == "adm:manual")
async def list_manual(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.message is None:
        await cb.answer()
        return
    orders = await list_awaiting_delivery(session)
    if not orders:
        await cb.message.edit_text(
            "Очередь ручной выдачи пуста.", reply_markup=admin_menu_kb()
        )
    else:
        await cb.message.edit_text(
            "📨 <b>Ожидают ручной выдачи</b>",
            reply_markup=pending_orders_kb(orders),
        )
    await cb.answer()


@router.callback_query(F.data.startswith("adm:ord:"))
async def view_order(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.message is None or cb.data is None:
        await cb.answer()
        return
    order_id = int(cb.data.rsplit(":", 1)[1])
    row = await get_order_with_product(session, order_id)
    if row is None:
        await cb.answer("Не найден", show_alert=True)
        return
    order, product = row
    await cb.message.edit_text(
        f"Заказ <b>#{order.id}</b>\n"
        f"Товар: <b>{product.title}</b>\n"
        f"Цена: <b>{order.price_stars}⭐</b>\n"
        f"Покупатель: <code>{order.user_id}</code>\n"
        f"Статус: <i>{order.status.value}</i>",
        reply_markup=order_fulfill_kb(order.id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("adm:fulfill:"))
async def fulfill_start(
    cb: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    if cb.message is None or cb.data is None:
        await cb.answer()
        return
    order_id = int(cb.data.rsplit(":", 1)[1])
    row = await get_order_with_product(session, order_id)
    if row is None or row[0].status != OrderStatus.AWAITING_DELIVERY:
        await cb.answer("Заказ уже не ждёт выдачи", show_alert=True)
        return
    await state.set_state(ManualFulfill.waiting_content)
    await state.update_data(order_id=order_id)
    await cb.message.edit_text(
        f"Пришлите содержимое для заказа #{order_id}. "
        "Оно будет отправлено покупателю как есть."
    )
    await cb.answer()


@router.message(ManualFulfill.waiting_content, F.text)
async def fulfill_send(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    content = (message.text or "").strip()
    if not content:
        await message.answer("Пустой текст. Пришлите содержимое.")
        return
    if len(content) > MAX_CONTENT_LENGTH:
        await message.answer(f"Слишком длинно (>{MAX_CONTENT_LENGTH}).")
        return

    data = await state.get_data()
    order_id = int(data.get("order_id", 0))
    row = await get_order_with_product(session, order_id)
    if row is None or row[0].status != OrderStatus.AWAITING_DELIVERY:
        await state.clear()
        await message.answer("Заказ уже обработан.", reply_markup=admin_menu_kb())
        return
    order, product = row

    try:
        await bot.send_message(
            order.user_id,
            "✉️ Ваш заказ выдан вручную.\n\n"
            f"Товар: <b>{product.title}</b>\n\n"
            f"<code>{content}</code>",
        )
    except Exception:
        log.exception("Failed to deliver order %s to user %s", order.id, order.user_id)
        await message.answer(
            "Не удалось отправить сообщение покупателю. "
            "Заказ оставлен в очереди."
        )
        return

    await mark_delivered(session, order, content)
    await state.clear()
    await message.answer(
        f"✅ Заказ #{order.id} выдан.", reply_markup=admin_menu_kb()
    )
