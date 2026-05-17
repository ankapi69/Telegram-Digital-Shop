from __future__ import annotations

import hashlib
import hmac
import json
import logging
from collections.abc import Mapping
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import aiohttp

from bot.payments.base import (
    InvoiceResult,
    PaymentProvider,
    PaymentStatus,
    WebhookEvent,
)

if TYPE_CHECKING:
    from aiogram import Bot
    from aiogram.types import User as TgUser

    from bot.database.models import Order, Product


log = logging.getLogger(__name__)

MAINNET = "https://pay.crypt.bot/api"
TESTNET = "https://testnet-pay.crypt.bot/api"

_STATUS_MAP = {
    "active": PaymentStatus.PENDING,
    "paid": PaymentStatus.PAID,
    "expired": PaymentStatus.EXPIRED,
}


class CryptoBotError(RuntimeError):
    pass


class CryptoBotProvider(PaymentProvider):
    code = "cryptobot"
    display_name = "CryptoBot"

    def __init__(
        self,
        token: str,
        asset: str = "USDT",
        testnet: bool = False,
        timeout: float = 15.0,
    ) -> None:
        if not token:
            raise ValueError("CryptoBot token is required")
        self._token = token
        self._asset = asset
        self.currency = asset
        self._base_url = TESTNET if testnet else MAINNET
        # The webhook signature secret is sha256(token), not the token itself.
        self._signature_secret = hashlib.sha256(token.encode()).digest()
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    def _client(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                headers={"Crypto-Pay-API-Token": self._token},
            )
        return self._session

    async def aclose(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _call(self, method: str, payload: dict[str, Any] | None = None) -> Any:
        client = self._client()
        async with client.post(f"{self._base_url}/{method}", json=payload or {}) as r:
            data = await r.json(content_type=None)
        if not data.get("ok"):
            raise CryptoBotError(f"{method} failed: {data}")
        return data["result"]

    def price_for(self, product: "Product") -> Decimal | None:
        return product.price_usdt

    async def create_invoice(
        self,
        *,
        bot: "Bot",
        order: "Order",
        product: "Product",
        user: "TgUser",
    ) -> InvoiceResult:
        amount = format(order.amount, "f")
        description = (product.description or product.title or "Товар")[:1024]
        result = await self._call(
            "createInvoice",
            {
                "asset": self._asset,
                "amount": amount,
                "description": description,
                "payload": str(order.id),
                "paid_btn_name": "callback",
                "paid_btn_url": f"https://t.me/{(await bot.me()).username}",
                "allow_comments": False,
                "allow_anonymous": False,
                "expires_in": 3600,
            },
        )
        return InvoiceResult(
            external_id=str(result["invoice_id"]),
            payment_url=result.get("pay_url") or result.get("bot_invoice_url"),
        )

    async def verify(self, order: "Order") -> PaymentStatus:
        if not order.external_id:
            return PaymentStatus.PENDING
        result = await self._call(
            "getInvoices", {"invoice_ids": str(order.external_id)}
        )
        items = result.get("items") or []
        if not items:
            return PaymentStatus.PENDING
        return _STATUS_MAP.get(items[0].get("status", ""), PaymentStatus.PENDING)

    async def parse_webhook(
        self, headers: Mapping[str, str], body: bytes
    ) -> WebhookEvent | None:
        signature = (
            headers.get("crypto-pay-api-signature")
            or headers.get("Crypto-Pay-Api-Signature")
            or headers.get("Crypto-Pay-API-Signature")
        )
        if not signature:
            log.warning("cryptobot webhook missing signature")
            return None
        expected = hmac.new(self._signature_secret, body, "sha256").hexdigest()
        if not hmac.compare_digest(expected, signature):
            log.warning("cryptobot webhook bad signature")
            return None
        try:
            data = json.loads(body)
        except ValueError:
            return None
        if data.get("update_type") != "invoice_paid":
            return None
        payload = data.get("payload") or {}
        invoice_id = payload.get("invoice_id")
        if invoice_id is None:
            return None
        return WebhookEvent(
            external_id=str(invoice_id),
            status=PaymentStatus.PAID,
        )
