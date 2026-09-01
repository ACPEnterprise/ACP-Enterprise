from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from zoneinfo import ZoneInfo

from .contracts import EntityKind

SNAPSHOT_POLICY_VERSION = "qbo-production-snapshot-policy/v1"
CATALOG_VERSION = "qbo-production-acquisition-catalog/v2"


class TemporalClassification(str, Enum):
    TRANSACTION_DATE_FILTERABLE = "TRANSACTION_DATE_FILTERABLE"
    MODIFICATION_TIME_FILTERABLE = "MODIFICATION_TIME_FILTERABLE"
    AS_OF_QUERY_SUPPORTED = "AS_OF_QUERY_SUPPORTED"
    CURRENT_STATE_ONLY = "CURRENT_STATE_ONLY"
    REFERENCE_MASTER_CURRENT = "REFERENCE_MASTER_CURRENT"
    PROVIDER_POINT_IN_TIME_UNAVAILABLE = "PROVIDER_POINT_IN_TIME_UNAVAILABLE"
    EMPTY_CONFIRMED = "EMPTY_CONFIRMED"
    OPTIONAL_PROVIDER_UNAVAILABLE = "OPTIONAL_PROVIDER_UNAVAILABLE"


TRANSACTION_DATE_FIELDS: dict[str, tuple[str, ...]] = {
    EntityKind.INVOICE.value: ("TxnDate",),
    EntityKind.PAYMENT.value: ("TxnDate", "PaymentDate"),
    EntityKind.CREDIT_MEMO.value: ("TxnDate",),
    EntityKind.BILL.value: ("TxnDate",),
    EntityKind.BILL_PAYMENT.value: ("TxnDate",),
    EntityKind.VENDOR_CREDIT.value: ("TxnDate",),
    EntityKind.PURCHASE.value: ("TxnDate",),
    EntityKind.CREDIT_CARD_PAYMENT.value: ("TxnDate",),
    EntityKind.DEPOSIT.value: ("TxnDate",),
    EntityKind.TRANSFER.value: ("TxnDate",),
    EntityKind.JOURNAL_ENTRY.value: ("TxnDate",),
    EntityKind.TAX_PAYMENT.value: ("TxnDate",),
    EntityKind.TIME_ACTIVITY.value: ("TxnDate",),
    EntityKind.REFUND_RECEIPT.value: ("TxnDate",),
    EntityKind.SALES_RECEIPT.value: ("TxnDate",),
    EntityKind.ESTIMATE.value: ("TxnDate",),
    EntityKind.PURCHASE_ORDER.value: ("TxnDate",),
}

CURRENT_STATE_FAMILIES = frozenset({EntityKind.COMPANY_INFO.value})
REFERENCE_MASTER_FAMILIES = frozenset(
    {
        EntityKind.ACCOUNT.value,
        EntityKind.CUSTOMER.value,
        EntityKind.VENDOR.value,
        EntityKind.EMPLOYEE.value,
        EntityKind.ITEM.value,
        EntityKind.TERM.value,
        EntityKind.PAYMENT_METHOD.value,
        EntityKind.TAX_AGENCY.value,
        EntityKind.CLASS.value,
        EntityKind.DEPARTMENT.value,
    }
)


class SnapshotPolicyError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class BoundedSnapshotProjection:
    document: dict[str, object]
    digest: str
    exclusion_digest: str


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _identity_digest(kind: str, native_id: str) -> str:
    return hashlib.sha256(f"{kind}:{native_id}".encode()).hexdigest()


def _parse_date(payload: dict[str, object], fields: tuple[str, ...]) -> date:
    for field in fields:
        value = payload.get(field)
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError as error:
                raise SnapshotPolicyError(
                    "authoritative_transaction_date_invalid"
                ) from error
    raise SnapshotPolicyError("authoritative_transaction_date_missing")


