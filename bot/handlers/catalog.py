from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.markdown import hbold
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import DeliveryType
from bot.keyboards.user import _fmt_amount, catalog_kb, product_kb
from bot.payments.registry import PaymentRegistry
from bot.repositories.product import (
    count_available_stock,
    get_product,
    list_active_products,
)

router = Router(name="catalog")


@router.callback_query(F.data == "catalog")
async def show_catalog(cb: CallbackQuery, session: AsyncSession) -> None:
    if cb.message is None:
        await cb.answer()
        return
    products = await list_active_products(session)
    if not products:
        await cb.message.edit_text(
            "Каталог пока пуст. Загляните позже.",
            reply_markup=catalog_kb([]),
        )
    else:
        await cb.message.edit_text(
            "🛍 <b>Каталог</b>\n\nВыберите товар:",
            reply_markup=catalog_kb(products),
        )
    await cb.answer()


@router.callback_query(F.data.startswith("product:"))
async def show_product(
    cb: CallbackQuery, session: AsyncSession, registry: PaymentRegistry
) -> None:
    if cb.message is None or cb.data is None:
        await cb.answer()
        return
    product_id = int(cb.data.split(":", 1)[1])
    product = await get_product(session, product_id)
    if product is None or not product.is_active:
        await cb.answer("Товар недоступен", show_alert=True)
        return

    providers = registry.for_product(product)

    extra_lines: list[str] = []
    can_buy = bool(providers)
    if product.delivery_type == DeliveryType.AUTO:
        available = await count_available_stock(session, product.id)
        extra_lines.append(f"📦 В наличии: <b>{available}</b>")
        if available <= 0:
            can_buy = False
    else:
        extra_lines.append("📨 Выдаётся вручную после оплаты")

    price_lines = [
        f"  • {p.display_name}: {_fmt_amount(p.price_for(product), p.currency)}"
        for p in providers
        if p.price_for(product) is not None
    ]
    if price_lines:
        extra_lines.append("💰 Способы оплаты:")
        extra_lines.extend(price_lines)
    else:
        extra_lines.append("⛔️ Нет настроенных способов оплаты")
        can_buy = False

    text = (
        f"{hbold(product.title)}\n\n"
        f"{product.description or '—'}\n\n"
        + "\n".join(extra_lines)
    )
    await cb.message.edit_text(
        text, reply_markup=product_kb(product, providers, can_buy)
    )
    await cb.answer()
