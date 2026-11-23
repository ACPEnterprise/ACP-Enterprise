"""Bootstrap and clear request-scoped database tenant context."""

from __future__ import annotations

from uuid import UUID

from starlette.types import ASGIApp, Receive, Scope, Send

from app.database.tenant_context import (
    clear_database_tenant_context,
    set_database_tenant_context,
)


class DatabaseTenantContextMiddleware:
    """Seed a bounded preliminary context and always clear it after a request.

    The preliminary header value is not authorization.  It only bounds the
    pre-authentication database reads; ``authorization_service.resolve`` still
    decides whether the caller may use the requested company and branch.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1"): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        company_value = headers.get("x-company-id")
        branch_value = headers.get("x-branch-id")
        try:
            company_id = UUID(company_value) if company_value else None
            branch_id = UUID(branch_value) if branch_value else None
        except ValueError:
            company_id = None
            branch_id = None

        if company_id is not None:
            set_database_tenant_context(
                company_id, (branch_id,) if branch_id is not None else ()
            )
        else:
            clear_database_tenant_context()

        try:
            await self.app(scope, receive, send)
        finally:
            clear_database_tenant_context()
