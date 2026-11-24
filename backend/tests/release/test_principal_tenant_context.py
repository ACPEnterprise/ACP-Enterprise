from __future__ import annotations

from uuid import UUID

import pytest
from app.database.tenant_context import get_database_tenant_context
from scripts.principal_tenant_context import (
    clear_protected_company_context,
    establish_protected_company_context,
)

COMPANY_ID = UUID("3ddf07ce-0f44-4b67-a40f-fb0ec41bb7cd")


def teardown_function() -> None:
    clear_protected_company_context()


def test_establishes_canonical_context_only_for_protected_company(monkeypatch):
    monkeypatch.setenv("SMOKE_COMPANY_ID", str(COMPANY_ID))

    establish_protected_company_context(COMPANY_ID)

    assert get_database_tenant_context() is not None
    assert get_database_tenant_context().company_id == COMPANY_ID
    assert get_database_tenant_context().branch_ids == ()


def test_rejects_company_that_does_not_match_protected_binding(monkeypatch):
    monkeypatch.setenv("SMOKE_COMPANY_ID", str(COMPANY_ID))

    with pytest.raises(PermissionError, match="protected release binding"):
        establish_protected_company_context(
            UUID("c36895cf-8a6f-5c31-a2ed-474dee8d0fc4")
        )

    assert get_database_tenant_context() is None


def test_requires_protected_company_binding(monkeypatch):
    monkeypatch.delenv("SMOKE_COMPANY_ID", raising=False)

    with pytest.raises(RuntimeError, match="protected binding is required"):
        establish_protected_company_context(COMPANY_ID)

    assert get_database_tenant_context() is None


def test_context_is_cleared_after_lifecycle(monkeypatch):
    monkeypatch.setenv("SMOKE_COMPANY_ID", str(COMPANY_ID))
    establish_protected_company_context(COMPANY_ID)

    clear_protected_company_context()

    assert get_database_tenant_context() is None
