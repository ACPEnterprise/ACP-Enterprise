"""Request-scoped database tenant context for PostgreSQL RLS.

The application authorization layer remains authoritative.  This module only
projects an already requested/authorized context into ``SET LOCAL`` settings
when a database transaction begins.  ``SET LOCAL`` is intentional: pooled
connections cannot retain a tenant after commit or rollback.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class DatabaseTenantContext:
    company_id: UUID
    branch_ids: tuple[UUID, ...] = ()


_current_context: ContextVar[DatabaseTenantContext | None] = ContextVar(
    "database_tenant_context", default=None
)


def set_database_tenant_context(
    company_id: UUID, branch_ids: tuple[UUID, ...] = ()
) -> None:
    """Set the context for the current request/task.

    Callers must provide IDs obtained from the authorization service.  The
    middleware may set a preliminary company context from the request header so
    authorization reads are tenant-bounded; the authorization dependency then
    replaces it with the verified branch set.
    """

    _current_context.set(
        DatabaseTenantContext(company_id=company_id, branch_ids=tuple(branch_ids))
    )


def clear_database_tenant_context() -> None:
    _current_context.set(None)


def get_database_tenant_context() -> DatabaseTenantContext | None:
    return _current_context.get()
