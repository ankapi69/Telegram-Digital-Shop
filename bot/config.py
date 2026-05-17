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

    @cached_property
    def admin_ids(self) -> list[int]:
        return [
            int(part)
            for part in self.admin_ids_raw.split(",")
            if part.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
