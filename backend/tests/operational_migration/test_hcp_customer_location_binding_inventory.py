from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pytest
from app.operational_migration.hcp_customer_location_binding_inventory import (
    build_customer_location_binding_inventory,
)


class _Mappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.rows)


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def mappings(self) -> _Mappings:
        return _Mappings(self.rows)


class _Session:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.results = [
            _Result([]),
            _Result(
                [
                    {
                        "source_system": "housecall_pro_source4",
                        "source_customer_id": "cus_1",
                        "customer_id": UUID(int=4),
                        "branch_id": UUID(int=2),
                        "native_exists": True,
                        "company_scope_matches": True,
                    }
                ]
            ),
            _Result(
                [
                    {
                        "source_system": "housecall_pro_source4",
                        "source_location_id": "adr_1",
                        "service_location_id": UUID(int=5),
                        "customer_id": UUID(int=4),
                        "parent_source_system": "housecall_pro_source4",
                        "parent_source_customer_id": "cus_1",
                        "native_exists": True,
                        "native_parent_matches": True,
                        "company_scope_matches": True,
                    }
                ]
            ),
            _Result(
                [
                    {
                        "entity_kind": "service_location",
                        "source_record_id": "adr_hold",
                        "reason_code": "PARENT_MISSING",
                        "state": "HELD",
                    }
                ]
            ),
        ]

    async def execute(self, statement: object, parameters: object = None) -> _Result:
        self.statements.append(str(statement))
        return self.results.pop(0)


@pytest.mark.asyncio
async def test_inventory_exports_only_exact_persisted_bindings_read_only() -> None:
    session = _Session()
    result = await build_customer_location_binding_inventory(  # type: ignore[arg-type]
        session,
        company_id=UUID(int=1),
        branch_id=UUID(int=2),
        observed_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )

    assert session.statements[0] == "SET TRANSACTION READ ONLY"
    assert result["mutation_authority"] == "none"
    assert result["identity_method"] == "exact_persisted_source_identity_only"
    assert result["counts"] == {"customers": 1, "locations": 1, "holds": 1}
    assert result["customers"][0]["customer_id"] == str(UUID(int=4))
    assert result["locations"][0]["native_parent_matches"] is True
    assert len(result["digest"]) == 64
    statements = " ".join(session.statements).upper()
    assert not any(word in statements for word in ("INSERT ", "UPDATE ", "DELETE "))
    assert "DISPLAY_NAME" not in statements
    assert "ADDRESS" not in statements
