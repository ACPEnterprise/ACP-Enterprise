from __future__ import annotations

import hashlib
import json
import re
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Protocol

_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class EntityKind(str, Enum):
    COMPANY_INFO = "company_info"
    ACCOUNT = "account"
    CUSTOMER = "customer"
    VENDOR = "vendor"
    INVOICE = "invoice"
    PAYMENT = "payment"
    CREDIT_MEMO = "credit_memo"
    BILL = "bill"
    BILL_PAYMENT = "bill_payment"
    VENDOR_CREDIT = "vendor_credit"
    PURCHASE = "purchase"
    CREDIT_CARD_PAYMENT = "credit_card_payment"
    DEPOSIT = "deposit"
    TRANSFER = "transfer"
    JOURNAL_ENTRY = "journal_entry"
    TAX_PAYMENT = "tax_payment"
    TAX_AGENCY = "tax_agency"
    CLASS = "class"
    DEPARTMENT = "department"
    ITEM = "item"
    EMPLOYEE = "employee"
    TIME_ACTIVITY = "time_activity"
    REFUND_RECEIPT = "refund_receipt"
    SALES_RECEIPT = "sales_receipt"
    ESTIMATE = "estimate"
    PURCHASE_ORDER = "purchase_order"
    TERM = "term"
    PAYMENT_METHOD = "payment_method"


@dataclass(frozen=True)
class SnapshotIdentity:
    snapshot_id: str
    realm_id: str
    environment: str
    accounting_date_cutoff: date
    cutoff_timezone: str
    started_at: datetime
    api_minor_version: int

    def __post_init__(self) -> None:
        if not self.snapshot_id or not self.realm_id:
            raise ValueError("snapshot and realm identity are required")
        if self.environment not in {"sandbox", "production"}:
            raise ValueError("environment must be sandbox or production")
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware")
        if self.api_minor_version < 1:
            raise ValueError("api_minor_version must be positive")


@dataclass(frozen=True)
class AcquisitionRequest:
    snapshot: SnapshotIdentity
    entity_kinds: tuple[EntityKind, ...]
    page_size: int = 1000

    def __post_init__(self) -> None:
        if not self.entity_kinds or len(set(self.entity_kinds)) != len(
            self.entity_kinds
        ):
            raise ValueError("unique entity kinds are required")
        if not 1 <= self.page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")


def canonical_source_digest(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        _json_domain(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class QboSourceEnvelope:
    schema_version: str
    provider: str
    snapshot: SnapshotIdentity
    native_entity_type: str
    native_id: str
    sync_token: str | None
    source_created_at: datetime | None
    source_updated_at: datetime | None
    acquired_at: datetime
    raw_sha256: str
    relationship_ids: tuple[str, ...]
    currency: str | None
    source_status: str | None
    source_accounting_meaning: Mapping[str, object]
    raw_payload: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.schema_version != "qbo-source-envelope/v1":
            raise ValueError("unsupported source-envelope schema")
        if self.provider != "quickbooks_online":
            raise ValueError("provider identity is invalid")
        if not self.native_entity_type or not self.native_id:
            raise ValueError("native entity type and ID are required")
        if self.acquired_at.tzinfo is None:
            raise ValueError("acquired_at must be timezone-aware")
        if not _SHA256.fullmatch(self.raw_sha256):
            raise ValueError("raw_sha256 is invalid")
        if canonical_source_digest(self.raw_payload) != self.raw_sha256:
            raise ValueError("raw payload digest mismatch")
        if self.currency is not None and not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise ValueError("currency must be an ISO 4217 code")
        if len(set(self.relationship_ids)) != len(self.relationship_ids):
            raise ValueError("relationship identities must be unique")
        object.__setattr__(self, "raw_payload", _deep_freeze(self.raw_payload))
        object.__setattr__(
            self,
            "source_accounting_meaning",
            MappingProxyType(dict(self.source_accounting_meaning)),
        )

    @classmethod
    def from_native(
        cls,
        *,
        snapshot: SnapshotIdentity,
        native_entity_type: str,
        native_id: str,
        payload: Mapping[str, object],
        acquired_at: datetime | None = None,
        sync_token: str | None = None,
        source_created_at: datetime | None = None,
        source_updated_at: datetime | None = None,
        relationship_ids: tuple[str, ...] = (),
        currency: str | None = None,
        source_status: str | None = None,
        source_accounting_meaning: Mapping[str, object] | None = None,
    ) -> QboSourceEnvelope:
        return cls(
            schema_version="qbo-source-envelope/v1",
            provider="quickbooks_online",
            snapshot=snapshot,
            native_entity_type=native_entity_type,
            native_id=native_id,
            sync_token=sync_token,
            source_created_at=source_created_at,
            source_updated_at=source_updated_at,
            acquired_at=acquired_at or datetime.now(timezone.utc),
            raw_sha256=canonical_source_digest(payload),
            relationship_ids=relationship_ids,
            currency=currency,
            source_status=source_status,
            source_accounting_meaning=source_accounting_meaning or {},
            raw_payload=payload,
        )


class SourceAcquisitionProvider(Protocol):
    """Read-only seam. Implementations expose no create/update/delete operation."""

    def acquire(
        self, request: AcquisitionRequest
    ) -> AsyncIterator[QboSourceEnvelope]: ...


def _deep_freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _deep_freeze(child) for key, child in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(child) for child in value)
    return value


def _json_domain(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_domain(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_domain(child) for child in value]
    return value
