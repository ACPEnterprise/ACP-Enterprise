"""HCP.SOURCE.3 control intake and residual-evidence closure contracts."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from itertools import pairwise
from typing import Any
from zoneinfo import ZoneInfo

from .hcp_readonly_extractor import ProtectedEvidenceStore
from .hcp_source_acquisition import SourceAssertion, preserve_conflict

CONTROL_CONTRACT_VERSION = "hcp-control-export-intake/v1"
REQUIRED_CONTROLS = (
    "customer_list",
    "job_list",
    "estimate_list",
    "payments_summary",
    "payment_details",
)


class ControlExportType(StrEnum):
    CUSTOMER_LIST = "customer_list"
    JOB_LIST = "job_list"
    ESTIMATE_LIST = "estimate_list"
    PAYMENTS_SUMMARY = "payments_summary"
    PAYMENT_DETAILS = "payment_details"


class ReconciliationClassification(StrEnum):
    MATCHED = "matched"
    SOURCE_API_MISSING = "source_api_missing"
    CONTROL_EXPORT_MISSING = "control_export_missing"
    CONFLICTING = "conflicting"
    UNSUPPORTED_RELATIONSHIP = "unsupported_relationship"


class ReadinessImpact(StrEnum):
    BLOCKS_ACQUISITION = "blocks_acquisition"
    BLOCKS_OPEN_WORK_CUTOVER = "blocks_open_work_cutover"
    BLOCKS_RECONCILIATION = "blocks_reconciliation"
    NON_BLOCKING_MISSING_EVIDENCE = "non_blocking_missing_evidence"


@dataclass(frozen=True)
class PaymentDateRange:
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("payment range end precedes start")


@dataclass(frozen=True)
class ControlManifestEntry:
    control_type: ControlExportType
    source_report_identity: str
    extraction_timestamp: datetime
    timezone: str
    filters: Mapping[str, Any]
    row_count: int
    byte_size: int
    raw_sha256: str
    exporting_admin_evidence_sha256: str
    schema_header_sha256: str
    ordered_headers: tuple[str, ...]
    protected_artifact_name: str
    company_identity_sha256: str


@dataclass(frozen=True)
class ControlManifest:
    contract_version: str
    extraction_id: str
    entries: tuple[ControlManifestEntry, ...]
    manifest_sha256: str


@dataclass(frozen=True)
class ReconciliationItem:
    entity: str
    native_id: str | None
    classification: ReconciliationClassification
    api_digest: str | None
    control_digest: str | None
    relationship: str | None = None


@dataclass(frozen=True)
class BranchMappingCandidate:
    hcp_business_unit_identity_sha256: str
    candidate_enterprise_branch_id: str | None
    non_name_evidence_sha256s: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class TechnicianCrosswalkSource:
    company_identity_sha256: str
    native_employee_id_sha256: str
    source_active: bool | None
    assignment_evidence_sha256s: tuple[str, ...]
    safe_context_sha256: str
    business_unit_evidence_sha256s: tuple[str, ...]
    enterprise_employee_id: None = None


@dataclass(frozen=True)
class FinancialConflictEvidence:
    assertions: tuple[SourceAssertion, ...]
    classification: str
    comparison_rule_version: str


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode()


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def ordered_header_fingerprint(headers: Sequence[str]) -> str:
    if not headers or any(not header for header in headers):
        raise ValueError("control export headers must be non-empty")
    return _sha256(_canonical(tuple(headers)))


def intake_csv_control(
    *,
    store: ProtectedEvidenceStore,
    artifact_name: str,
    source: bytes,
    control_type: ControlExportType,
    source_report_identity: str,
    extraction_timestamp: datetime,
    timezone: str,
    filters: Mapping[str, Any],
    exporting_admin_evidence_sha256: str,
    company_identity_sha256: str,
) -> ControlManifestEntry:
    if extraction_timestamp.tzinfo is None:
        raise ValueError("control extraction timestamp must be timezone-aware")
    ZoneInfo(timezone)
    if extraction_timestamp.astimezone(ZoneInfo(timezone)).utcoffset() is None:
        raise ValueError("invalid control extraction timezone")
    if not source_report_identity or not filters:
        raise ValueError("report identity and explicit filters are required")
    if any(len(digest) != 64 for digest in (exporting_admin_evidence_sha256, company_identity_sha256)):
        raise ValueError("admin and Company evidence must be SHA-256")
    try:
        text = source.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text, newline="")))
    except (UnicodeDecodeError, csv.Error) as error:
        raise ValueError("control artifact must be valid UTF-8 CSV") from error
    if not rows:
        raise ValueError("control artifact is empty")
    headers = tuple(rows[0])
    if len(set(headers)) != len(headers):
        raise ValueError("control artifact contains duplicate headers")
    expected_columns = len(headers)
    if any(len(row) != expected_columns for row in rows[1:]):
        raise ValueError("control artifact has inconsistent columns")
    store.write_once(artifact_name, source)
    return ControlManifestEntry(
        control_type=control_type,
        source_report_identity=source_report_identity,
        extraction_timestamp=extraction_timestamp,
        timezone=timezone,
        filters=dict(filters),
        row_count=len(rows) - 1,
        byte_size=len(source),
        raw_sha256=_sha256(source),
        exporting_admin_evidence_sha256=exporting_admin_evidence_sha256,
        schema_header_sha256=ordered_header_fingerprint(headers),
        ordered_headers=headers,
        protected_artifact_name=artifact_name,
        company_identity_sha256=company_identity_sha256,
    )


def seal_control_manifest(
    extraction_id: str, entries: Iterable[ControlManifestEntry]
) -> ControlManifest:
    ordered = tuple(sorted(entries, key=lambda item: item.control_type.value))
    if tuple(sorted(item.control_type.value for item in ordered)) != tuple(sorted(REQUIRED_CONTROLS)):
        raise ValueError("exactly one of each required HCP control is required")
    if len({item.protected_artifact_name for item in ordered}) != len(ordered):
        raise ValueError("control artifact names must be unique")
    if len({item.company_identity_sha256 for item in ordered}) != 1:
        raise ValueError("control artifacts cross Company scope")
    body = {
        "contract_version": CONTROL_CONTRACT_VERSION,
        "extraction_id": extraction_id,
        "entries": [asdict(item) for item in ordered],
    }
    return ControlManifest(
        CONTROL_CONTRACT_VERSION, extraction_id, ordered, _sha256(_canonical(body))
    )


def validate_payment_ranges(ranges: Iterable[PaymentDateRange]) -> tuple[PaymentDateRange, ...]:
    ordered = tuple(sorted(ranges, key=lambda item: item.start))
    for previous, current in pairwise(ordered):
        if current.start != previous.end + timedelta(days=1):
            raise ValueError("payment ranges must be contiguous and non-overlapping")
    return ordered


def reconcile_native_evidence(
    *, entity: str, api: Mapping[str, str], control: Mapping[str, str]
) -> tuple[ReconciliationItem, ...]:
    results: list[ReconciliationItem] = []
    for native_id in sorted(set(api) | set(control)):
        api_digest = api.get(native_id)
        control_digest = control.get(native_id)
        if api_digest is None:
            classification = ReconciliationClassification.SOURCE_API_MISSING
        elif control_digest is None:
            classification = ReconciliationClassification.CONTROL_EXPORT_MISSING
        elif api_digest == control_digest:
            classification = ReconciliationClassification.MATCHED
        else:
            classification = ReconciliationClassification.CONFLICTING
        results.append(
            ReconciliationItem(
                entity, native_id, classification, api_digest, control_digest
            )
        )
    return tuple(results)


def unsupported_relationship(entity: str, relationship: str) -> ReconciliationItem:
    return ReconciliationItem(
        entity,
        None,
        ReconciliationClassification.UNSUPPORTED_RELATIONSHIP,
        None,
        None,
        relationship,
    )


def financial_conflict(
    hcp: SourceAssertion, qbo: SourceAssertion
) -> FinancialConflictEvidence:
    assertions = preserve_conflict(hcp, qbo)
    values = {_canonical(item.original_value) for item in assertions}
    return FinancialConflictEvidence(
        assertions,
        "conflict" if len(values) > 1 else "consistent",
        "hcp-qbo-financial-assertions/v1",
    )
