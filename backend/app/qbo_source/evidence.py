from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Protocol

from .contracts import QboSourceEnvelope, SnapshotIdentity, _json_domain
from .intuit import CatalogDispositionEvidence, PageEvidence, PageObserver
from .snapshot_policy import build_bounded_snapshot


class EvidenceStoreError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RunState(str, Enum):
    IN_PROGRESS = "in_progress"
    PARTIAL = "partial"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True)
class AcquisitionRun:
    run_id: str
    snapshot: SnapshotIdentity
    company_name: str
    started_at: datetime
    state: RunState


@dataclass(frozen=True)
class StoredEnvelope:
    entity_kind: str
    native_id: str
    envelope_sha256: str
    raw_sha256: str


@dataclass(frozen=True)
class AcquisitionFailureEvidence:
    schema_version: str
    catalog_version: str
    acquisition_generation: str
    entity_kind: str | None
    query_classification: str
    page: int | None
    provider_status_classification: str
    error_classification: str
    retryable: bool
    catalog_requirement: str
    occurred_at: str
    correlation_id: str


class EvidenceStore(Protocol):
    def begin_run(
        self, *, run_id: str, snapshot: SnapshotIdentity, company_name: str
    ) -> AcquisitionRun: ...

    def store_envelope(
        self, *, run_id: str, envelope: QboSourceEnvelope
    ) -> StoredEnvelope: ...

    def finish_run(
        self,
        *,
        run_id: str,
        state: RunState,
        ended_at: datetime,
        failure_code: str | None = None,
        failure_evidence: AcquisitionFailureEvidence | None = None,
    ) -> str: ...


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _snapshot_document(snapshot: SnapshotIdentity) -> dict[str, object]:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "realm_id": snapshot.realm_id,
        "environment": snapshot.environment,
        "accounting_date_cutoff": snapshot.accounting_date_cutoff.isoformat(),
        "cutoff_timezone": snapshot.cutoff_timezone,
        "started_at": snapshot.started_at.isoformat(),
        "api_minor_version": snapshot.api_minor_version,
    }


def _envelope_document(envelope: QboSourceEnvelope) -> dict[str, object]:
    return {
        "schema_version": envelope.schema_version,
        "provider": envelope.provider,
        "snapshot": _snapshot_document(envelope.snapshot),
        "native_entity_type": envelope.native_entity_type,
        "native_id": envelope.native_id,
        "sync_token": envelope.sync_token,
        "source_created_at": (
            envelope.source_created_at.isoformat()
            if envelope.source_created_at
            else None
        ),
        "source_updated_at": (
            envelope.source_updated_at.isoformat()
            if envelope.source_updated_at
            else None
        ),
        "acquired_at": envelope.acquired_at.isoformat(),
        "raw_sha256": envelope.raw_sha256,
        "relationship_ids": list(envelope.relationship_ids),
        "currency": envelope.currency,
        "source_status": envelope.source_status,
        "source_accounting_meaning": dict(envelope.source_accounting_meaning),
    }


