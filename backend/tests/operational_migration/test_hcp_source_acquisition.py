from datetime import datetime, timezone

import pytest

from app.operational_migration.hcp_source_acquisition import (
    AcquisitionMechanism,
    SnapshotIdentity,
    SourceAssertion,
    SourceRelationship,
    evidence_key,
    preserve_conflict,
    seal_source_envelope,
    sha256,
)


def snapshot() -> SnapshotIdentity:
    now = datetime(2026, 8, 26, 15, tzinfo=timezone.utc)
    return SnapshotIdentity(
        "fixture-snapshot-1", now, AcquisitionMechanism.PUBLIC_API, "fixture",
        "all-pages", now, now, 1, 1, "a" * 64
    )


def test_envelope_preserves_provider_payload_exactly() -> None:
    payload = {"id": "job_1", "status": "open", "assigned_employee_ids": []}
    envelope = seal_source_envelope(
        native_entity="job", native_id="job_1", raw_payload=payload,
        snapshot=snapshot(), source_status="open"
    )
    assert envelope.provider == "housecall_pro"
    assert envelope.raw_payload == payload
    assert envelope.source_status == "open"
    assert envelope.source_digest == sha256(payload)


def test_missing_relationship_is_not_fabricated() -> None:
    with pytest.raises(ValueError, match="never fabricated"):
        seal_source_envelope(
            native_entity="job", native_id="job_1", raw_payload={"id": "job_1"},
            snapshot=snapshot(),
            relationships=(SourceRelationship("customer", "customer", None),),
        )


def test_hcp_and_qbo_assertions_both_survive_conflict() -> None:
    assertions = preserve_conflict(
        SourceAssertion("quickbooks_online", "invoice", "q1", "status", "open", "b" * 64),
        SourceAssertion("housecall_pro", "invoice", "h1", "status", "paid", "a" * 64),
    )
    assert [(a.provider, a.original_value) for a in assertions] == [
        ("housecall_pro", "paid"), ("quickbooks_online", "open")
    ]


def test_reconciliation_key_rejects_name_only_matching() -> None:
    with pytest.raises(ValueError, match="non-name corroborator"):
        evidence_key(entity="customer", provider="housecall_pro", native_id="c1", corroborators={"name": "Pat"})
    assert evidence_key(
        entity="invoice", provider="housecall_pro", native_id="i1",
        corroborators={"invoice_number": "100", "amount_minor": 12500},
    ) == evidence_key(
        entity="invoice", provider="housecall_pro", native_id="i1",
        corroborators={"amount_minor": 12500, "invoice_number": "100"},
    )
