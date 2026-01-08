from __future__ import annotations

from collections.abc import AsyncGenerator
from urllib.parse import urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


def make_database_url() -> str:
    """Build async MySQL connection URL.

    Priority:
    1. MYSQL_URL (Railway MySQL service)
    2. DATABASE_URL (generic)
    3. Individual MYSQL_* env vars (local development)
    """
    raw_url = settings.mysql_url or settings.database_url

    if raw_url:
        # Railway provides mysql://... but SQLAlchemy async needs mysql+aiomysql://...
        parsed = urlparse(raw_url)
        if parsed.scheme == "mysql":
            # Convert to async driver
            new_scheme = "mysql+aiomysql"
            parsed = parsed._replace(scheme=new_scheme)

        # Ensure charset is set
        url = urlunparse(parsed)
        if "?" not in url:
            url += "?charset=utf8mb4"
        elif "charset" not in url:
            url += "&charset=utf8mb4"
        return url

    # Fallback to individual env vars (local docker-compose)
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
