from __future__ import annotations

import pytest
from app.operational_migration.hcp_continuous_delta import (
    NativeObservation,
    ProviderObservation,
    build_continuous_delta,
)
from app.operational_migration.hcp_source_completeness import (
    CompletenessDisposition,
    SourceIdentity,
    build_source_completeness,
)

CUTOFF = "2026-09-12T23:59:59Z"
ACQUIRED = "2026-10-03T12:00:00Z"


def observation(domain: str, source_id: str, digest: str) -> ProviderObservation:
    return ProviderObservation(
        domain=domain,
        source_id=source_id,
        source_digest=digest,
        acquired_at=ACQUIRED,
        source_updated_at="2026-10-02T12:00:00Z",
        payload={"id": source_id},
    )


def identity(row: ProviderObservation, version: str = "v1") -> SourceIdentity:
    return SourceIdentity(row.domain, row.source_id, version, row.source_digest)


def test_accounts_for_safe_majority_and_quarantines_only_conflict() -> None:
    created = observation("customer", "created", "1" * 64)
    updated = observation("job", "updated", "2" * 64)
    replay = observation("appointment", "replay", "3" * 64)
    conflict = observation("estimate", "conflict", "4" * 64)
    plan = build_continuous_delta(
        cutoff=CUTOFF,
        base_source4_digest="a" * 64,
        company_id="company",
        branch_id="branch",
        acquired_at=ACQUIRED,
        provider=(created, updated, replay, conflict),
        native={
            updated.key: NativeObservation(
                "5" * 64, "2026-09-20T12:00:00Z", "2026-09-20T12:00:00Z"
            ),
            replay.key: NativeObservation(
                "3" * 64, "2026-09-20T12:00:00Z", "2026-09-20T12:00:00Z"
            ),
            conflict.key: NativeObservation(
                "6" * 64, "2026-09-20T12:00:00Z", "2026-09-20T12:00:00Z"
            ),
        },
    )
    result = build_source_completeness(
        cutoff=CUTOFF,
        acquired_at=ACQUIRED,
        source=tuple(identity(row) for row in (created, updated, replay, conflict)),
        delta=plan,
    )

    assert result.unexplained_provider_gaps == 0
    assert [row.disposition for row in result.records] == [
        CompletenessDisposition.REPLAY,
        CompletenessDisposition.CREATE,
        CompletenessDisposition.CONFLICT,
        CompletenessDisposition.UPDATE,
    ]
    assert sum(row.source for row in result.domains) == 4


def test_reports_missing_disposition_as_unexplained_gap() -> None:
    row = observation("invoice", "invoice-1", "1" * 64)
    empty = build_continuous_delta(
        cutoff=CUTOFF,
        base_source4_digest="a" * 64,
        company_id="company",
        branch_id="branch",
        acquired_at=ACQUIRED,
        provider=(),
        native={},
    )
    result = build_source_completeness(
        cutoff=CUTOFF,
        acquired_at=ACQUIRED,
        source=(identity(row),),
        delta=empty,
    )
    invoice = next(value for value in result.domains if value.domain == "invoice")
    assert invoice.source == 1
    assert invoice.unexplained == 1
    assert result.unexplained_provider_gaps == 1


def test_rejects_duplicate_provider_identity_and_extra_delta_identity() -> None:
    row = observation("customer", "same", "1" * 64)
    plan = build_continuous_delta(
        cutoff=CUTOFF,
        base_source4_digest="a" * 64,
        company_id="company",
        branch_id="branch",
        acquired_at=ACQUIRED,
        provider=(row,),
        native={},
    )
    with pytest.raises(ValueError, match="unique"):
        build_source_completeness(
            cutoff=CUTOFF,
            acquired_at=ACQUIRED,
            source=(identity(row), identity(row)),
            delta=plan,
        )
    with pytest.raises(ValueError, match="absent"):
        build_source_completeness(
            cutoff=CUTOFF,
            acquired_at=ACQUIRED,
            source=(),
            delta=plan,
        )


def test_digest_and_source_versions_are_replay_stable() -> None:
    row = observation("payment", "payment-1", "1" * 64)
    plan = build_continuous_delta(
        cutoff=CUTOFF,
        base_source4_digest="a" * 64,
        company_id="company",
        branch_id="branch",
        acquired_at=ACQUIRED,
        provider=(row,),
        native={},
    )
    values = (identity(row, "provider-v7"),)
    first = build_source_completeness(
        cutoff=CUTOFF, acquired_at=ACQUIRED, source=values, delta=plan
    )
    second = build_source_completeness(
        cutoff=CUTOFF, acquired_at=ACQUIRED, source=values, delta=plan
    )
    assert first == second
    payment = next(value for value in first.domains if value.domain == "payment")
    assert payment.source_versions == ("provider-v7",)
