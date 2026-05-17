from __future__ import annotations

import hmac
import json
import logging
import uuid
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

BASE_URL = "https://api.lava.ru/business"

# Lava.ru business invoice statuses.
_STATUS_MAP = {
    "success": PaymentStatus.PAID,
    "pending": PaymentStatus.PENDING,
    "cancel": PaymentStatus.CANCELLED,
    "expired": PaymentStatus.EXPIRED,
    "error": PaymentStatus.FAILED,
}


class LavaError(RuntimeError):
    pass


class LavaProvider(PaymentProvider):
    """Lava.ru Business API integration.

    Auth: every request is signed with HMAC-SHA256 over the raw JSON body
    using the shop's secret key.  Webhooks are signed with the same
    scheme.
    """

    code = "lava"
    display_name = "Lava (RUB)"

    def __init__(
        self,
        secret_key: str,
        shop_id: str,
        webhook_url: str | None = None,
        success_url: str | None = None,
        fail_url: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        if not secret_key or not shop_id:
            raise ValueError("Lava secret_key and shop_id are required")
        self.currency = "RUB"
        self._secret = secret_key.encode()
        self._shop_id = shop_id
        self._webhook_url = webhook_url or ""
        self._success_url = success_url or ""
        self._fail_url = fail_url or ""
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None

    def _client(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def aclose(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    def _sign(self, body: bytes) -> str:
        return hmac.new(self._secret, body, "sha256").hexdigest()

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = self._sign(body)
        client = self._client()
        async with client.post(
            f"{BASE_URL}{path}",
            data=body,
            headers={
                "Signature": signature,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        ) as r:
            data = await r.json(content_type=None)
        if data.get("status_check") is False or data.get("status") == "error":
            raise LavaError(f"{path} failed: {data}")
        return data

    def price_for(self, product: "Product") -> Decimal | None:
        return product.price_rub

    async def create_invoice(
        self,
        *,
        bot: "Bot",
        order: "Order",
        product: "Product",
        user: "TgUser",
    ) -> InvoiceResult:
        local_order_id = uuid.uuid4().hex
        amount = format(order.amount, "f")
        comment = (product.description or product.title or "Товар")[:255]
        payload: dict[str, Any] = {
            "sum": amount,
            "orderId": local_order_id,
            "shopId": self._shop_id,
            "comment": comment,
            "expire": 30,  # minutes
        }
        if self._webhook_url:
            payload["hookUrl"] = self._webhook_url
        if self._success_url:
            payload["successUrl"] = self._success_url
        if self._fail_url:
            payload["failUrl"] = self._fail_url

        data = await self._post("/invoice/create", payload)
        body = data.get("data") or {}
        url = body.get("url")
        if not url:
            raise LavaError(f"invoice/create returned no url: {data}")
        return InvoiceResult(external_id=local_order_id, payment_url=url)

    async def verify(self, order: "Order") -> PaymentStatus:
        if not order.external_id:
            return PaymentStatus.PENDING
        data = await self._post(
            "/invoice/status",
            {"orderId": order.external_id, "shopId": self._shop_id},
        )
        status_raw = (data.get("data") or {}).get("status", "")
        return _STATUS_MAP.get(str(status_raw).lower(), PaymentStatus.PENDING)

    async def parse_webhook(
        self, headers: Mapping[str, str], body: bytes
    ) -> WebhookEvent | None:
        signature = headers.get("Signature") or headers.get("signature")
        if not signature:
            log.warning("lava webhook missing signature")
            return None
        if not hmac.compare_digest(self._sign(body), signature):
            log.warning("lava webhook bad signature")
            return None
        try:
            data = json.loads(body)
        except ValueError:
            return None
        order_id = data.get("order_id") or data.get("orderId")
        if not order_id:
            return None
        status_raw = str(data.get("status", "")).lower()
        return WebhookEvent(
            external_id=str(order_id),
            status=_STATUS_MAP.get(status_raw, PaymentStatus.PENDING),
        )
