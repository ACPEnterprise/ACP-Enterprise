from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pytest

from app.operational_migration.hcp_realworld_acceptance_snapshot import (
    build_realworld_snapshot,
)


class _Mappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def one(self) -> dict[str, Any]:
        assert len(self.rows) == 1
        return self.rows[0]

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
            *[_Result([{"admitted": 2, "projected": 2}]) for _ in range(7)],
            _Result([{"entity_kind": "job", "count": 3}]),
            _Result(
                [
                    {
                        "open_jobs": 1,
                        "future_appointments": 1,
                        "dispatch_graph_complete": 1,
                    }
                ]
            ),
            _Result(
                [
                    {
                        "source_customer_id": "cus_1",
                        "customer_id": UUID(int=4),
                        "customer_number": "CUS-000001",
                        "display_name": "Historical Customer",
                        "locations": 1,
                        "jobs": 2,
                        "appointments": 1,
                        "estimates": 1,
                        "invoices": 1,
                        "payments": 1,
                    }
                ]
            ),
        ]

    async def execute(self, statement: object, parameters: object = None) -> _Result:
        self.statements.append(str(statement))
        return self.results.pop(0)


@pytest.mark.asyncio
async def test_snapshot_is_read_only_and_accounts_native_continuity() -> None:
    session = _Session()
    result = await build_realworld_snapshot(  # type: ignore[arg-type]
        session,
        company_id=UUID(int=1),
        branch_id=UUID(int=2),
        observed_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
    )

    assert session.statements[0] == "SET TRANSACTION READ ONLY"
    assert result["mutation_authority"] == "none"
    assert result["families"]["customers"] == {
        "admitted": 2,
        "projected": 2,
        "missing_native_projection": 0,
    }
    assert result["held_by_entity_kind"] == {"job": 3}
    assert result["current_operations"]["dispatch_graph_complete"] == 1
    assert result["historical_customer_journeys"][0]["customer_id"] == str(UUID(int=4))
    assert len(result["digest"]) == 64
    assert not any(
        word in " ".join(session.statements).upper()
        for word in ("INSERT ", "UPDATE ", "DELETE ")
    )
    assert any(
        "owner.id = n.customer_id" in statement for statement in session.statements
    )
