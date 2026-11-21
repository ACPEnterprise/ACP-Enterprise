from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Self
from uuid import UUID

import pytest

from scripts import apply_hcp_customer_roster_correction as correction

COMPANY_ID = UUID("00000000-0000-0000-0000-000000000001")
OTHER_COMPANY_ID = UUID("00000000-0000-0000-0000-000000000002")
BRANCH_ID = UUID("00000000-0000-0000-0000-000000000003")
ACTOR_ID = UUID("00000000-0000-0000-0000-000000000004")


def _record(source_id: str, display_name: str) -> SimpleNamespace:
    return SimpleNamespace(
        source_id=source_id,
        customer=SimpleNamespace(display_name=display_name),
    )


def _identity(source_id: str, customer_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        source_customer_id=source_id,
        customer_id=UUID(int=customer_id),
        created_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )


class _ScalarResult:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def all(self) -> list[object]:
        return self._values


class _ReadOnlySession:
    def __init__(self, scalar_results: list[list[object]]) -> None:
        self.scalar_results = scalar_results
        self.executed: list[str] = []
        self.rolled_back = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, statement: object) -> None:
        self.executed.append(str(statement))

    async def scalars(self, _statement: object) -> _ScalarResult:
        return _ScalarResult(self.scalar_results.pop(0))

    async def rollback(self) -> None:
        self.rolled_back = True

    def add(self, _value: object) -> None:
        raise AssertionError("preflight attempted an ORM write")

    async def flush(self) -> None:
        raise AssertionError("preflight attempted to flush")


@pytest.mark.asyncio
async def test_preflight_is_read_only_and_classifies_exact_bindings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = {
        "tenant-defect": _record("tenant-defect", "Richard Ratliff"),
        "native-hold": _record("native-hold", "Native Change"),
        "missing": _record("missing", "Missing Native"),
        "cross-tenant": _record("cross-tenant", "Cross Tenant"),
        "pre-binding": _record("pre-binding", "Older Native Change"),
        "unbound": _record("unbound", "New Customer"),
    }
    identities = [
        _identity("tenant-defect", 11),
        _identity("native-hold", 12),
        _identity("missing", 13),
        _identity("cross-tenant", 14),
        _identity("provider-only", 15),
        _identity("pre-binding", 16),
    ]
    customers = [
        SimpleNamespace(
            id=UUID(int=11),
            company_id=COMPANY_ID,
            display_name="All County Plumbing and Leak",
        ),
        SimpleNamespace(
            id=UUID(int=12),
            company_id=COMPANY_ID,
            display_name="Native Change",
        ),
        SimpleNamespace(
            id=UUID(int=14),
            company_id=OTHER_COMPANY_ID,
            display_name="Cross Tenant",
        ),
        SimpleNamespace(
            id=UUID(int=15),
            company_id=COMPANY_ID,
            display_name="Provider Only",
        ),
        SimpleNamespace(
            id=UUID(int=16),
            company_id=COMPANY_ID,
            display_name="Older Native Change",
        ),
    ]
    binding_time = identities[0].created_at
    session = _ReadOnlySession(
        [
            identities,
            customers,
            [
                SimpleNamespace(
                    entity_id=UUID(int=11),
                    occurred_at=binding_time + timedelta(days=1),
                ),
                SimpleNamespace(
                    entity_id=UUID(int=12),
                    occurred_at=binding_time - timedelta(days=1),
                ),
                SimpleNamespace(
                    entity_id=UUID(int=12),
                    occurred_at=binding_time + timedelta(days=1),
                ),
                SimpleNamespace(
                    entity_id=UUID(int=16),
                    occurred_at=binding_time - timedelta(days=1),
                ),
            ],
        ]
    )
    report = SimpleNamespace(
        source=5464,
        accepted=6,
        rejected=5458,
        duplicate=0,
        transformation_sha256="transformation-digest",
        child_exceptions=(),
    )
    args = argparse.Namespace(
        company_id=COMPANY_ID,
        branch_id=BRANCH_ID,
        actor_id=ACTOR_ID,
    )

    monkeypatch.setattr(
        correction,
        "_load_source",
        lambda _args: ("source-digest", report, records),
    )
    monkeypatch.setattr(correction, "AsyncSessionFactory", lambda: session)

    async def accepted_context(*_args: object, **_kwargs: object) -> object:
        return object()

    monkeypatch.setattr(correction, "_context", accepted_context)

    result = await correction.preflight(args)

    assert session.executed == [correction.READ_ONLY_TRANSACTION]
    assert session.rolled_back is True
    assert result["read_only"] is True
    assert result["authority"] == {
        "actor_id": str(ACTOR_ID),
        "branch_id": str(BRANCH_ID),
        "company_id": str(COMPANY_ID),
        "validated": True,
    }
    assert result["counts"] == {
        "cross_tenant_native_records": 1,
        "missing_native_records": 1,
        "newer_native_change_holds": 1,
        "provider_identities_absent_from_csv": 1,
        "provider_identities_total": 6,
        "source_bound": 5,
        "source_bound_cross_tenant_native_records": 1,
        "source_bound_eligible_for_update": 2,
        "source_bound_missing_native_records": 1,
        "source_unbound": 1,
        "tenant_defect_overrides": 1,
        "tenant_defect_records": 1,
    }


