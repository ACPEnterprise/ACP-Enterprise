from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.tenant_context import get_database_tenant_context

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
)

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@event.listens_for(Session, "after_begin")
def _set_transaction_tenant_context(
    session: Session, transaction: object, connection: Connection
) -> None:
    """Project the request context into this transaction only.

    ``connection`` is a synchronous SQLAlchemy connection here because this
    listener runs on AsyncSession's underlying sync session.  No global or
    pooled-connection ``SET`` is used.
    """

    del session, transaction
    context = get_database_tenant_context()
    if context is None:
        return
    if context.company_id is not None:
        connection.execute(
            text("SELECT set_config('app.company_id', :company_id, true)"),
            {"company_id": str(context.company_id)},
        )
        connection.execute(
            text("SELECT set_config('app.branch_ids', :branch_ids, true)"),
            {"branch_ids": ",".join(str(value) for value in context.branch_ids)},
        )
    if context.user_id is not None:
        connection.execute(
            text("SELECT set_config('app.user_id', :user_id, true)"),
            {"user_id": str(context.user_id)},
        )


async def apply_database_tenant_context(session: AsyncSession) -> None:
    """Apply the current transaction-local context after a transaction began."""

    context = get_database_tenant_context()
    if context is None:
        return
    if context.company_id is not None:
        await session.execute(
            text("SELECT set_config('app.company_id', :company_id, true)"),
            {"company_id": str(context.company_id)},
        )
        await session.execute(
            text("SELECT set_config('app.branch_ids', :branch_ids, true)"),
            {"branch_ids": ",".join(str(value) for value in context.branch_ids)},
        )
    if context.user_id is not None:
        await session.execute(
            text("SELECT set_config('app.user_id', :user_id, true)"),
            {"user_id": str(context.user_id)},
        )


async def get_database_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide the request's application session to routers and services."""
    async with AsyncSessionFactory() as session:
        yield session


async def get_security_database_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated request-scoped session for authentication reads."""
    async with AsyncSessionFactory() as session:
        yield session
