from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
)

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_database_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide the request's application session to routers and services."""
    async with AsyncSessionFactory() as session:
        yield session


async def get_security_database_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated request-scoped session for authentication reads."""
    async with AsyncSessionFactory() as session:
        yield session
