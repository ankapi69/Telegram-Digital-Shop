from __future__ import annotations

import json
from decimal import Decimal
from typing import TYPE_CHECKING

from aiogram.types import LabeledPrice

from bot.payments.base import InvoiceResult, PaymentProvider, PaymentStatus

if TYPE_CHECKING:
    from aiogram import Bot
    from aiogram.types import User as TgUser

    from bot.database.models import Order, Product


def encode_payload(order_id: int) -> str:
    """Encode the bot's order id into the Telegram invoice payload."""
    return json.dumps({"o": order_id}, separators=(",", ":"))


def decode_payload(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(json.loads(raw)["o"])
    except (ValueError, TypeError, KeyError):
        return None


class StarsProvider(PaymentProvider):
    code = "stars"
    display_name = "Telegram Stars"
    supports_webhook = False  # Telegram delivers successful_payment via update
    supports_manual_check = False

    def __init__(self) -> None:
        self.currency = "XTR"

    def price_for(self, product: "Product") -> Decimal | None:
        if product.price_stars is None:
            return None
        return Decimal(product.price_stars)

    async def create_invoice(
        self,
        *,
        bot: "Bot",
        order: "Order",
        product: "Product",
        user: "TgUser",
    ) -> InvoiceResult:
        stars = int(order.amount)
        payload = encode_payload(order.id)
        title = (product.title or "Товар")[:32]
        description = (product.description or product.title or "Товар")[:255]
        await bot.send_invoice(
            chat_id=user.id,
            title=title,
            description=description,
            payload=payload,
            provider_token="",  # Stars
            currency="XTR",
            prices=[LabeledPrice(label=title, amount=stars)],
        )
        return InvoiceResult(external_id=payload, payment_url=None, sent_inline=True)

    async def verify(self, order: "Order") -> PaymentStatus:
        # Stars are confirmed by Telegram's successful_payment update,
        # not by polling. If we get here the order is still awaiting that
        # update.
        return PaymentStatus.PENDING
