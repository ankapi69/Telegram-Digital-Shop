from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def build_engine(database_url: str) -> AsyncEngine:
    is_sqlite = database_url.startswith("sqlite")
    kwargs: dict = {"echo": False, "future": True}
    if not is_sqlite:
        kwargs.update(
            pool_size=20,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
    return create_async_engine(database_url, **kwargs)


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