class ProtectedFilesystemEvidenceStore(EvidenceStore):
    """Restricted, content-addressed store. Raw payloads never enter manifests."""

    def __init__(
        self, *, root: Path, repository_root: Path, bounded_snapshot: bool = False
    ) -> None:
        self.root = root.expanduser().resolve()
        repository = repository_root.expanduser().resolve()
        if self.root == repository or repository in self.root.parents:
            raise EvidenceStoreError("evidence_root_inside_repository")
        if self.root.exists():
            mode = stat.S_IMODE(self.root.stat().st_mode)
            if mode & 0o077:
                raise EvidenceStoreError("evidence_root_permissions_too_open")
        else:
            self.root.mkdir(parents=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.bounded_snapshot = bounded_snapshot
        for name in ("blobs", "envelopes", "runs", "controls"):
            path = self.root / name
            path.mkdir(mode=0o700, exist_ok=True)
            os.chmod(path, 0o700)

    def begin_run(
        self, *, run_id: str, snapshot: SnapshotIdentity, company_name: str
    ) -> AcquisitionRun:
        _safe_identity(run_id)
        run_dir = self.root / "runs" / run_id
        state_path = run_dir / "state.json"
        if state_path.exists():
            state = self._read_json(state_path)
            if state.get("snapshot") != _snapshot_document(snapshot):
                raise EvidenceStoreError("run_snapshot_conflict")
            if state.get("company_name") != company_name:
                raise EvidenceStoreError("run_company_conflict")
            return AcquisitionRun(
                run_id=run_id,
                snapshot=snapshot,
                company_name=company_name,
                started_at=datetime.fromisoformat(str(state["started_at"])),
                state=RunState(str(state["state"])),
            )
        run_dir.mkdir(mode=0o700)
        started_at = datetime.now(timezone.utc)
        state = {
            "schema_version": "qbo-acquisition-run/v1",
            "run_id": run_id,
            "snapshot": _snapshot_document(snapshot),
            "company_name": company_name,
            "started_at": started_at.isoformat(),
            "ended_at": None,
            "state": RunState.IN_PROGRESS.value,
            "failure_code": None,
            "entities": {},
            "pages": [],
            "catalog_dispositions": [],
        }
        self._replace_json(state_path, state)
        return AcquisitionRun(
            run_id=run_id,
            snapshot=snapshot,
            company_name=company_name,
            started_at=started_at,
            state=RunState.IN_PROGRESS,
        )

    def store_envelope(
        self, *, run_id: str, envelope: QboSourceEnvelope
    ) -> StoredEnvelope:
        state_path = self._state_path(run_id)
        state = self._read_json(state_path)
        if state["state"] != RunState.IN_PROGRESS.value:
            raise EvidenceStoreError("run_not_writable")
        if state["snapshot"] != _snapshot_document(envelope.snapshot):
            raise EvidenceStoreError("envelope_snapshot_conflict")
        raw_bytes = _canonical_json(_json_domain(envelope.raw_payload))
        if hashlib.sha256(raw_bytes).hexdigest() != envelope.raw_sha256:
            raise EvidenceStoreError("raw_digest_conflict")
        self._store_blob(envelope.raw_sha256, raw_bytes)
        envelope_bytes = _canonical_json(_envelope_document(envelope))
        envelope_digest = hashlib.sha256(envelope_bytes).hexdigest()
        self._store_named_immutable(
            self.root / "envelopes" / f"{envelope_digest}.json", envelope_bytes
        )
        entity_key = f"{envelope.native_entity_type}:{envelope.native_id}"
        entities = state.get("entities")
        if not isinstance(entities, dict):
            raise EvidenceStoreError("run_state_invalid")
        existing = entities.get(entity_key)
        record = {
            "entity_kind": envelope.native_entity_type,
            "native_id": envelope.native_id,
            "sync_token": envelope.sync_token,
            "envelope_sha256": envelope_digest,
            "raw_sha256": envelope.raw_sha256,
        }
        if existing is not None:
            if (
                not isinstance(existing, dict)
                or existing.get("raw_sha256") != envelope.raw_sha256
            ):
                raise EvidenceStoreError("duplicate_native_identity_conflict")
            return StoredEnvelope(
                entity_kind=str(existing["entity_kind"]),
                native_id=str(existing["native_id"]),
                envelope_sha256=str(existing["envelope_sha256"]),
                raw_sha256=str(existing["raw_sha256"]),
            )
        entities[entity_key] = record
        self._replace_json(state_path, state)
        return StoredEnvelope(
            entity_kind=envelope.native_entity_type,
            native_id=envelope.native_id,
            envelope_sha256=envelope_digest,
            raw_sha256=envelope.raw_sha256,
        )

    def record_page(
        self, *, run_id: str, evidence: PageEvidence, raw_body: bytes
    ) -> None:
        if hashlib.sha256(raw_body).hexdigest() != evidence.response_sha256:
            raise EvidenceStoreError("page_digest_conflict")
        self._store_blob(evidence.response_sha256, raw_body)
        state_path = self._state_path(run_id)
        state = self._read_json(state_path)
        if state["state"] != RunState.IN_PROGRESS.value:
            raise EvidenceStoreError("run_not_writable")
        record = {
            **asdict(evidence),
            "raw_blob_sha256": evidence.response_sha256,
        }
        pages = state.get("pages")
        if not isinstance(pages, list):
            raise EvidenceStoreError("run_state_invalid")
        key = (evidence.entity_kind, evidence.page, evidence.start_position)
        matching = [
            page
            for page in pages
            if (page["entity_kind"], page["page"], page["start_position"]) == key
        ]
        if matching and matching[0] != record:
            raise EvidenceStoreError("page_checkpoint_conflict")
        if not matching:
            pages.append(record)
        self._replace_json(state_path, state)

    def record_catalog_disposition(
        self, *, run_id: str, evidence: CatalogDispositionEvidence
    ) -> None:
        state_path = self._state_path(run_id)
        state = self._read_json(state_path)
        if state["state"] != RunState.IN_PROGRESS.value:
            raise EvidenceStoreError("run_not_writable")
        dispositions = state.get("catalog_dispositions")
        if not isinstance(dispositions, list):
            raise EvidenceStoreError("run_state_invalid")
        record = asdict(evidence)
        matching = [
            item
            for item in dispositions
            if item.get("entity_kind") == evidence.entity_kind
        ]
        if matching and matching[0] != record:
            raise EvidenceStoreError("catalog_disposition_conflict")
        if not matching:
            dispositions.append(record)
        self._replace_json(state_path, state)

    def finish_run(
        self,
        *,
        run_id: str,
        state: RunState,
        ended_at: datetime,
        failure_code: str | None = None,
        failure_evidence: AcquisitionFailureEvidence | None = None,
    ) -> str:
        if state == RunState.IN_PROGRESS or ended_at.tzinfo is None:
            raise ValueError("terminal state and timezone-aware end are required")
        state_path = self._state_path(run_id)
        document = self._read_json(state_path)
        if document["state"] != RunState.IN_PROGRESS.value:
            manifest_path = self.root / "runs" / run_id / "manifest.json"
            return hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        document["state"] = state.value
        document["ended_at"] = ended_at.isoformat()
        document["failure_code"] = failure_code
        document["failure_evidence"] = (
            asdict(failure_evidence) if failure_evidence is not None else None
        )
        entities = document.pop("entities")
        pages = document.pop("pages")
        catalog_dispositions = document.pop("catalog_dispositions", [])
        assert isinstance(entities, dict)
        assert isinstance(pages, list)
        assert isinstance(catalog_dispositions, list)
        entity_records = sorted(
            entities.values(), key=lambda row: (row["entity_kind"], row["native_id"])
        )
        page_records = sorted(
            pages,
            key=lambda row: (
                row["entity_kind"],
                row["page"],
                row["start_position"],
            ),
        )
        counts: dict[str, int] = {}
        for row in entity_records:
            kind = str(row["entity_kind"])
            counts[kind] = counts.get(kind, 0) + 1
        manifest = {
            **document,
            "entity_counts": dict(sorted(counts.items())),
            "entities": entity_records,
            "pages": page_records,
            "catalog_dispositions": sorted(
                catalog_dispositions, key=lambda row: row["entity_kind"]
            ),
        }
        if state is RunState.COMPLETE and self.bounded_snapshot:
            bounded = build_bounded_snapshot(
                source_manifest=manifest, blob_root=self.root / "blobs"
            )
            bounded_bytes = _canonical_json(bounded.document)
            self._store_named_immutable(
                self.root / "runs" / run_id / "bounded-manifest.json",
                bounded_bytes,
            )
            manifest["snapshot_policy_version"] = bounded.document[
                "snapshot_policy_version"
            ]
            manifest["bounded_snapshot_sha256"] = bounded.digest
            manifest["post_cutoff_exclusion_sha256"] = bounded.exclusion_digest
        manifest_bytes = _canonical_json(manifest)
        self._store_named_immutable(
            self.root / "runs" / run_id / "manifest.json", manifest_bytes
        )
        self._replace_json(state_path, {**manifest, "sealed": True})
        return hashlib.sha256(manifest_bytes).hexdigest()

    def _state_path(self, run_id: str) -> Path:
        _safe_identity(run_id)
        path = self.root / "runs" / run_id / "state.json"
        if not path.is_file():
            raise EvidenceStoreError("run_not_found")
        return path

    def bounded_snapshot_summary(self, *, run_id: str) -> dict[str, object] | None:
        _safe_identity(run_id)
        path = self.root / "runs" / run_id / "bounded-manifest.json"
        if not path.is_file():
            return None
        document = self._read_json(path)
        return {
            "state": document.get("state"),
            "snapshot_policy_version": document.get("snapshot_policy_version"),
            "bounded_snapshot_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "post_cutoff_exclusion_sha256": document.get("exclusion_digest"),
            "excluded_post_cutoff_counts": document.get(
                "excluded_post_cutoff_counts", {}
            ),
            "maximum_included_transaction_dates": document.get(
                "maximum_included_transaction_dates", {}
            ),
        }

    def stored_snapshot(self, *, run_id: str) -> SnapshotIdentity | None:
        _safe_identity(run_id)
        path = self.root / "runs" / run_id / "state.json"
        if not path.is_file():
            return None
        document = self._read_json(path)
        snapshot = document.get("snapshot")
        if not isinstance(snapshot, dict):
            raise EvidenceStoreError("run_state_invalid")
        return SnapshotIdentity(
            snapshot_id=str(snapshot["snapshot_id"]),
            realm_id=str(snapshot["realm_id"]),
            environment=str(snapshot["environment"]),
            accounting_date_cutoff=date.fromisoformat(
                str(snapshot["accounting_date_cutoff"])
            ),
            cutoff_timezone=str(snapshot["cutoff_timezone"]),
            started_at=datetime.fromisoformat(str(snapshot["started_at"])),
            api_minor_version=int(snapshot["api_minor_version"]),
        )

    def terminal_run_summary(self, *, run_id: str) -> dict[str, object]:
        state_path = self._state_path(run_id)
        document = self._read_json(state_path)
        state = RunState(str(document["state"]))
        if state is RunState.IN_PROGRESS:
            raise EvidenceStoreError("run_not_terminal")
        manifest_path = self.root / "runs" / run_id / "manifest.json"
        entities = document.get("entities")
        if not isinstance(entities, list):
            raise EvidenceStoreError("run_state_invalid")
        return {
            "state": state,
            "envelope_count": len(entities),
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "failure_code": document.get("failure_code"),
        }

    def _store_blob(self, digest: str, content: bytes) -> None:
        if hashlib.sha256(content).hexdigest() != digest:
            raise EvidenceStoreError("blob_digest_conflict")
        path = self.root / "blobs" / digest[:2] / digest
        path.parent.mkdir(mode=0o700, exist_ok=True)
        os.chmod(path.parent, 0o700)
        self._store_named_immutable(path, content)

    @staticmethod
    def _store_named_immutable(path: Path, content: bytes) -> None:
        if path.exists():
            if path.read_bytes() != content:
                raise EvidenceStoreError("immutable_content_conflict")
            return
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as target:
                target.write(content)
                target.flush()
                os.fsync(target.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _replace_json(path: Path, document: Mapping[str, object]) -> None:
        temporary = path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "wb") as target:
            target.write(_canonical_json(document))
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        value = json.loads(path.read_bytes())
        if not isinstance(value, dict):
            raise EvidenceStoreError("stored_document_invalid")
        return value


class RunPageObserver(PageObserver):
    def __init__(self, *, store: ProtectedFilesystemEvidenceStore, run_id: str) -> None:
        self.store = store
        self.run_id = run_id

    async def record_page(self, evidence: PageEvidence, raw_body: bytes) -> None:
        self.store.record_page(run_id=self.run_id, evidence=evidence, raw_body=raw_body)

    async def record_catalog_disposition(
        self, evidence: CatalogDispositionEvidence
    ) -> None:
        self.store.record_catalog_disposition(run_id=self.run_id, evidence=evidence)


class ControlReportKind(str, Enum):
    TRIAL_BALANCE = "trial_balance"
    BALANCE_SHEET = "balance_sheet"
    PROFIT_AND_LOSS = "profit_and_loss"
    AR_AGING_DETAIL = "ar_aging_detail"
    AP_AGING_DETAIL = "ap_aging_detail"
    ACCOUNT_LIST = "account_list"
    GENERAL_LEDGER = "general_ledger"
    CUSTOMER_BALANCE_DETAIL = "customer_balance_detail"
    OPEN_INVOICES = "open_invoices"
    VENDOR_BALANCE_DETAIL = "vendor_balance_detail"
    UNPAID_BILLS = "unpaid_bills"


@dataclass(frozen=True)
class ControlEvidenceRegistration:
    control_id: str
    kind: ControlReportKind
    raw_sha256: str
    byte_size: int
    storage_reference: str
    report_end_date: date
    accounting_basis: str
    generated_at: datetime | None
    safe_report_parameters: Mapping[str, str]


class ControlEvidenceRegistry:
    def __init__(self, store: ProtectedFilesystemEvidenceStore) -> None:
        self.store = store

    def register(self, registration: ControlEvidenceRegistration) -> str:
        _safe_identity(registration.control_id)
        if (
            len(registration.raw_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in registration.raw_sha256
            )
            or registration.byte_size < 1
        ):
            raise ValueError("valid raw control digest and size are required")
        if registration.report_end_date != date(2026, 8, 25):
            raise ValueError("August 25, 2026 report cutoff is required")
        if registration.accounting_basis.lower() != "accrual":
            raise ValueError("accrual report basis is required")
        document = {
            "schema_version": "qbo-control-registration/v1",
            "control_id": registration.control_id,
            "kind": registration.kind.value,
            "raw_sha256": registration.raw_sha256,
            "byte_size": registration.byte_size,
            "storage_reference": registration.storage_reference,
            "report_end_date": registration.report_end_date.isoformat(),
            "accounting_basis": registration.accounting_basis,
            "generated_at": (
                registration.generated_at.isoformat()
                if registration.generated_at
                else None
            ),
            "safe_report_parameters": dict(
                sorted(registration.safe_report_parameters.items())
            ),
        }
        content = _canonical_json(document)
        digest = hashlib.sha256(content).hexdigest()
        self.store._store_named_immutable(
            self.store.root / "controls" / f"{registration.control_id}.json", content
        )
        return digest


def _safe_identity(value: str) -> None:
    if (
        not value
        or len(value) > 128
        or not all(character.isalnum() or character in "-_." for character in value)
    ):
        raise ValueError("safe evidence identity is required")
