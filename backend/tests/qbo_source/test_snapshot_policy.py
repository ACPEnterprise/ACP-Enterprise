from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from app.qbo_source.contracts import (
    AcquisitionRequest,
    EntityKind,
    QboSourceEnvelope,
    SnapshotIdentity,
)
from app.qbo_source.evidence import ProtectedFilesystemEvidenceStore, RunState
from app.qbo_source.runner import AcquisitionRunner
from app.qbo_source.snapshot_policy import SNAPSHOT_POLICY_VERSION


def _snapshot() -> SnapshotIdentity:
    return SnapshotIdentity(
        snapshot_id="bounded-generation",
        realm_id="synthetic-realm",
        environment="production",
        accounting_date_cutoff=date(2026, 8, 31),
        cutoff_timezone="America/New_York",
        started_at=datetime(2026, 9, 1, 12, tzinfo=timezone.utc),
        api_minor_version=75,
    )


def _envelope(
    kind: str,
    native_id: str,
    payload: dict[str, object],
    *,
    updated_at: datetime | None = None,
) -> QboSourceEnvelope:
    return QboSourceEnvelope.from_native(
        snapshot=_snapshot(),
        native_entity_type=kind,
        native_id=native_id,
        payload={"Id": native_id, **payload},
        acquired_at=datetime(2026, 9, 1, 12, tzinfo=timezone.utc),
        source_updated_at=updated_at,
    )


def test_bounded_snapshot_preserves_raw_and_excludes_post_cutoff(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    store = ProtectedFilesystemEvidenceStore(
        root=tmp_path / "evidence",
        repository_root=repository,
        bounded_snapshot=True,
    )
    store.begin_run(
        run_id="bounded-generation", snapshot=_snapshot(), company_name="Synthetic"
    )
    for item in (
        _envelope("invoice", "before", {"TxnDate": "2026-08-30"}),
        _envelope(
            "invoice",
            "on-cutoff",
            {"TxnDate": "2026-08-31"},
            updated_at=datetime(2026, 9, 1, 13, tzinfo=timezone.utc),
        ),
        _envelope("deposit", "after", {"TxnDate": "2026-09-01"}),
        _envelope("customer", "current", {"Active": True}),
    ):
        store.store_envelope(run_id="bounded-generation", envelope=item)
    source_digest = store.finish_run(
        run_id="bounded-generation",
        state=RunState.COMPLETE,
        ended_at=datetime(2026, 9, 1, 14, tzinfo=timezone.utc),
    )

    run_root = tmp_path / "evidence/runs/bounded-generation"
    source = json.loads((run_root / "manifest.json").read_bytes())
    bounded_bytes = (run_root / "bounded-manifest.json").read_bytes()
    bounded = json.loads(bounded_bytes)
    assert (
        hashlib.sha256((run_root / "manifest.json").read_bytes()).hexdigest()
        == source_digest
    )
    assert source["entity_counts"] == {"customer": 1, "deposit": 1, "invoice": 2}
    assert source["snapshot_policy_version"] == SNAPSHOT_POLICY_VERSION
    assert (
        source["bounded_snapshot_sha256"] == hashlib.sha256(bounded_bytes).hexdigest()
    )
    assert store.bounded_snapshot_summary(run_id="bounded-generation") == {
        "state": "BOUNDED_COMPLETE",
        "snapshot_policy_version": SNAPSHOT_POLICY_VERSION,
        "bounded_snapshot_sha256": hashlib.sha256(bounded_bytes).hexdigest(),
        "post_cutoff_exclusion_sha256": bounded["exclusion_digest"],
        "excluded_post_cutoff_counts": {"deposit": 1},
        "maximum_included_transaction_dates": {"invoice": "2026-08-31"},
    }
    assert bounded["included_counts"] == {"customer": 1, "invoice": 2}
    assert bounded["state"] == "BOUNDED_COMPLETE"
    assert bounded["excluded_post_cutoff_counts"] == {"deposit": 1}
    assert bounded["maximum_included_transaction_dates"] == {"invoice": "2026-08-31"}
    assert bounded["excluded_post_cutoff"][0]["reason"] == "EXCLUDED_POST_CUTOFF"
    assert bounded["post_cutoff_source_modifications"][0]["classification"] == (
        "POST_CUTOFF_SOURCE_MODIFICATION"
    )
    assert bounded["per_family_policy"]["customer"]["classification"] == (
        "REFERENCE_MASTER_CURRENT"
    )
    assert bounded["per_family_policy"]["bill"]["classification"] == ("EMPTY_CONFIRMED")
    assert "after" not in json.dumps(bounded)
    assert (tmp_path / "evidence/blobs").is_dir()


@pytest.mark.asyncio
async def test_missing_authoritative_date_seals_partial(tmp_path: Path) -> None:
    class Provider:
        async def acquire(self, request):  # type: ignore[no-untyped-def]
            yield _envelope("invoice", "missing-date", {})

    repository = tmp_path / "repository"
    repository.mkdir()
    store = ProtectedFilesystemEvidenceStore(
        root=tmp_path / "evidence",
        repository_root=repository,
        bounded_snapshot=True,
    )
    result = await AcquisitionRunner(provider=Provider(), evidence_store=store).run(
        run_id="missing-date",
        request=AcquisitionRequest(_snapshot(), (EntityKind.INVOICE,)),
        company_name="Synthetic",
    )
    manifest = json.loads(
        (tmp_path / "evidence/runs/missing-date/manifest.json").read_bytes()
    )
    assert result.state is RunState.PARTIAL
    assert result.failure_code == "authoritative_transaction_date_missing"
    assert manifest["failure_evidence"]["error_classification"] == (
        "DATA_VALIDATION_FAILURE"
    )
