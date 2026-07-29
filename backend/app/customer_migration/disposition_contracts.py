import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

DISPOSITION_IDENTITY_VERSION = "owner-disposition/v1"
DISPOSITION_REPLAY_VERSION = "owner-disposition-replay/v1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_KEY = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9:_-]{0,190}$")
REASON_CODE = re.compile(r"^[a-z][a-z0-9_]{2,79}$")


class DispositionKind(StrEnum):
    MISSING_CUSTOMER_TYPE = "missing_customer_type"
    CONTACT_NAME_RESOLUTION = "contact_name_resolution"
    DUPLICATE_CLUSTER_RESOLUTION = "duplicate_cluster_resolution"
    ADDRESS_EXCEPTION_DISPOSITION = "address_exception_disposition"


class DispositionCode(StrEnum):
    OWNER_PROVIDED_RESIDENTIAL = "owner_provided_residential"
    OWNER_PROVIDED_COMMERCIAL = "owner_provided_commercial"
    ACCEPT_CUSTOMER_WITHOUT_CONTACT = "accept_customer_without_contact"
    OWNER_PROVIDED_CONTACT_REFERENCE = "owner_provided_contact_reference"
    KEEP_SEPARATE = "keep_separate"
    MARK_DUPLICATE_CANDIDATE = "mark_duplicate_candidate"
    SKIP_INCOMPLETE_ADDRESS = "skip_incomplete_address"
    REQUIRES_SOURCE_CORRECTION = "requires_source_correction"
    REQUIRES_OWNER_REVIEW = "requires_owner_review"
    PERMANENT_REJECTION = "permanent_rejection"


ALLOWED_CODES: dict[DispositionKind, frozenset[DispositionCode]] = {
    DispositionKind.MISSING_CUSTOMER_TYPE: frozenset(
        {
            DispositionCode.OWNER_PROVIDED_RESIDENTIAL,
            DispositionCode.OWNER_PROVIDED_COMMERCIAL,
            DispositionCode.REQUIRES_SOURCE_CORRECTION,
            DispositionCode.PERMANENT_REJECTION,
        }
    ),
    DispositionKind.CONTACT_NAME_RESOLUTION: frozenset(
        {
            DispositionCode.ACCEPT_CUSTOMER_WITHOUT_CONTACT,
            DispositionCode.OWNER_PROVIDED_CONTACT_REFERENCE,
            DispositionCode.REQUIRES_SOURCE_CORRECTION,
            DispositionCode.PERMANENT_REJECTION,
        }
    ),
    DispositionKind.DUPLICATE_CLUSTER_RESOLUTION: frozenset(
        {
            DispositionCode.KEEP_SEPARATE,
            DispositionCode.MARK_DUPLICATE_CANDIDATE,
            DispositionCode.REQUIRES_OWNER_REVIEW,
        }
    ),
    DispositionKind.ADDRESS_EXCEPTION_DISPOSITION: frozenset(
        {
            DispositionCode.SKIP_INCOMPLETE_ADDRESS,
            DispositionCode.REQUIRES_SOURCE_CORRECTION,
            DispositionCode.PERMANENT_REJECTION,
        }
    ),
}


def _require_sha256(value: str, field: str) -> None:
    if SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _require_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


def _digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class DispositionSourceIdentity:
    company_id: UUID
    source_artifact_sha256: str
    source_identity_sha256: str
    adapter_version: str
    schema_version: str
    source_row_number: int | None = None

    def __post_init__(self) -> None:
        _require_sha256(self.source_artifact_sha256, "source_artifact_sha256")
        _require_sha256(self.source_identity_sha256, "source_identity_sha256")
        if (
            not self.adapter_version
            or self.adapter_version != self.adapter_version.strip()
        ):
            raise ValueError("adapter_version must be explicit")
        if (
            not self.schema_version
            or self.schema_version != self.schema_version.strip()
        ):
            raise ValueError("schema_version must be explicit")
        if self.source_row_number is not None and self.source_row_number < 2:
            raise ValueError("source_row_number must identify a data row")


@dataclass(frozen=True)
class DispositionDecision:
    kind: DispositionKind
    code: DispositionCode
    decision_evidence_sha256: str

    def __post_init__(self) -> None:
        if self.code not in ALLOWED_CODES[self.kind]:
            raise ValueError(f"{self.code.value} is not valid for {self.kind.value}")
        _require_sha256(self.decision_evidence_sha256, "decision_evidence_sha256")


@dataclass(frozen=True)
class DispositionAuditMetadata:
    approved_by_user_id: UUID
    approved_at: datetime
    reason_code: str
    approval_request_id: UUID
    approval_evidence_sha256: str

    def __post_init__(self) -> None:
        _require_utc(self.approved_at, "approved_at")
        if REASON_CODE.fullmatch(self.reason_code) is None:
            raise ValueError("reason_code must be a bounded machine-readable code")
        _require_sha256(self.approval_evidence_sha256, "approval_evidence_sha256")


