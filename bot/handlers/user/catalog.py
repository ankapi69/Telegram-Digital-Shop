from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.markdown import hbold
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import DeliveryType
from bot.keyboards.user import categories_kb, product_kb
from bot.locales import translate
from bot.payments.registry import PaymentRegistry
from bot.repositories import category as cat_repo
from bot.repositories import product as product_repo
from bot.utils.money import fmt_amount

router = Router(name="catalog")


async def _render_category(
    cb: CallbackQuery, session: AsyncSession, category_id: int | None, t
) -> None:
    if cb.message is None:
        await cb.answer()
        return
    subcats = await cat_repo.list_children(session, category_id)
    products = await cat_repo.list_products_in(session, category_id)
    if not subcats and not products and category_id is None:
        await cb.message.edit_text(t("catalog_empty"))
        return
    parent_id = None
    if category_id is not None:
        cat = await cat_repo.get_category(session, category_id)
        if cat is None:
            await cb.answer()
            return
        parent_id = cat.parent_id
        title = t("subcatalog_title", name=cat.name)
    else:
        title = t("catalog_title")
    await cb.message.edit_text(
        title, reply_markup=categories_kb(subcats, products, parent_id)
    )


@router.callback_query(F.data == "catalog")
async def show_root_catalog(
    cb: CallbackQuery, session: AsyncSession, t=translate
) -> None:
    await _render_category(cb, session, None, t)
    await cb.answer()


@router.callback_query(F.data.startswith("cat:"))
async def show_category(
    cb: CallbackQuery, session: AsyncSession, t=translate
) -> None:
    if cb.data is None:
        await cb.answer()
        return
    parts = cb.data.split(":")
    # cat:<id>           — go into category
    # cat:<id>:up        — go up: jump to that category's parent (id is current cat)
    try:
        category_id = int(parts[1])
    except (IndexError, ValueError):
        await cb.answer()
        return
    if len(parts) >= 3 and parts[2] == "up":
        cat = await cat_repo.get_category(session, category_id)
        await _render_category(cb, session, cat.parent_id if cat else None, t)
    else:
        await _render_category(cb, session, category_id, t)
    await cb.answer()


@router.callback_query(F.data.startswith("product:"))
async def show_product(
    cb: CallbackQuery,
    session: AsyncSession,
    registry: PaymentRegistry,
    t=translate,
) -> None:
    if cb.message is None or cb.data is None:
        await cb.answer()
        return
    product_id = int(cb.data.split(":", 1)[1])
    product = await product_repo.get_product(session, product_id)
    if product is None or not product.is_active:
        await cb.answer(t("out_of_stock"), show_alert=True)
        return

    providers = registry.for_product(product)
    can_buy = bool(providers)
    extra: list[str] = []
    if product.delivery_type == DeliveryType.AUTO:
        available = await product_repo.count_available_stock(session, product.id)
        if product.show_stock:
            extra.append(t("stock_left", n=available))
        if available <= 0:
            can_buy = False
    else:
        extra.append(t("manual_delivery_note"))

    price_lines = [
        f"  • {p.display_name}: {fmt_amount(p.price_for(product), p.currency)}"
        for p in providers
        if p.price_for(product) is not None
    ]
    if price_lines:
        extra.append(t("prices_label"))
        extra.extend(price_lines)
    else:
        extra.append(t("no_providers"))
        can_buy = False

    text = (
        f"{hbold(product.title)}\n\n"
        f"{product.description or '—'}\n\n" + "\n".join(extra)
    )
    markup = product_kb(product, providers, can_buy, product.category_id)
    if product.photo_file_id:
        try:
            await cb.message.delete()
        except Exception:
            pass
        await cb.message.answer_photo(
            product.photo_file_id, caption=text, reply_markup=markup
        )
    else:
        try:
            await cb.message.edit_text(text, reply_markup=markup)
        except Exception:
            await cb.message.answer(text, reply_markup=markup)
    await cb.answer()
