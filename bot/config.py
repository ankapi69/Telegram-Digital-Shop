from functools import cached_property, lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_ids(raw: str) -> list[int]:
    return [int(part) for part in raw.split(",") if part.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    bot_token: str = Field(..., min_length=10)

    # Comma-separated role lists. Superadmins inherit everything.
    superadmin_ids_raw: str = Field(default="", alias="SUPERADMIN_IDS")
    manager_ids_raw: str = Field(default="", alias="MANAGER_IDS")
    support_ids_raw: str = Field(default="", alias="SUPPORT_IDS")
    # Legacy alias: still accepted, becomes superadmin.
    admin_ids_raw: str = Field(default="", alias="ADMIN_IDS")

    database_url: str = "sqlite+aiosqlite:///./shop.db"
    redis_url: str | None = None

    # Group chats for notifications. 0 / empty disables.
    notify_group_id: int = 0
    support_group_id: int = 0

    throttle_rate: float = 0.5
    log_level: str = "INFO"

    catalog_cache_ttl: int = 60
    cart_ttl_seconds: int = 86_400
    broadcast_rate_per_sec: int = 25

    # Webhook server
    webhook_enabled: bool = False
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8081
    webhook_public_url: str = ""
    webhook_base_path: str = "/payments"

    # CryptoBot
    cryptobot_token: str = ""
    cryptobot_asset: str = "USDT"
    cryptobot_testnet: bool = False

    # Lava
    lava_secret_key: str = ""
    lava_shop_id: str = ""
    lava_success_url: str = ""
    lava_fail_url: str = ""

    @cached_property
    def superadmin_ids(self) -> list[int]:
        return _parse_ids(self.superadmin_ids_raw) + _parse_ids(self.admin_ids_raw)

    @cached_property
    def manager_ids(self) -> list[int]:
        return _parse_ids(self.manager_ids_raw)

    @cached_property
    def support_ids(self) -> list[int]:
        return _parse_ids(self.support_ids_raw)

    @cached_property
    def admin_ids(self) -> list[int]:
        """Union of all roles — used for legacy admin-only paths."""
        return list(dict.fromkeys(self.superadmin_ids + self.manager_ids + self.support_ids))

    def role_of(self, user_id: int) -> str | None:
        if user_id in self.superadmin_ids:
            return "superadmin"
        if user_id in self.manager_ids:
            return "manager"
        if user_id in self.support_ids:
            return "support"
        return None

    def webhook_url_for(self, provider_code: str) -> str | None:
        if not (self.webhook_enabled and self.webhook_public_url):
            return None
        base = self.webhook_public_url.rstrip("/")
        path = self.webhook_base_path.strip("/")
        return f"{base}/{path}/{provider_code}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