def build_bounded_snapshot(
    *, source_manifest: dict[str, object], blob_root: Path
) -> BoundedSnapshotProjection:
    snapshot = source_manifest.get("snapshot")
    if not isinstance(snapshot, dict):
        raise SnapshotPolicyError("snapshot_identity_missing")
    cutoff_value = snapshot.get("accounting_date_cutoff")
    timezone_value = snapshot.get("cutoff_timezone")
    if not isinstance(cutoff_value, str) or not isinstance(timezone_value, str):
        raise SnapshotPolicyError("snapshot_cutoff_missing")
    cutoff = date.fromisoformat(cutoff_value)
    cutoff_end = datetime.combine(cutoff, time.max, ZoneInfo(timezone_value))
    entities = source_manifest.get("entities")
    dispositions = source_manifest.get("catalog_dispositions", [])
    if not isinstance(entities, list) or not isinstance(dispositions, list):
        raise SnapshotPolicyError("source_manifest_invalid")

    unavailable = {
        str(item.get("entity_kind"))
        for item in dispositions
        if isinstance(item, dict)
        and item.get("disposition") == "PROVIDER_FAMILY_UNAVAILABLE"
    }
    source_counts = source_manifest.get("entity_counts", {})
    if not isinstance(source_counts, dict):
        raise SnapshotPolicyError("source_manifest_invalid")

    included: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    corrections: list[dict[str, object]] = []
    family_dates: dict[str, list[date]] = {}
    policy: dict[str, dict[str, object]] = {}
    for entity_kind in EntityKind:
        count = int(source_counts.get(entity_kind.value, 0))
        if entity_kind.value in unavailable:
            classification = TemporalClassification.OPTIONAL_PROVIDER_UNAVAILABLE
        elif count == 0:
            classification = TemporalClassification.EMPTY_CONFIRMED
        elif entity_kind.value in TRANSACTION_DATE_FIELDS:
            classification = TemporalClassification.TRANSACTION_DATE_FILTERABLE
        elif entity_kind.value in CURRENT_STATE_FAMILIES:
            classification = TemporalClassification.CURRENT_STATE_ONLY
        elif entity_kind.value in REFERENCE_MASTER_FAMILIES:
            classification = TemporalClassification.REFERENCE_MASTER_CURRENT
        else:
            classification = TemporalClassification.PROVIDER_POINT_IN_TIME_UNAVAILABLE
        policy[entity_kind.value] = {
            "classification": classification.value,
            "source_count": count,
            "cutoff_enforcement": (
                "LOCAL_AUTHORITATIVE_TRANSACTION_DATE"
                if entity_kind.value in TRANSACTION_DATE_FIELDS and count
                else "NOT_APPLICABLE"
            ),
            "temporal_limitation": (
                "CURRENT_PROVIDER_STATE_NOT_HISTORICAL_AS_OF"
                if classification
                in {
                    TemporalClassification.CURRENT_STATE_ONLY,
                    TemporalClassification.REFERENCE_MASTER_CURRENT,
                }
                else None
            ),
        }

    for row in entities:
        if not isinstance(row, dict):
            raise SnapshotPolicyError("source_manifest_invalid")
        entity_kind_value = str(row.get("entity_kind"))
        native_id = str(row.get("native_id"))
        raw_digest = row.get("raw_sha256")
        envelope_digest = row.get("envelope_sha256")
        if not isinstance(raw_digest, str) or not isinstance(envelope_digest, str):
            raise SnapshotPolicyError("source_manifest_invalid")
        identity = _identity_digest(entity_kind_value, native_id)
        record: dict[str, object] = {
            "entity_kind": entity_kind_value,
            "source_identity_digest": identity,
            "envelope_sha256": envelope_digest,
            "raw_sha256": raw_digest,
        }
        fields = TRANSACTION_DATE_FIELDS.get(entity_kind_value)
        if fields is None:
            included.append(record)
            continue
        raw_path = blob_root / raw_digest[:2] / raw_digest
        try:
            payload = json.loads(raw_path.read_bytes())
        except (FileNotFoundError, json.JSONDecodeError) as error:
            raise SnapshotPolicyError("source_blob_unavailable") from error
        if not isinstance(payload, dict):
            raise SnapshotPolicyError("source_blob_invalid")
        transaction_date = _parse_date(payload, fields)
        family_dates.setdefault(entity_kind_value, []).append(transaction_date)
        if transaction_date > cutoff:
            excluded.append(
                {
                    **record,
                    "authoritative_transaction_date": transaction_date.isoformat(),
                    "accounting_date_cutoff": cutoff.isoformat(),
                    "reason": "EXCLUDED_POST_CUTOFF",
                }
            )
            continue
        included.append(
            {**record, "authoritative_transaction_date": transaction_date.isoformat()}
        )
        envelope_path = blob_root.parent / "envelopes" / f"{envelope_digest}.json"
        try:
            envelope = json.loads(envelope_path.read_bytes())
        except (FileNotFoundError, json.JSONDecodeError) as error:
            raise SnapshotPolicyError("source_envelope_unavailable") from error
        updated = (
            envelope.get("source_updated_at") if isinstance(envelope, dict) else None
        )
        if isinstance(updated, str):
            updated_at = datetime.fromisoformat(updated)
            if updated_at > cutoff_end:
                corrections.append(
                    {
                        "entity_kind": entity_kind_value,
                        "source_identity_digest": identity,
                        "authoritative_transaction_date": transaction_date.isoformat(),
                        "classification": "POST_CUTOFF_SOURCE_MODIFICATION",
                        "source_updated_at": updated_at.isoformat(),
                    }
                )

    included.sort(
        key=lambda item: (
            str(item["entity_kind"]),
            str(item["source_identity_digest"]),
        )
    )
    excluded.sort(
        key=lambda item: (
            str(item["entity_kind"]),
            str(item["source_identity_digest"]),
        )
    )
    corrections.sort(
        key=lambda item: (
            str(item["entity_kind"]),
            str(item["source_identity_digest"]),
        )
    )
    included_counts: dict[str, int] = {}
    excluded_counts: dict[str, int] = {}
    for item in included:
        item_kind = str(item["entity_kind"])
        included_counts[item_kind] = included_counts.get(item_kind, 0) + 1
    for item in excluded:
        item_kind = str(item["entity_kind"])
        excluded_counts[item_kind] = excluded_counts.get(item_kind, 0) + 1
    exclusion_digest = hashlib.sha256(_canonical(excluded)).hexdigest()
    document: dict[str, object] = {
        "schema_version": "qbo-bounded-accounting-snapshot/v1",
        "state": "BOUNDED_COMPLETE",
        "snapshot_policy_version": SNAPSHOT_POLICY_VERSION,
        "catalog_version": CATALOG_VERSION,
        "source_run_id": source_manifest.get("run_id"),
        "realm_id": snapshot.get("realm_id"),
        "environment": snapshot.get("environment"),
        "accounting_date_cutoff": cutoff.isoformat(),
        "per_family_policy": dict(sorted(policy.items())),
        "included_counts": dict(sorted(included_counts.items())),
        "excluded_post_cutoff_counts": dict(sorted(excluded_counts.items())),
        "maximum_included_transaction_dates": {
            kind: max(value for value in dates if value <= cutoff).isoformat()
            for kind, dates in sorted(family_dates.items())
            if any(value <= cutoff for value in dates)
        },
        "included_entities": included,
        "excluded_post_cutoff": excluded,
        "post_cutoff_source_modifications": corrections,
        "exclusion_digest": exclusion_digest,
    }
    digest = hashlib.sha256(_canonical(document)).hexdigest()
    return BoundedSnapshotProjection(document, digest, exclusion_digest)
