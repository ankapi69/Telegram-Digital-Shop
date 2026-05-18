from __future__ import annotations

from decimal import Decimal

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import LedgerEntry, LedgerKind, Wallet


async def get_or_create(session: AsyncSession, user_id: int) -> Wallet:
    wallet = await session.get(Wallet, user_id)
    if wallet is None:
        wallet = Wallet(user_id=user_id, balance=Decimal("0"))
        session.add(wallet)
        await session.flush()
    return wallet


async def get_balance(session: AsyncSession, user_id: int) -> Decimal:
    wallet = await session.get(Wallet, user_id)
    return wallet.balance if wallet else Decimal("0")


async def credit(
    session: AsyncSession,
    *,
    user_id: int,
    amount: Decimal,
    kind: LedgerKind,
    ref_order_id: int | None = None,
    ref_admin_id: int | None = None,
    comment: str | None = None,
) -> LedgerEntry:
    """Add ``amount`` to the wallet (must be positive) and append a ledger row."""
    if amount <= 0:
        raise ValueError("credit amount must be positive")
    await get_or_create(session, user_id)
    await session.execute(
        update(Wallet)
        .where(Wallet.user_id == user_id)
        .values(balance=Wallet.balance + amount)
    )
    entry = LedgerEntry(
        user_id=user_id,
        delta=amount,
        kind=kind,
        ref_order_id=ref_order_id,
        ref_admin_id=ref_admin_id,
        comment=comment,
    )
    session.add(entry)
    await session.flush()
    return entry


async def try_debit(
    session: AsyncSession,
    *,
    user_id: int,
    amount: Decimal,
    kind: LedgerKind,
    ref_order_id: int | None = None,
    ref_admin_id: int | None = None,
    comment: str | None = None,
) -> LedgerEntry | None:
    """Atomically subtract ``amount`` from balance iff sufficient funds exist.

    Returns the ledger entry on success or ``None`` if balance was too low.
    The conditional UPDATE rules out negative balances under concurrent
    debits without needing a SELECT-then-UPDATE check.
    """
    if amount <= 0:
        raise ValueError("debit amount must be positive")
    result = await session.execute(
        update(Wallet)
        .where(Wallet.user_id == user_id, Wallet.balance >= amount)
        .values(balance=Wallet.balance - amount)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        return None
    entry = LedgerEntry(
        user_id=user_id,
        delta=-amount,
        kind=kind,
        ref_order_id=ref_order_id,
        ref_admin_id=ref_admin_id,
        comment=comment,
    )
    session.add(entry)
    await session.flush()
    return entry


async def admin_adjust(
    session: AsyncSession,
    *,
    target_user_id: int,
    delta: Decimal,
    admin_id: int,
    comment: str | None,
) -> LedgerEntry | None:
    """Manager-driven balance change. Negative ``delta`` debits the wallet.

    Returns ``None`` if a debit was requested but the user doesn't have enough.
    """
    if delta == 0:
        raise ValueError("delta must be non-zero")
    if delta > 0:
        return await credit(
            session,
            user_id=target_user_id,
            amount=delta,
            kind=LedgerKind.ADMIN_ADJUST,
            ref_admin_id=admin_id,
            comment=comment,
        )
    return await try_debit(
        session,
        user_id=target_user_id,
        amount=-delta,
        kind=LedgerKind.ADMIN_ADJUST,
        ref_admin_id=admin_id,
        comment=comment,
    )


async def list_entries(
    session: AsyncSession, user_id: int, limit: int = 10
) -> list[LedgerEntry]:
    stmt = (
        select(LedgerEntry)
        .where(LedgerEntry.user_id == user_id)
        .order_by(desc(LedgerEntry.id))
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())
