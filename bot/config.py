from functools import cached_property, lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    bot_token: str = Field(..., min_length=10)
    admin_ids_raw: str = Field(default="", alias="ADMIN_IDS")

    database_url: str = "sqlite+aiosqlite:///./shop.db"
    redis_url: str | None = None

    throttle_rate: float = 0.5
    log_level: str = "INFO"

    # --- Webhook server -------------------------------------------------
    webhook_enabled: bool = False
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8081
    # Public base URL of the webhook server, used to build hookUrl values
    # we hand to payment providers.  Empty disables webhooks even if
    # ``webhook_enabled`` is true (no point starting a server providers
    # can't reach).
    webhook_public_url: str = ""
    webhook_base_path: str = "/payments"

    # --- CryptoBot ------------------------------------------------------
    cryptobot_token: str = ""
    cryptobot_asset: str = "USDT"
    cryptobot_testnet: bool = False

    # --- Lava -----------------------------------------------------------
    lava_secret_key: str = ""
    lava_shop_id: str = ""
    lava_success_url: str = ""
    lava_fail_url: str = ""

    @cached_property
    def admin_ids(self) -> list[int]:
        return [
            int(part)
            for part in self.admin_ids_raw.split(",")
            if part.strip()
        ]

    def webhook_url_for(self, provider_code: str) -> str | None:
        """Return the public webhook URL for ``provider_code`` if the
        webhook server is configured, else ``None`` (manual check only)."""
        if not (self.webhook_enabled and self.webhook_public_url):
            return None
        base = self.webhook_public_url.rstrip("/")
        path = self.webhook_base_path.strip("/")
        return f"{base}/{path}/{provider_code}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
