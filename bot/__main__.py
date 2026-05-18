import asyncio

from loguru import logger

from bot.config import get_settings
from bot.main import run, run_migrations
from bot.utils.logging import configure_logging


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("running alembic upgrade head")
    run_migrations(settings.database_url)
    asyncio.run(run())


if __name__ == "__main__":
    main()
