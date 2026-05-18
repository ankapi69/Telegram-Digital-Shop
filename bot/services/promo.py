from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Promo, PromoType
from bot.repositories import promo as promo_repo


@dataclass(slots=True)
class PromoApplication:
    promo: Promo
    discount: Decimal
    total_after: Decimal


async def apply_promo(
    session: AsyncSession,
    code: str | None,
    subtotal: Decimal,
    currency: str,
) -> PromoApplication | None:
    if not code:
        return None
    promo = await promo_repo.get_by_code(session, code)
    if promo is None or not promo_repo.is_usable(promo):
        return None
    if promo.currency and promo.currency != currency:
        return None

    if promo.discount_type == PromoType.PERCENT:
        discount = (subtotal * promo.value / Decimal(100)).quantize(Decimal("0.0001"))
    else:
        discount = Decimal(promo.value)

    discount = min(discount, subtotal)
    total_after = subtotal - discount
    if total_after < 0:
        total_after = Decimal(0)
    return PromoApplication(promo=promo, discount=discount, total_after=total_after)
