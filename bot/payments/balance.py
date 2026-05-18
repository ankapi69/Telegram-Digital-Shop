from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from bot.payments.base import InvoiceResult, PaymentProvider, PaymentStatus

if TYPE_CHECKING:
    from aiogram import Bot
    from aiogram.types import User as TgUser

    from bot.database.models import Order, Product


class BalanceProvider(PaymentProvider):
    """Pay-from-wallet "provider".

    Doesn't actually create an external invoice — the handler atomically
    debits the user's wallet and immediately marks the order as paid.
    The provider is excluded from the public catalog button list; it's
    only used to share ``price_for()`` and quote-building logic.
    """

    code = "balance"
    display_name = "Баланс"
    supports_webhook = False
    supports_manual_check = False
    is_internal = True

    def __init__(self) -> None:
        # Internally we equate the wallet to USD — same as USDT in this bot.
        self.currency = "USDT"

    def price_for(self, product: "Product") -> Decimal | None:
        return product.price_usdt

    async def create_invoice(
        self,
        *,
        bot: "Bot",
        order: "Order",
        product: "Product | None",
        user: "TgUser",
    ) -> InvoiceResult:
        # Not actually called — the wallet path bypasses provider.create_invoice.
        return InvoiceResult(external_id=str(order.id), sent_inline=True)

    async def verify(self, order: "Order") -> PaymentStatus:
        return PaymentStatus.PAID