def test_shared_customer_events_are_compared_to_each_provider_binding() -> None:
    customer_id = UUID(int=21)
    first_binding = datetime(2026, 11, 1, tzinfo=timezone.utc)
    event_time = first_binding + timedelta(days=1)
    identities = (
        SimpleNamespace(
            source_customer_id="older-binding",
            customer_id=customer_id,
            created_at=first_binding,
        ),
        SimpleNamespace(
            source_customer_id="newer-binding",
            customer_id=customer_id,
            created_at=event_time + timedelta(days=1),
        ),
    )
    events = (SimpleNamespace(entity_id=customer_id, occurred_at=event_time),)

    newer_source_ids = correction._newer_native_source_ids(
        identities=identities,
        events=events,
    )
    counts = correction._preflight_counts(
        records={
            "older-binding": _record("older-binding", "Shared Customer"),
            "newer-binding": _record("newer-binding", "Shared Customer"),
        },
        identities=identities,
        customers={
            customer_id: SimpleNamespace(
                id=customer_id,
                company_id=COMPANY_ID,
                display_name="Shared Customer",
            )
        },
        newer_native_source_ids=newer_source_ids,
        company_id=COMPANY_ID,
    )

    assert newer_source_ids == {"older-binding"}
    assert counts["newer_native_change_holds"] == 1
    assert counts["source_bound_eligible_for_update"] == 1


def test_source_loader_rejects_duplicate_accepted_provider_identities(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source_path = tmp_path / "customers.csv"
    source_path.write_bytes(b"sealed source")
    digest = hashlib.sha256(b"sealed source").hexdigest()
    report = SimpleNamespace(
        source=5464,
        accepted=2,
        rejected=5462,
        duplicate=0,
        records=(_record("duplicate", "One"), _record("duplicate", "Two")),
    )

    class Adapter:
        def transform(self, *_args: object, **_kwargs: object) -> object:
            return report

    monkeypatch.setattr(correction, "HousecallProCustomerExportAdapter", Adapter)

    with pytest.raises(ValueError, match="duplicate accepted provider identities"):
        correction._load_source(argparse.Namespace(source=source_path, sha256=digest))


def test_parser_exposes_explicit_preflight_mode() -> None:
    args = correction.parser().parse_args(
        [
            "--source",
            "customers.csv",
            "--sha256",
            "digest",
            "--company-id",
            str(COMPANY_ID),
            "--branch-id",
            str(BRANCH_ID),
            "--actor-id",
            str(ACTOR_ID),
            "--preflight",
        ]
    )

    assert args.preflight is True
