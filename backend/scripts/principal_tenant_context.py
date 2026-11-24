"""Protected tenant binding for release-principal lifecycle scripts."""

from __future__ import annotations

import os
from uuid import UUID

from app.database.tenant_context import (
    clear_database_tenant_context,
    set_database_tenant_context,
)


def establish_protected_company_context(company_id: UUID) -> None:
    """Seed canonical RLS context after validating the protected binding.

    Principal provisioning is a protected release operation.  The company ID
    supplied by a caller is accepted only when it matches the protected smoke
    company binding injected by the release environment.  The application
    authorization layer still validates the authenticated principal's active
    membership for reader provisioning.
    """

    configured = os.environ.get("SMOKE_COMPANY_ID")
    if not configured:
        raise RuntimeError("SMOKE_COMPANY_ID protected binding is required.")
    try:
        configured_id = UUID(configured)
    except ValueError as exc:
        raise RuntimeError("SMOKE_COMPANY_ID protected binding is invalid.") from exc
    if configured_id != company_id:
        raise PermissionError("Company does not match the protected release binding.")
    set_database_tenant_context(company_id)


def clear_protected_company_context() -> None:
    """Clear task-local context so pooled sessions cannot inherit a tenant."""

    clear_database_tenant_context()
