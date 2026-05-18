from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import OrderItemStatus
from bot.keyboards.admin import (
    admin_menu_kb,
    item_fulfill_kb,
    pending_items_kb,
)
from bot.repositories.order import (
    get_order,
    get_order_item,
    list_pending_manual_items,
    mark_item_delivered,
    refresh_order_state,
)
from bot.states.admin import ManualFulfill

router = Router(name="admin-orders")

MAX_CONTENT = 4000


@router.callback_query(F.data == "adm:manual")
async def list_manual(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.message is None:
        await cb.answer()
        return
    items = await list_pending_manual_items(session)
    if not items:
        try:
            await cb.message.edit_text("Очередь пуста.")
        except Exception:
            pass
    else:
        try:
            await cb.message.edit_text(
                "📨 <b>Ждут ручной выдачи</b>", reply_markup=pending_items_kb(items)
            )
        except Exception:
            await cb.message.answer(
                "📨 <b>Ждут ручной выдачи</b>", reply_markup=pending_items_kb(items)
            )
    await cb.answer()


@router.callback_query(F.data.startswith("adm:item:"))
async def view_item(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.data is None or cb.message is None:
        await cb.answer()
        return
    item_id = int(cb.data.rsplit(":", 1)[1])
    item = await get_order_item(session, item_id)
    if item is None:
        await cb.answer("Нет", show_alert=True)
        return
    order = await get_order(session, item.order_id)
    text = (
        f"Заказ <b>#{item.order_id}</b> · позиция #{item.id}\n"
        f"Товар: <b>{item.title_snapshot}</b> ×{item.quantity}\n"
        f"Сумма: <b>{item.unit_price * item.quantity} {order.currency if order else ''}</b>\n"
        f"Покупатель: <code>{order.user_id if order else ''}</code>\n"
        f"Статус позиции: <i>{item.status.value}</i>"
    )
    try:
        await cb.message.edit_text(text, reply_markup=item_fulfill_kb(item.id))
    except Exception:
        await cb.message.answer(text, reply_markup=item_fulfill_kb(item.id))
    await cb.answer()


@router.callback_query(F.data.startswith("adm:fulfill:"))
async def fulfill_start(
    cb: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    if cb.data is None or cb.message is None:
        await cb.answer()
        return
    item_id = int(cb.data.rsplit(":", 1)[1])
    item = await get_order_item(session, item_id)
    if item is None or item.status != OrderItemStatus.PENDING:
        await cb.answer("Уже выдано/недоступно", show_alert=True)
        return
    await state.set_state(ManualFulfill.waiting_content)
    await state.update_data(item_id=item_id)
    await cb.message.edit_text(
        f"Пришлите содержимое для #{item.order_id}·{item.id}. "
        "Будет отправлено покупателю как есть."
    )
    await cb.answer()


@router.message(ManualFulfill.waiting_content, F.text)
async def fulfill_send(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
) -> None:
    content = (message.text or "").strip()
    if not content:
        await message.answer("Пусто.")
        return
    if len(content) > MAX_CONTENT:
        await message.answer(f"Макс {MAX_CONTENT}.")
        return

    data = await state.get_data()
    item_id = int(data.get("item_id", 0))
    item = await get_order_item(session, item_id)
    if item is None or item.status != OrderItemStatus.PENDING:
        await state.clear()
        await message.answer("Уже обработано.")
        return
    order = await get_order(session, item.order_id)
    if order is None:
        await state.clear()
        await message.answer("Заказ исчез.")
        return
    try:
        await bot.send_message(
            order.user_id,
            "✉️ Ручная выдача.\n\n"
            f"<b>{item.title_snapshot}</b>\n\n<code>{content}</code>",
        )
    except Exception:
        logger.exception("manual deliver to {} failed", order.user_id)
        await message.answer("Не удалось отправить пользователю.")
        return

    await mark_item_delivered(session, item, content)
    await refresh_order_state(session, order)
    await state.clear()
    await message.answer(f"✅ Позиция #{item.id} выдана.")
