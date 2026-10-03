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
            _Result(
                [
                    {
                        "invoices": 2,
                        "customer_job_linked": 2,
                        "source_line_items": 4,
                        "open_ar_invoices": 1,
                        "open_ar_amount": "125.00",
                        "paid": 1,
                        "open_status": 1,
                    }
                ]
            ),
            _Result(
                [
                    {
                        "payment_assertions": 2,
                        "invoice_linked": 2,
                        "succeeded": 2,
                        "non_succeeded": 0,
                    }
                ]
            ),
            _Result(
                [
                    {
                        "parent_type": "job",
                        "registered": 3,
                        "available": 2,
                        "failed": 1,
                        "retryable": 1,
                    }
                ]
            ),
            _Result(
                [
                    {
                        "parent_type": "job",
                        "entry_type": "note",
                        "admitted": 5,
                        "unresolved_employee": 1,
                    }
                ]
            ),
            _Result(
                [
                    {
                        "source_identities": 7,
                        "canonical_bound": 6,
                        "terminated_or_excluded": 1,
                        "unresolved": 0,
                    }
                ]
            ),
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
    assert result["invoice_parity"] == {
        "invoices": 2,
        "customer_job_linked": 2,
        "source_line_items": 4,
        "open_ar_invoices": 1,
        "open_ar_amount": "125.00",
        "paid": 1,
        "open_status": 1,
    }
    assert result["payment_parity"]["invoice_linked"] == 2
    assert result["attachment_parity"]["by_parent_type"]["job"]["failed"] == 1
    assert result["employee_source_parity"]["canonical_bound"] == 6
    assert result["history_parity"]["by_parent_and_type"]["job:note"] == {
        "admitted": 5,
        "unresolved_employee": 1,
    }
    assert result["historical_customer_journeys"][0]["customer_id"] == str(UUID(int=4))
    assert len(result["digest"]) == 64
    assert not any(
        word in " ".join(session.statements).upper()
        for word in ("INSERT ", "UPDATE ", "DELETE ")
    )
    assert any(
        "owner.id = n.customer_id" in statement for statement in session.statements
    )
