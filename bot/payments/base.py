from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import ClassVar, TYPE_CHECKING

if TYPE_CHECKING:  # avoid circular imports at module load time
    from aiogram import Bot
    from aiogram.types import User as TgUser

    from bot.database.models import Order, Product


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(slots=True)
class InvoiceResult:
    """What we got back from the provider after creating an invoice.

    ``external_id`` is the identifier we will later send back to the
    provider when polling status or matching a webhook.

    ``payment_url`` is a URL the user can open to pay; ``None`` for
    inline flows (Telegram Stars sends the invoice via ``send_invoice``
    directly inside the bot chat).

    ``sent_inline`` tells the UI layer not to render an external pay
    button — the invoice already lives in the user's chat.
    """

    external_id: str
    payment_url: str | None = None
    sent_inline: bool = False
    expires_at: datetime | None = None


@dataclass(slots=True)
class WebhookEvent:
    """Result of parsing+verifying a provider webhook callback."""

    external_id: str
    status: PaymentStatus
    raw_amount: Decimal | None = None
    raw_currency: str | None = None


class PaymentProvider(ABC):
    """Pluggable payment backend.

    Subclasses declare a stable ``code`` (used in DB rows and webhook
    routes) plus the ``currency`` they price products in.  Adding a new
    provider is just: subclass this, plug into
    :func:`bot.payments.registry.build_registry`.
    """

    code: ClassVar[str]
    display_name: ClassVar[str]
    supports_webhook: ClassVar[bool] = True
    supports_manual_check: ClassVar[bool] = True
    # Internal providers (e.g. wallet) don't appear in the buyer's
    # provider button list and aren't offered as a checkout option.
    is_internal: ClassVar[bool] = False
    # ``currency`` may be set as a class attribute on subclasses with a
    # fixed currency (Stars=XTR, Lava=RUB) or as an instance attribute on
    # subclasses where it depends on configuration (CryptoBot asset).
    currency: str

    @abstractmethod
    def price_for(self, product: "Product") -> Decimal | None:
        """Price of ``product`` in this provider's currency, or ``None``
        if the product isn't sold via this provider."""

    @abstractmethod
    async def create_invoice(
        self,
        *,
        bot: "Bot",
        order: "Order",
        product: "Product | None",
        user: "TgUser",
    ) -> InvoiceResult:
        """Create an invoice on the provider's side and return identifiers.

        ``product`` is provided for single-line orders for backwards
        compatibility; for multi-item carts it is ``None`` and the
        provider should derive a description from ``order``.
        """

    @abstractmethod
    async def verify(self, order: "Order") -> PaymentStatus:
        """Poll the provider for the current status of ``order``."""

    async def parse_webhook(
        self, headers: Mapping[str, str], body: bytes
    ) -> WebhookEvent | None:
        """Parse and signature-verify a webhook payload.

        Return ``None`` if the request is unauthenticated, malformed, or
        not an event we care about (so the HTTP layer can reply 400 or
        silently 200).  Default: no webhooks.
        """
        return None

    async def aclose(self) -> None:
        """Release any provider-owned resources (HTTP sessions, etc.)."""
