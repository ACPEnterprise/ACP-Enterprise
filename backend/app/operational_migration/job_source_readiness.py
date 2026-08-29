"""Fail-closed, non-PII readiness contracts for complete Job source acquisition."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, model_validator

from app.operational_migration.phase1 import JOB_HEADERS

READINESS_VERSION = "job-source-readiness/v1"
LEGACY_SCHEMA_VERSION = "housecall_pro_job_export_20240321_v1"
CURRENT_SCHEMA_VERSION = "housecall_pro_jobs_export_2026_v1"
LEGACY_IDENTITY_SEMANTICS = "housecall_pro_job_id"
CURRENT_IDENTITY_SEMANTICS = "job_number_unproven"

CURRENT_JOB_HEADERS = (
    "Job #",
    "Job description",
    "Job status",
    "Customer name",
    "Job created date",
    "Job scheduled start date",
    "Job amount",
    "Total labor hours",
)
MONTHLY_REPORT_HEADERS = ("Jobs by completed month", "Job revenue")
CUSTOMER_REPORT_HEADERS = (
    "Customer name",
    "Job revenue",
    "Job count",
    "Avg job size",
    "Gross profit",
    "Review count",
    "Avg rating",
)


class JobSourceSchema(StrEnum):
    LEGACY_JOB = LEGACY_SCHEMA_VERSION
    CURRENT_JOB = CURRENT_SCHEMA_VERSION
    MONTHLY_AGGREGATE = "housecall_pro_jobs_completed_month_report/v1"
    CUSTOMER_AGGREGATE = "housecall_pro_customer_job_report/v1"
    UNREGISTERED = "unregistered"


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def sha256(value: str | bytes) -> str:
    return hashlib.sha256(
        value.encode() if isinstance(value, str) else value
    ).hexdigest()


def schema_fingerprint(headers: Sequence[str]) -> str:
    return sha256(canonical(list(headers)))


REGISTERED_SCHEMAS: dict[tuple[str, ...], JobSourceSchema] = {
    JOB_HEADERS: JobSourceSchema.LEGACY_JOB,
    CURRENT_JOB_HEADERS: JobSourceSchema.CURRENT_JOB,
    MONTHLY_REPORT_HEADERS: JobSourceSchema.MONTHLY_AGGREGATE,
    CUSTOMER_REPORT_HEADERS: JobSourceSchema.CUSTOMER_AGGREGATE,
}


def detect_schema(headers: Sequence[str]) -> JobSourceSchema:
    return REGISTERED_SCHEMAS.get(tuple(headers), JobSourceSchema.UNREGISTERED)


def decode_csv(source: bytes) -> tuple[str, list[dict[str, str]], tuple[str, ...]]:
    encoding = "utf-8-sig" if source.startswith(b"\xef\xbb\xbf") else "utf-8"
    text = source.decode(encoding)
    reader = csv.DictReader(io.StringIO(text, newline=""))
    headers = tuple(reader.fieldnames or ())
    return encoding, [dict(row) for row in reader], headers


@dataclass(frozen=True)
class SourceArtifactInventory:
    filename: str
    secure_location: str
    byte_size: int
    row_count: int
    column_count: int
    encoding: str
    schema_version: str
    schema_fingerprint: str
    sha256: str
    extraction_timestamp: str | None
    observed_date_min: str | None
    observed_date_max: str | None
    statuses: dict[str, int]
    stable_identifiers: tuple[str, ...]
    relationship_fields: tuple[str, ...]
    row_level: bool
    authoritative_for_migration: bool
    identity_semantics: str | None


def inventory_artifact(
    *,
    filename: str,
    secure_location: str,
    source: bytes,
    extraction_timestamp: str | None = None,
) -> SourceArtifactInventory:
    encoding, rows, headers = decode_csv(source)
    schema = detect_schema(headers)
    statuses: Counter[str] = Counter()
    dates: list[datetime] = []
    stable_identifiers: tuple[str, ...] = ()
    relationships: tuple[str, ...] = ()
    identity_semantics = None
    row_level = schema in {JobSourceSchema.LEGACY_JOB, JobSourceSchema.CURRENT_JOB}
    authoritative = schema is JobSourceSchema.LEGACY_JOB
    if schema is JobSourceSchema.LEGACY_JOB:
        statuses.update((row["Job Status"].strip() or "<blank>") for row in rows)
        for row in rows:
            for field, pattern in (
                ("Date", "%Y-%m-%d %H:%M"),
                ("Finished", "%Y-%m-%d %I:%M%p"),
            ):
                if row[field].strip():
                    dates.append(
                        datetime.strptime(row[field].strip().lower(), pattern).replace(
                            tzinfo=ZoneInfo("America/New_York")
                        )
                    )
        stable_identifiers = ("HCP Id",)
        relationships = (
            "Customer name",
            "Email",
            "Mobile Phone",
            "Home Phone",
            "Address",
        )
        identity_semantics = LEGACY_IDENTITY_SEMANTICS
    elif schema is JobSourceSchema.CURRENT_JOB:
        statuses.update((row["Job status"].strip() or "<blank>") for row in rows)
        for row in rows:
            for field in ("Job created date", "Job scheduled start date"):
                if row[field].strip():
                    dates.append(datetime.fromisoformat(row[field].strip()))
        relationships = ("Customer name",)
        identity_semantics = CURRENT_IDENTITY_SEMANTICS
    return SourceArtifactInventory(
        filename=filename,
        secure_location=secure_location,
        byte_size=len(source),
        row_count=len(rows),
        column_count=len(headers),
        encoding=encoding,
        schema_version=schema.value,
        schema_fingerprint=schema_fingerprint(headers),
        sha256=sha256(source),
        extraction_timestamp=extraction_timestamp,
        observed_date_min=min(dates).isoformat() if dates else None,
        observed_date_max=max(dates).isoformat() if dates else None,
        statuses=dict(sorted(statuses.items())),
        stable_identifiers=stable_identifiers,
        relationship_fields=relationships,
        row_level=row_level,
        authoritative_for_migration=authoritative,
        identity_semantics=identity_semantics,
    )


@dataclass(frozen=True)
class CrossExportReconciliation:
    earlier_rows: int
    later_rows: int
    exact_identity_matches: int
    same_identity_updated_source_version: int
    earlier_source_only: int
    later_source_only: int
    possible_duplicate: int
    ambiguous_identity: int
    unsupported_identity: int
    deleted_or_missing_historical_identity: int
    already_imported_identity_matches: int
    target_only_identity: int


def reconcile_legacy_exports(
    *, earlier: bytes, later: bytes, imported_source_ids: Sequence[str]
) -> CrossExportReconciliation:
    _, earlier_rows, earlier_headers = decode_csv(earlier)
    _, later_rows, later_headers = decode_csv(later)
    if (
        detect_schema(earlier_headers) is not JobSourceSchema.LEGACY_JOB
        or detect_schema(later_headers) is not JobSourceSchema.LEGACY_JOB
    ):
        raise ValueError("legacy reconciliation requires registered legacy schemas")
    earlier_ids = [row["HCP Id"].strip() for row in earlier_rows]
    later_ids = [row["HCP Id"].strip() for row in later_rows]
    if any(not value for value in (*earlier_ids, *later_ids)):
        raise ValueError("legacy reconciliation requires nonblank source identities")
    earlier_map = {row["HCP Id"].strip(): row for row in earlier_rows}
    later_map = {row["HCP Id"].strip(): row for row in later_rows}
    shared = earlier_map.keys() & later_map.keys()
    imported = set(imported_source_ids)
    later_set = set(later_ids)
    return CrossExportReconciliation(
        earlier_rows=len(earlier_rows),
        later_rows=len(later_rows),
        exact_identity_matches=sum(
            earlier_map[item] == later_map[item] for item in shared
        ),
        same_identity_updated_source_version=sum(
            earlier_map[item] != later_map[item] for item in shared
        ),
        earlier_source_only=len(earlier_map.keys() - later_map.keys()),
        later_source_only=len(later_map.keys() - earlier_map.keys()),
        possible_duplicate=(len(earlier_ids) - len(set(earlier_ids)))
        + (len(later_ids) - len(set(later_ids))),
        ambiguous_identity=0,
        unsupported_identity=0,
        deleted_or_missing_historical_identity=len(
            earlier_map.keys() - later_map.keys()
        ),
        already_imported_identity_matches=len(imported & later_set),
        target_only_identity=len(imported - later_set),
    )


def normalized(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return re.sub(r"[^a-z0-9]", "", text.encode("ascii", "ignore").decode().lower())


def normalized_phone(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[-10:] if len(digits) >= 10 else digits


def _add(index: dict[str, set[int]], value: str, item: int) -> None:
    if value:
        index[value].add(item)


def service_location_dispositions(
    *,
    source: bytes,
    phase1_review: Mapping[str, Any],
    customer_review: Mapping[str, Any],
    customer_manifest: Mapping[str, Any],
) -> dict[str, int]:
    _, rows, headers = decode_csv(source)
    if detect_schema(headers) is not JobSourceSchema.LEGACY_JOB:
        raise ValueError("Service Location reconciliation requires the legacy schema")
    disposition_rows = {
        int(item["row_number"])
        for item in phase1_review["dispositions"]
        if item["category"] == "service_location_not_migrated"
    }
    aggregates: list[Mapping[str, Any]] = list(customer_review["aggregates"])
    allowed = set(customer_manifest["ordered_source_identities"])
    indexes: dict[str, dict[str, set[int]]] = {
        key: defaultdict(set) for key in ("email", "phone", "name", "address")
    }
    location_counts: list[int] = []
    for index, aggregate in enumerate(aggregates):
        customer = json.loads(str(aggregate["customer_json"]))
        contact = (
            json.loads(str(aggregate["contact_json"]))
            if aggregate.get("contact_json")
            else {}
        )
        _add(indexes["email"], normalized(contact.get("email")), index)
        for field in ("mobile_phone", "office_phone"):
            _add(indexes["phone"], normalized_phone(contact.get(field)), index)
        for value in (
            customer.get("display_name"),
            customer.get("legal_name"),
            " ".join(
                filter(None, (contact.get("first_name"), contact.get("last_name")))
            ),
        ):
            _add(indexes["name"], normalized(value), index)
        locations = aggregate.get("service_location_json", [])
        location_counts.append(len(locations))
        for raw in locations:
            location = json.loads(str(raw))
            _add(
                indexes["address"],
                normalized(
                    " ".join(
                        str(location.get(field) or "")
                        for field in (
                            "address",
                            "address_line_2",
                            "city",
                            "state",
                            "postal_code",
                        )
                    )
                ),
                index,
            )
    counts: Counter[str] = Counter()
    for row_number, row in enumerate(rows, start=2):
        if row_number not in disposition_rows:
            continue
        address = normalized(row["Address"])
        if not address:
            counts["blank_source_address"] += 1
            continue
        address_matches = indexes["address"].get(address, set())
        owner_address_matches = {
            item
            for item in address_matches
            if aggregates[item]["source_identity"] not in allowed
        }
        signals: list[set[int]] = []
        email = normalized(row["Email"])
        if email and (matches := indexes["email"].get(email)):
            signals.append(set(matches))
        phones = set().union(
            *(
                indexes["phone"].get(normalized_phone(row[field]), set())
                for field in ("Mobile Phone", "Home Phone")
                if normalized_phone(row[field])
            )
        )
        if phones:
            signals.append(phones)
        names = indexes["name"].get(normalized(row["Customer"]), set()) | indexes[
            "name"
        ].get(normalized(f"{row['First Name']} {row['Last Name']}"), set())
        if names:
            signals.append(set(names))
        if not signals:
            category = (
                "source_address_matches_owner_disposition_customer"
                if owner_address_matches
                else "customer_identity_unresolved"
            )
            counts[category] += 1
            continue
        candidates = set(signals[0])
        for signal in signals[1:]:
            candidates &= signal
        if not candidates:
            category = (
                "source_address_matches_owner_disposition_customer"
                if owner_address_matches
                else "customer_signals_conflict"
            )
        elif len(candidates) > 1:
            category = "customer_identity_ambiguous"
        else:
            item = next(iter(candidates))
            aggregate = aggregates[item]
            location_count = location_counts[item]
            accepted = aggregate["source_identity"] in allowed
            if not accepted and location_count > 1:
                category = "multiple_service_locations"
            elif not accepted and item in address_matches:
                category = "source_address_matches_owner_disposition_customer"
            elif not accepted:
                category = "customer_not_in_accepted_boundary"
            elif location_count == 0:
                category = "customer_migrated_service_location_missing"
            elif location_count > 1:
                category = "multiple_service_locations"
            else:
                category = "nonmatching_normalized_address"
        counts[category] += 1
    counts.setdefault("incomplete_source_address", 0)
    if sum(counts.values()) != len(disposition_rows):
        raise ValueError("Service Location dispositions do not reconcile")
    return dict(sorted(counts.items()))


class JobSourceReadinessPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    readiness_version: str
    generated_at: datetime
    result: str
    source_inventory: tuple[dict[str, Any], ...]
    schema_registry: dict[str, str]
    cross_export_reconciliation: dict[str, int]
    phase1_boundary: dict[str, int]
    service_location_dispositions: dict[str, int]
    baseline: dict[str, Any]
    completeness: dict[str, int]
    acquisition_requirements: tuple[str, ...]
    proposed_stages: tuple[str, ...]
    backup_and_rollback: tuple[str, ...]
    package_sha256: str

    @model_validator(mode="after")
    def verify(self) -> JobSourceReadinessPackage:
        if self.result != "BLOCKED — SOURCE REQUIRED":
            raise ValueError("incomplete source readiness must fail closed")
        if self.completeness["available_authoritative_identities"] != (
            self.completeness["already_imported"]
            + self.completeness["known_owner_disposition"]
        ):
            raise ValueError("available source boundary does not reconcile")
        expected = sha256(
            canonical(self.model_dump(exclude={"package_sha256"}, mode="json"))
        )
        if expected != self.package_sha256:
            raise ValueError("readiness package digest mismatch")
        return self


def make_readiness_package(
    *,
    generated_at: datetime,
    inventory: Sequence[SourceArtifactInventory],
    reconciliation: CrossExportReconciliation,
    location_dispositions: Mapping[str, int],
    approximate_baseline: int = 5635,
) -> JobSourceReadinessPackage:
    cross_export_reconciliation = asdict(reconciliation)
    cross_export_reconciliation["unsupported_identity"] = sum(
        item.row_count
        for item in inventory
        if item.identity_semantics == CURRENT_IDENTITY_SEMANTICS
    )
    payload: dict[str, Any] = {
        "readiness_version": READINESS_VERSION,
        "generated_at": generated_at,
        "result": "BLOCKED — SOURCE REQUIRED",
        "source_inventory": tuple(asdict(item) for item in inventory),
        "schema_registry": {
            schema.value: schema_fingerprint(headers)
            for headers, schema in REGISTERED_SCHEMAS.items()
        },
        "cross_export_reconciliation": cross_export_reconciliation,
        "phase1_boundary": {
            "source_rows": 950,
            "already_imported": 305,
            "service_location_disposition": 642,
            "customer_identity_disposition": 3,
            "other_rejection": 0,
        },
        "service_location_dispositions": dict(location_dispositions),
        "baseline": {
            "control_total": approximate_baseline,
            "status": "approximate_unproven",
            "source": "owner-provided historical Housecall Pro count",
        },
        "completeness": {
            "approximate_historical_expected": approximate_baseline,
            "available_authoritative_identities": 950,
            "already_imported": 305,
            "known_owner_disposition": 645,
            "available_newly_eligible": 0,
            "unavailable_due_to_incomplete_export": approximate_baseline - 950,
        },
        "acquisition_requirements": (
            "All-time scope with no lower date bound and a recorded cutover timestamp.",
            "All lifecycle states, including cancelled, unscheduled, archived, deleted, and voided where available.",
            "Stable Housecall Pro Job ID; Job number must remain a separate field.",
            "Stable Customer ID and Service Address or Service Location ID.",
            "Created, scheduled, completed, and cancelled timestamps and source status.",
            "Branch or business-unit identity.",
            "Estimate, Invoice, Payment, Note, Attachment, visit, and child-work-order relationship IDs where available.",
        ),
        "proposed_stages": (
            "inventory-only validation",
            "first 25 cumulative authoritative identities",
            "first 100 cumulative authoritative identities",
            "first 500 cumulative authoritative identities",
            "full eligible authoritative boundary",
        ),
        "backup_and_rollback": (
            "No import until source completeness and identity semantics are accepted.",
            "Create and verify a restricted custom-format PostgreSQL backup before every future live stage.",
            "Use immutable manifests and identical-manifest replay with zero operational delta.",
            "Rollback restores only the verified stage backup after explicit Preview incident authorization.",
        ),
    }
    payload["package_sha256"] = "0" * 64
    provisional = JobSourceReadinessPackage.model_construct(**payload)
    payload["package_sha256"] = sha256(
        canonical(provisional.model_dump(exclude={"package_sha256"}, mode="json"))
    )
    return JobSourceReadinessPackage.model_validate(payload)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("expected a JSON object")
    return payload
