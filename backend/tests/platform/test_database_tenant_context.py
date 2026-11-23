from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

import pytest
from app.database.tenant_context import (
    DatabaseTenantContext,
    clear_database_tenant_context,
    get_database_tenant_context,
    set_database_tenant_context,
)
from app.database.tenant_context_middleware import DatabaseTenantContextMiddleware
from starlette.types import Message, Receive, Scope, Send


def test_database_tenant_context_is_explicit_and_clearable() -> None:
    company_id = uuid4()
    branch_id = uuid4()

    set_database_tenant_context(company_id, (branch_id,))
    context = get_database_tenant_context()

    assert context is not None
    assert context.company_id == company_id
    assert context.branch_ids == (branch_id,)

    clear_database_tenant_context()
    assert get_database_tenant_context() is None


@pytest.mark.asyncio
async def test_middleware_clears_context_after_request() -> None:
    company_id = uuid4()
    branch_id = uuid4()
    observed: list[object] = []

    async def application(scope: Scope, receive: Receive, send: Send) -> None:
        del scope, receive, send
        observed.append(get_database_tenant_context())

    async def receive() -> Message:
        return {"type": "http.request"}

    async def send(message: Message) -> None:
        del message

    middleware = DatabaseTenantContextMiddleware(application)
    await middleware(
        {
            "type": "http",
            "headers": [
                (b"x-company-id", str(company_id).encode()),
                (b"x-branch-id", str(branch_id).encode()),
            ],
        },
        receive,
        send,
    )

    context = cast(DatabaseTenantContext, observed[0])
    assert context.company_id == UUID(str(company_id))
    assert get_database_tenant_context() is None


@pytest.mark.asyncio
async def test_invalid_header_does_not_create_tenant_context() -> None:
    observed: list[object] = []

    async def application(scope: Scope, receive: Receive, send: Send) -> None:
        del scope, receive, send
        observed.append(get_database_tenant_context())

    async def receive() -> Message:
        return {"type": "http.request"}

    async def send(message: Message) -> None:
        del message

    middleware = DatabaseTenantContextMiddleware(application)
    await middleware(
        {"type": "http", "headers": [(b"x-company-id", b"not-a-uuid")]},
        receive,
        send,
    )

    assert observed == [None]
    assert get_database_tenant_context() is None
