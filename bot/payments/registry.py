from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING

from bot.payments.balance import BalanceProvider
from bot.payments.base import PaymentProvider
from bot.payments.cryptobot import CryptoBotProvider
from bot.payments.lava import LavaProvider
from bot.payments.stars import StarsProvider

if TYPE_CHECKING:
    from bot.config import Settings
    from bot.database.models import Product


log = logging.getLogger(__name__)


class PaymentRegistry:
    """Holds the set of enabled payment providers, keyed by provider code."""

    def __init__(self, providers: Iterable[PaymentProvider] = ()) -> None:
        self._providers: dict[str, PaymentProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: PaymentProvider) -> None:
        if provider.code in self._providers:
            raise ValueError(f"Provider {provider.code!r} already registered")
        self._providers[provider.code] = provider

    def get(self, code: str) -> PaymentProvider | None:
        return self._providers.get(code)

    def all(self) -> list[PaymentProvider]:
        """Public providers — used to build user-facing payment buttons."""
        return [p for p in self._providers.values() if not p.is_internal]

    def all_including_internal(self) -> list[PaymentProvider]:
        return list(self._providers.values())

    def for_product(self, product: "Product") -> list[PaymentProvider]:
        return [
            p
            for p in self._providers.values()
            if not p.is_internal and p.price_for(product) is not None
        ]

    async def aclose(self) -> None:
        for provider in self._providers.values():
            try:
                await provider.aclose()
            except Exception:
                log.warning("provider %s aclose failed", provider.code, exc_info=True)


def build_registry(settings: "Settings") -> PaymentRegistry:
    """Instantiate every provider whose configuration is present."""
    providers: list[PaymentProvider] = [StarsProvider(), BalanceProvider()]

    if settings.cryptobot_token:
        providers.append(
            CryptoBotProvider(
                token=settings.cryptobot_token,
                asset=settings.cryptobot_asset,
                testnet=settings.cryptobot_testnet,
            )
        )
        log.info("CryptoBot provider enabled (asset=%s)", settings.cryptobot_asset)

    if settings.lava_secret_key and settings.lava_shop_id:
        providers.append(
            LavaProvider(
                secret_key=settings.lava_secret_key,
                shop_id=settings.lava_shop_id,
                webhook_url=settings.webhook_url_for("lava"),
                success_url=settings.lava_success_url or None,
                fail_url=settings.lava_fail_url or None,
            )
        )
        log.info("Lava provider enabled")

    return PaymentRegistry(providers)