def disposition_identity(
    *,
    source: DispositionSourceIdentity,
    kind: DispositionKind,
    subject_key: str,
) -> str:
    if SAFE_KEY.fullmatch(subject_key) is None:
        raise ValueError("subject_key must be a PII-safe bounded identifier")
    return _digest(
        {
            "identity_version": DISPOSITION_IDENTITY_VERSION,
            "company_id": str(source.company_id),
            "source_artifact_sha256": source.source_artifact_sha256,
            "source_identity_sha256": source.source_identity_sha256,
            "kind": kind.value,
            "subject_key": subject_key,
        }
    )


@dataclass(frozen=True)
class OwnerDisposition:
    id: UUID
    identity_version: str
    disposition_identity: str
    version: int
    source: DispositionSourceIdentity
    subject_key: str
    decision: DispositionDecision
    audit: DispositionAuditMetadata
    prior_disposition_id: UUID | None
    record_sha256: str

    def __post_init__(self) -> None:
        if self.identity_version != DISPOSITION_IDENTITY_VERSION:
            raise ValueError("unsupported disposition identity version")
        _require_sha256(self.disposition_identity, "disposition_identity")
        _require_sha256(self.record_sha256, "record_sha256")
        if self.version < 1:
            raise ValueError("version must be positive")
        if self.version == 1 and self.prior_disposition_id is not None:
            raise ValueError("initial disposition cannot supersede another disposition")
        if self.version > 1 and self.prior_disposition_id is None:
            raise ValueError("versioned disposition must link its prior decision")
        expected_identity = disposition_identity(
            source=self.source,
            kind=self.decision.kind,
            subject_key=self.subject_key,
        )
        if self.disposition_identity != expected_identity:
            raise ValueError("disposition identity does not match its source linkage")
        if self.record_sha256 != owner_disposition_record_sha256(
            disposition_id=self.id,
            disposition_identity_value=self.disposition_identity,
            version=self.version,
            source=self.source,
            subject_key=self.subject_key,
            decision=self.decision,
            audit=self.audit,
            prior_disposition_id=self.prior_disposition_id,
        ):
            raise ValueError(
                "record digest does not match immutable disposition content"
            )


def owner_disposition_record_sha256(
    *,
    disposition_id: UUID,
    disposition_identity_value: str,
    version: int,
    source: DispositionSourceIdentity,
    subject_key: str,
    decision: DispositionDecision,
    audit: DispositionAuditMetadata,
    prior_disposition_id: UUID | None,
) -> str:
    return _digest(
        {
            "id": str(disposition_id),
            "identity_version": DISPOSITION_IDENTITY_VERSION,
            "disposition_identity": disposition_identity_value,
            "version": version,
            "company_id": str(source.company_id),
            "source_artifact_sha256": source.source_artifact_sha256,
            "source_identity_sha256": source.source_identity_sha256,
            "source_row_number": source.source_row_number,
            "adapter_version": source.adapter_version,
            "schema_version": source.schema_version,
            "subject_key": subject_key,
            "decision_kind": decision.kind.value,
            "decision_code": decision.code.value,
            "decision_evidence_sha256": decision.decision_evidence_sha256,
            "approved_by_user_id": str(audit.approved_by_user_id),
            "approved_at": audit.approved_at.isoformat(),
            "reason_code": audit.reason_code,
            "approval_request_id": str(audit.approval_request_id),
            "approval_evidence_sha256": audit.approval_evidence_sha256,
            "prior_disposition_id": str(prior_disposition_id)
            if prior_disposition_id
            else None,
        }
    )


@dataclass(frozen=True)
class DispositionReplayApplication:
    replay_version: str
    ordinal: int
    application_id: str
    disposition: OwnerDisposition

    def __post_init__(self) -> None:
        if self.replay_version != DISPOSITION_REPLAY_VERSION:
            raise ValueError("unsupported replay contract version")
        if self.ordinal < 0:
            raise ValueError("ordinal must be nonnegative")
        _require_sha256(self.application_id, "application_id")


@dataclass(frozen=True)
class DispositionReplayPlan:
    replay_version: str
    company_id: UUID
    source_artifact_sha256: str
    applications: tuple[DispositionReplayApplication, ...]
    replay_sha256: str

    def __post_init__(self) -> None:
        if self.replay_version != DISPOSITION_REPLAY_VERSION:
            raise ValueError("unsupported replay contract version")
        _require_sha256(self.source_artifact_sha256, "source_artifact_sha256")
        _require_sha256(self.replay_sha256, "replay_sha256")
        if tuple(item.ordinal for item in self.applications) != tuple(
            range(len(self.applications))
        ):
            raise ValueError("applications must have contiguous replay ordering")


@dataclass(frozen=True)
class DispositionApplicationReceipt:
    company_id: UUID
    application_id: str
    disposition_record_sha256: str
    effect_sha256: str
    applied_at: datetime

    def __post_init__(self) -> None:
        _require_sha256(self.application_id, "application_id")
        _require_sha256(self.disposition_record_sha256, "disposition_record_sha256")
        _require_sha256(self.effect_sha256, "effect_sha256")
        _require_utc(self.applied_at, "applied_at")
