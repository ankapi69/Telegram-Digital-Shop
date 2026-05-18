from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.user import back_to_menu_kb
from bot.repositories import stats as stats_repo
from bot.utils.money import fmt_amount

router = Router(name="admin-stats")


@router.callback_query(F.data == "adm:stats")
async def show_stats(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.message is None:
        await cb.answer()
        return

    revenue = await stats_repo.revenue_by_day(session, days=14)
    top = await stats_repo.top_products(session, limit=10, days=30)
    dau = await stats_repo.dau(session)
    total = await stats_repo.total_users(session)
    banned = await stats_repo.banned_users(session)

    lines = ["📊 <b>Статистика</b>", ""]
    lines.append(f"👥 Всего пользователей: <b>{total}</b>")
    lines.append(f"🟢 DAU (24ч): <b>{dau}</b>")
    lines.append(f"🚫 Заблокировано: <b>{banned}</b>")
    lines.append("")
    lines.append("💰 <b>Выручка (14 дней)</b>")
    if not revenue:
        lines.append("  пока нет оплат")
    else:
        for d, c, s in revenue:
            lines.append(f"  {d} · {fmt_amount(s, c)}")
    lines.append("")
    lines.append("🔥 <b>Топ-10 товаров (30 дней)</b>")
    if not top:
        lines.append("  нет данных")
    else:
        for title, qty, rev, cur in top:
            lines.append(f"  • {title} — {qty} шт · {fmt_amount(rev, cur)}")

    text = "\n".join(lines)
    try:
        await cb.message.edit_text(text, reply_markup=back_to_menu_kb())
    except Exception:
        await cb.message.answer(text, reply_markup=back_to_menu_kb())
    await cb.answer()
