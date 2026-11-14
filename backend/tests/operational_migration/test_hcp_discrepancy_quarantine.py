from app.operational_migration.hcp_discrepancy_quarantine import (
    QUARANTINE_REASON,
    _derive_records,
)


def _record(source_id: str, disposition: str = "REPLAY", parents=()):
    return {
        "domain": "estimate",
        "source_id": source_id,
        "disposition": disposition,
        "assertion": "create",
        "source_digest": "a" * 64,
        "acquired_at": "2026-11-01T00:00:00+00:00",
        "payload": {"source_id": source_id},
        "parent_keys": list(parents),
    }


def test_estimate_without_job_parent_is_quarantined_without_reclassification_loss():
    records, quarantined = _derive_records([_record("estimate-1")])

    assert len(quarantined) == 1
    assert quarantined[0]["source_id"] == "estimate-1"
    assert records[0]["disposition"] == "HOLD"
    assert records[0]["assertion"] == "hold"
    assert records[0]["source_disposition"] == "REPLAY"
    assert records[0]["reason"] == QUARANTINE_REASON


def test_estimate_with_job_parent_remains_executable():
    records, quarantined = _derive_records(
        [_record("estimate-1", parents=({"domain": "job", "source_id": "job-1"},))]
    )

    assert quarantined == []
    assert records[0]["disposition"] == "REPLAY"
    assert "source_disposition" not in records[0]


def test_existing_hold_is_preserved():
    existing = _record("estimate-held", disposition="HOLD")
    records, quarantined = _derive_records([existing])

    assert quarantined == []
    assert records == [existing]
