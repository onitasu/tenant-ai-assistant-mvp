from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


def make_database_url() -> str:
    return (
        f"mysql+aiomysql://{settings.mysql_user}:{settings.mysql_password}"
        f"@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_db}"
        f"?charset=utf8mb4"
    )


engine = create_async_engine(
    make_database_url(),
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
