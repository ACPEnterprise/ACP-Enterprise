from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.qbo_source.contracts import (
    AcquisitionRequest,
    EntityKind,
    QboSourceEnvelope,
    SnapshotIdentity,
)
from app.qbo_source.evidence import (
    ControlEvidenceRegistration,
    ControlEvidenceRegistry,
    ControlReportKind,
    EvidenceStoreError,
    ProtectedFilesystemEvidenceStore,
    RunState,
)
from app.qbo_source.intuit import PageEvidence
from app.qbo_source.runner import AcquisitionRunner


def snapshot() -> SnapshotIdentity:
    return SnapshotIdentity(
        snapshot_id="synthetic-snapshot",
        realm_id="synthetic-realm",
        environment="sandbox",
        accounting_date_cutoff=date(2026, 8, 25),
        cutoff_timezone="America/New_York",
        started_at=datetime(2026, 8, 26, 12, tzinfo=timezone.utc),
        api_minor_version=75,
    )


def envelope(native_id: str, *, acquired_minute: int = 1) -> QboSourceEnvelope:
    return QboSourceEnvelope.from_native(
        snapshot=snapshot(),
        native_entity_type="invoice",
        native_id=native_id,
        payload={
            "Id": native_id,
            "SyncToken": "1",
            "Balance": 25,
            "LinkedTxn": [{"TxnId": "synthetic-payment"}],
        },
        sync_token="1",
        acquired_at=datetime(2026, 8, 26, 12, acquired_minute, tzinfo=timezone.utc),
        relationship_ids=("LinkedTxn:synthetic-payment",),
        source_status="open",
        source_accounting_meaning={"Balance": 25},
    )


def evidence_store(
    root: Path, repository_root: Path
) -> ProtectedFilesystemEvidenceStore:
    return ProtectedFilesystemEvidenceStore(root=root, repository_root=repository_root)


def test_store_rejects_repository_path_and_open_permissions(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    with pytest.raises(EvidenceStoreError, match="inside_repository"):
        evidence_store(repository / "evidence", repository)
    open_root = tmp_path / "open-evidence"
    open_root.mkdir(mode=0o755)
    os.chmod(open_root, 0o755)
    with pytest.raises(EvidenceStoreError, match="permissions_too_open"):
        evidence_store(open_root, repository)


def test_immutable_store_is_resumable_deduplicated_and_deterministic(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    store = evidence_store(tmp_path / "protected", repository)
    store.begin_run(
        run_id="synthetic-run", snapshot=snapshot(), company_name="Synthetic Company"
    )
    second = store.store_envelope(
        run_id="synthetic-run", envelope=envelope("synthetic-invoice-2")
    )
    first = store.store_envelope(
        run_id="synthetic-run", envelope=envelope("synthetic-invoice-1")
    )
    resumed = store.begin_run(
        run_id="synthetic-run", snapshot=snapshot(), company_name="Synthetic Company"
    )
    duplicate = store.store_envelope(
        run_id="synthetic-run",
        envelope=envelope("synthetic-invoice-1", acquired_minute=9),
    )
    raw_page = b'{"QueryResponse":{}}'
    store.record_page(
        run_id="synthetic-run",
        evidence=PageEvidence(
            entity_kind="invoice",
            page=1,
            start_position=1,
            returned_count=2,
            response_sha256=hashlib.sha256(raw_page).hexdigest(),
            request_id="synthetic-request",
        ),
        raw_body=raw_page,
    )
    digest = store.finish_run(
        run_id="synthetic-run",
        state=RunState.COMPLETE,
        ended_at=datetime(2026, 8, 26, 13, tzinfo=timezone.utc),
    )

    manifest_path = tmp_path / "protected/runs/synthetic-run/manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    assert resumed.state == RunState.IN_PROGRESS
    assert duplicate == first
    assert first != second
    assert hashlib.sha256(manifest_bytes).hexdigest() == digest
    assert manifest["entity_counts"] == {"invoice": 2}
    assert [row["native_id"] for row in manifest["entities"]] == [
        "synthetic-invoice-1",
        "synthetic-invoice-2",
    ]
    assert "Balance" not in manifest_bytes.decode()
    assert stat.S_IMODE((tmp_path / "protected").stat().st_mode) == 0o700
    assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o600


def test_duplicate_native_identity_with_changed_source_fails(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    store = evidence_store(tmp_path / "protected", repository)
    store.begin_run(run_id="run", snapshot=snapshot(), company_name="Synthetic")
    original = envelope("invoice")
    store.store_envelope(run_id="run", envelope=original)
    changed = QboSourceEnvelope.from_native(
        snapshot=snapshot(),
        native_entity_type="invoice",
        native_id="invoice",
        payload={"Id": "invoice", "Balance": 0},
        acquired_at=datetime(2026, 8, 26, 12, 3, tzinfo=timezone.utc),
    )
    with pytest.raises(EvidenceStoreError, match="duplicate_native_identity_conflict"):
        store.store_envelope(run_id="run", envelope=changed)


def test_control_registration_contains_metadata_not_raw_report(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    store = evidence_store(tmp_path / "protected", repository)
    registry = ControlEvidenceRegistry(store)

    digest = registry.register(
        ControlEvidenceRegistration(
            control_id="aug25-trial-balance",
            kind=ControlReportKind.TRIAL_BALANCE,
            raw_sha256="a" * 64,
            byte_size=12345,
            storage_reference="evidence://controls/aug25/trial-balance",
            report_end_date=date(2026, 8, 25),
            accounting_basis="Accrual",
            generated_at=None,
            safe_report_parameters={"basis": "Accrual", "end_date": "2026-08-25"},
        )
    )

    registration = (
        tmp_path / "protected/controls/aug25-trial-balance.json"
    ).read_bytes()
    assert hashlib.sha256(registration).hexdigest() == digest
    assert b"raw_sha256" in registration
    assert b"financial rows" not in registration


@pytest.mark.asyncio
async def test_runner_seals_partial_failure_without_source_mutation(
    tmp_path: Path,
) -> None:
    class PartialProvider:
        async def acquire(self, request):  # type: ignore[no-untyped-def]
            yield envelope("first")
            raise RuntimeError("synthetic provider failure with no raw values")

    repository = tmp_path / "repository"
    repository.mkdir()
    store = evidence_store(tmp_path / "protected", repository)
    runner = AcquisitionRunner(provider=PartialProvider(), evidence_store=store)

    result = await runner.run(
        run_id="partial-run",
        request=AcquisitionRequest(snapshot(), (EntityKind.INVOICE,)),
        company_name="Synthetic",
    )

    assert result.state == RunState.PARTIAL
    assert result.envelope_count == 1
    manifest = json.loads(
        (tmp_path / "protected/runs/partial-run/manifest.json").read_bytes()
    )
    assert manifest["failure_code"] == "acquisition_failed"
    assert manifest["entities"][0]["raw_sha256"] == envelope("first").raw_sha256
