from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Settings
from bot.filters.admin import SupportGroupFilter
from bot.keyboards.user import support_cancel_kb
from bot.locales import translate
from bot.services.support import SupportService
from bot.states.admin import Support

router = Router(name="support")


@router.callback_query(F.data == "support")
async def support_start(
    cb: CallbackQuery,
    state: FSMContext,
    support: SupportService,
    t=translate,
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    if not support.enabled:
        await cb.answer(t("support_disabled"), show_alert=True)
        return
    await state.set_state(Support.waiting_message)
    try:
        await cb.message.edit_text(t("support_prompt"), reply_markup=support_cancel_kb())
    except Exception:
        await cb.message.answer(t("support_prompt"), reply_markup=support_cancel_kb())
    await cb.answer()


@router.message(Support.waiting_message)
async def support_relay(
    message: Message,
    state: FSMContext,
    support: SupportService,
    t=translate,
) -> None:
    ok = await support.forward_from_user(message)
    await state.clear()
    if ok:
        await message.answer(t("support_sent"))
    else:
        await message.answer(t("support_disabled"))


def make_group_router(settings: Settings) -> Router:
    """Router that listens inside the support group chat for admin replies."""
    r = Router(name="support-group")
    flt = SupportGroupFilter(settings.support_group_id)
    r.message.filter(flt)

    @r.message(F.reply_to_message)
    async def admin_reply(
        message: Message, support: SupportService, t=translate
    ) -> None:
        ok = await support.reply_back(message)
        if ok:
            await message.reply(t("support_reply_ok"))
        else:
            await message.reply(t("support_reply_help"))

    return r
