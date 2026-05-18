from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import LedgerKind, Order, OrderKind
from bot.repositories import order as order_repo
from bot.repositories import wallet as wallet_repo
from bot.services.checkout import CheckoutError, CheckoutQuote


# Internal code used in Order.provider for wallet-paid orders.
BALANCE_PROVIDER_CODE = "balance"
WALLET_CURRENCY = "USD"


@dataclass(slots=True)
class WalletPayResult:
    order: Order
    new_balance: Decimal


class InsufficientFunds(CheckoutError):
    pass


async def pay_with_balance(
    session: AsyncSession,
    *,
    user_id: int,
    quote: CheckoutQuote,
) -> WalletPayResult:
    """Atomically debit the wallet, materialize an Order, and fulfill it.

    Caller is responsible for the surrounding transaction. On any failure
    the whole session is rolled back, leaving the wallet untouched.
    """
    if quote.provider.currency not in ("USDT", "USD"):
        raise CheckoutError("Баланс работает только в долларах")

    entry = await wallet_repo.try_debit(
        session,
        user_id=user_id,
        amount=quote.total,
        kind=LedgerKind.PURCHASE,
        comment="checkout",
    )
    if entry is None:
        raise InsufficientFunds("Недостаточно средств на балансе")

    order = await order_repo.create_order(
        session,
        user_id=user_id,
        provider=BALANCE_PROVIDER_CODE,
        currency=WALLET_CURRENCY,
        subtotal=quote.subtotal,
        discount=quote.discount,
        total=quote.total,
        promo_code=quote.promo.promo.code if quote.promo else None,
        items=quote.lines,
        kind=OrderKind.PURCHASE,
    )
    order.external_id = f"ledger-{entry.id}"
    entry.ref_order_id = order.id

    await session.flush()
    new_balance = await wallet_repo.get_balance(session, user_id)
    return WalletPayResult(order=order, new_balance=new_balance)
