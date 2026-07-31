"""Reviewed Housecall Pro Job and Appointment migration contracts.

The legacy export does not carry Customer or Service Location identifiers.  This
adapter therefore accepts a row only when its exact normalized service address
and every matching supplied customer signal converge on one Customer aggregate
already present in the accepted customer migration manifest.
"""

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
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.operational_migration.service import (
    AppointmentMigrationRecord,
    JobMigrationRecord,
)

SOURCE_SYSTEM = "housecall_pro"
EXPORT_VERSION = "housecall_pro_job_export_20240321_v1"
REVIEW_VERSION = "operational-migration-phase1-review/v1"
MANIFEST_VERSION = "operational-migration-phase1-manifest/v1"
SELECTION_VERSION = "source-identity-sha256/v1"
TRANSFORMATION_VERSION = "operational-phase1-hcp/v1"

JOB_HEADERS = (
    "Invoice",
    "HCP Id",
    "Date",
    "Customer",
    "First Name",
    "Last Name",
    "Email",
    "Company",
    "Mobile Phone",
    "Home Phone",
    "Customer Tags",
    "Address",
    "Description",
    "Line Items",
    "Amount",
    "Labor",
    "Materials",
    "Subtotal",
    "Payment History",
    "Credit Card Fee",
    "Job Tags",
    "Notes",
    "Employee",
    "Job Status",
    "Finished",
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode())


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _normalized(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = text.encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", ascii_text)


def _phone(value: object) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[-10:] if len(digits) >= 10 else digits


def _location_source_id(customer_source_id: str) -> str:
    value = f"{customer_source_id}::service-location::1"
    if len(value) > 191:
        raise ValueError("derived service-location source identity is too long")
    return value


def _local_timestamp(value: str, *, finished: bool = False) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    pattern = "%Y-%m-%d %I:%M%p" if finished else "%Y-%m-%d %H:%M"
    return datetime.strptime(value.lower(), pattern).replace(
        tzinfo=ZoneInfo("America/New_York")
    )


@dataclass(frozen=True)
class ParentCrosswalk:
    customer_source_id: str
    service_location_source_id: str


@dataclass(frozen=True)
class Phase1Disposition:
    row_number: int
    source_id_sha256: str | None
    category: str


@dataclass(frozen=True)
class Phase1Review:
    source_sha256: str
    customer_review_sha256: str
    customer_manifest_sha256: str
    transformation_sha256: str
    jobs: tuple[JobMigrationRecord, ...]
    appointments: tuple[AppointmentMigrationRecord, ...]
    dispositions: tuple[Phase1Disposition, ...]
    source_count: int

    def payload(self) -> dict[str, object]:
        return {
            "review_version": REVIEW_VERSION,
            "source_system": SOURCE_SYSTEM,
            "export_version": EXPORT_VERSION,
            "transformation_version": TRANSFORMATION_VERSION,
            "source_sha256": self.source_sha256,
            "customer_review_sha256": self.customer_review_sha256,
            "customer_manifest_sha256": self.customer_manifest_sha256,
            "transformation_sha256": self.transformation_sha256,
            "source_count": self.source_count,
            "eligible_job_count": len(self.jobs),
            "eligible_appointment_count": len(self.appointments),
            "jobs": [asdict(item) for item in self.jobs],
            "appointments": [asdict(item) for item in self.appointments],
            "dispositions": [asdict(item) for item in self.dispositions],
            "disposition_counts": dict(
                sorted(Counter(item.category for item in self.dispositions).items())
            ),
        }


class ReviewedOperationalOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    review_version: Literal["operational-migration-phase1-review/v1"]
    source_system: Literal["housecall_pro"]
    export_version: Literal["housecall_pro_job_export_20240321_v1"]
    transformation_version: Literal["operational-phase1-hcp/v1"]
    source_sha256: str
    customer_review_sha256: str
    customer_manifest_sha256: str
    transformation_sha256: str
    source_count: int = Field(ge=0)
    eligible_job_count: int = Field(ge=0)
    eligible_appointment_count: int = Field(ge=0)
    jobs: tuple[dict[str, Any], ...]
    appointments: tuple[dict[str, Any], ...]
    dispositions: tuple[dict[str, Any], ...]
    disposition_counts: dict[str, int]
    review_sha256: str

    @model_validator(mode="after")
    def validate_integrity(self) -> ReviewedOperationalOutput:
        if self.eligible_job_count != len(self.jobs):
            raise ValueError("eligible Job count does not reconcile")
        if self.eligible_appointment_count != len(self.appointments):
            raise ValueError("eligible Appointment count does not reconcile")
        if self.source_count != self.eligible_job_count + len(self.dispositions):
            raise ValueError("source count does not reconcile")
        expected = _sha256_text(
            _canonical(self.model_dump(exclude={"review_sha256"}, mode="json"))
        )
        if expected != self.review_sha256:
            raise ValueError("reviewed operational output digest mismatch")
        return self

    def job_records(self) -> tuple[JobMigrationRecord, ...]:
        timestamp_fields = {
            "scheduled_start_at",
            "scheduled_end_at",
            "activated_at",
            "started_at",
            "completed_at",
        }
        records = []
        for item in self.jobs:
            payload = dict(item)
            for field in timestamp_fields:
                if isinstance(payload.get(field), str):
                    payload[field] = datetime.fromisoformat(payload[field])
            if isinstance(payload.get("assigned_technician_source_ids"), list):
                payload["assigned_technician_source_ids"] = tuple(
                    payload["assigned_technician_source_ids"]
                )
            records.append(JobMigrationRecord(**payload))
        return tuple(records)

    def appointment_records(self) -> tuple[AppointmentMigrationRecord, ...]:
        records = []
        for item in self.appointments:
            payload = dict(item)
            for field in ("arrival_window_start_at", "arrival_window_end_at"):
                if isinstance(payload.get(field), str):
                    payload[field] = datetime.fromisoformat(payload[field])
            if isinstance(payload.get("assigned_technician_source_ids"), list):
                payload["assigned_technician_source_ids"] = tuple(
                    payload["assigned_technician_source_ids"]
                )
            records.append(AppointmentMigrationRecord(**payload))
        return tuple(records)


class OperationalPhase1Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_version: Literal["operational-migration-phase1-manifest/v1"]
    selection_version: Literal["source-identity-sha256/v1"]
    stage_identifier: str
    prior_stage_identifier: str | None
    prior_stage_manifest_sha256: str | None
    source_system: Literal["housecall_pro"]
    source_sha256: str
    export_version: Literal["housecall_pro_job_export_20240321_v1"]
    transformation_version: Literal["operational-phase1-hcp/v1"]
    transformation_sha256: str
    reviewed_output_sha256: str
    customer_manifest_sha256: str
    ordered_job_source_identities: tuple[str, ...]
    ordered_job_identity_sha256: tuple[str, ...]
    ordered_appointment_source_identities: tuple[str, ...]
    expected_jobs: int = Field(ge=0)
    expected_appointments: int = Field(ge=0)
    expected_business_events: int = Field(ge=0)
    eligibility: dict[str, int]
    replay_digest: str
    generated_at: datetime
    manifest_sha256: str

    @model_validator(mode="after")
    def validate_integrity(self) -> OperationalPhase1Manifest:
        if self.expected_jobs != len(self.ordered_job_source_identities):
            raise ValueError("manifest Job count does not reconcile")
        if self.expected_appointments != len(
            self.ordered_appointment_source_identities
        ):
            raise ValueError("manifest Appointment count does not reconcile")
        if tuple(map(_sha256_text, self.ordered_job_source_identities)) != (
            self.ordered_job_identity_sha256
        ):
            raise ValueError("manifest identity digests do not reconcile")
        expected = _sha256_text(
            _canonical(self.model_dump(exclude={"manifest_sha256"}, mode="json"))
        )
        if expected != self.manifest_sha256:
            raise ValueError("operational stage manifest digest mismatch")
        return self


def _add(index: dict[str, set[int]], key: str, aggregate_index: int) -> None:
    if key:
        index[key].add(aggregate_index)


def _crosswalk(
    reviewed_customer: Mapping[str, object],
    customer_manifest: Mapping[str, object],
) -> tuple[
    list[Mapping[str, object]],
    dict[str, dict[str, set[int]]],
]:
    allowed = set(customer_manifest["ordered_source_identities"])  # type: ignore[arg-type]
    aggregates = [
        item
        for item in reviewed_customer["aggregates"]  # type: ignore[union-attr]
        if item["source_identity"] in allowed
    ]
    indexes: dict[str, dict[str, set[int]]] = {
        key: defaultdict(set) for key in ("email", "phone", "name", "address")
    }
    for index, aggregate in enumerate(aggregates):
        customer = json.loads(str(aggregate["customer_json"]))
        contact = (
            json.loads(str(aggregate["contact_json"]))
            if aggregate.get("contact_json")
            else {}
        )
        _add(indexes["email"], _normalized(contact.get("email")), index)
        for field in ("mobile_phone", "office_phone"):
            _add(indexes["phone"], _phone(contact.get(field)), index)
        for value in (
            customer.get("display_name"),
            customer.get("legal_name"),
            " ".join(
                filter(None, (contact.get("first_name"), contact.get("last_name")))
            ),
        ):
            _add(indexes["name"], _normalized(value), index)
        locations = aggregate["service_location_json"]
        if len(locations) == 1:
            location = json.loads(str(locations[0]))
            _add(
                indexes["address"],
                _normalized(
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
    return aggregates, indexes


def _parent(
    row: Mapping[str, str],
    aggregates: Sequence[Mapping[str, object]],
    indexes: Mapping[str, Mapping[str, set[int]]],
) -> tuple[ParentCrosswalk | None, str | None]:
    address = indexes["address"].get(_normalized(row["Address"]), set())
    if not address:
        return None, "service_location_not_migrated"
    signals: list[set[int]] = []
    email = _normalized(row["Email"])
    if email and (matches := indexes["email"].get(email)):
        signals.append(matches)
    phones = set().union(
        *(
            indexes["phone"].get(_phone(row[field]), set())
            for field in ("Mobile Phone", "Home Phone")
            if _phone(row[field])
        )
    )
    if phones:
        signals.append(phones)
    names = indexes["name"].get(_normalized(row["Customer"]), set()) | indexes[
        "name"
    ].get(_normalized(f"{row['First Name']} {row['Last Name']}"), set())
    if names:
        signals.append(names)
    if not signals:
        return None, "customer_identity_unresolved"
    candidates = set(address)
    for signal in signals:
        candidates &= signal
    if not candidates:
        return None, "customer_signals_conflict"
    if len(candidates) != 1:
        return None, "customer_identity_ambiguous"
    aggregate = aggregates[next(iter(candidates))]
    customer_source_id = str(aggregate["source_identity"])
    return (
        ParentCrosswalk(
            customer_source_id=customer_source_id,
            service_location_source_id=_location_source_id(customer_source_id),
        ),
        None,
    )


def _read_export(source_bytes: bytes) -> list[dict[str, str]]:
    text = source_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != JOB_HEADERS:
        raise ValueError("unsupported Housecall Pro Job export layout")
    return [dict(row) for row in reader]


def transform_phase1(
    *,
    source_bytes: bytes,
    reviewed_customer_bytes: bytes,
    customer_manifest_bytes: bytes,
) -> Phase1Review:
    reviewed_customer = json.loads(reviewed_customer_bytes)
    customer_manifest = json.loads(customer_manifest_bytes)
    if reviewed_customer.get("review_sha256") != customer_manifest.get(
        "reviewed_output_sha256"
    ):
        raise ValueError("customer reviewed output does not match final manifest")
    aggregates, indexes = _crosswalk(reviewed_customer, customer_manifest)
    jobs: list[JobMigrationRecord] = []
    appointments: list[AppointmentMigrationRecord] = []
    dispositions: list[Phase1Disposition] = []
    seen: set[str] = set()
    for row_number, row in enumerate(_read_export(source_bytes), start=2):
        source_id = row["HCP Id"].strip()
        source_hash = _sha256_text(source_id) if source_id else None
        if not source_id:
            dispositions.append(
                Phase1Disposition(row_number, None, "missing_job_source_identity")
            )
            continue
        if source_id in seen:
            dispositions.append(
                Phase1Disposition(
                    row_number, source_hash, "duplicate_job_source_identity"
                )
            )
            continue
        seen.add(source_id)
        parent, category = _parent(row, aggregates, indexes)
        if parent is None:
            dispositions.append(
                Phase1Disposition(row_number, source_hash, category or "unresolved")
            )
            continue
        scheduled = _local_timestamp(row["Date"])
        finished = _local_timestamp(row["Finished"], finished=True)
        employee_hash = (
            _sha256_text(row["Employee"].strip()) if row["Employee"].strip() else None
        )
        metadata: dict[str, object] = {
            "export_version": EXPORT_VERSION,
            "source_status": row["Job Status"].strip(),
            "scheduled_at": scheduled.isoformat() if scheduled else None,
            "finished_at": finished.isoformat() if finished else None,
            "employee_source_sha256": employee_hash,
            "lifecycle_status_deferred": True,
        }
        job = JobMigrationRecord(
            source_id=source_id,
            source_customer_id=parent.customer_source_id,
            source_service_location_id=parent.service_location_source_id,
            source_job_number=row["Invoice"].strip() or None,
            status="draft",
            summary=row["Description"].strip() or None,
            description=row["Notes"].strip() or None,
            external_metadata=metadata,
        )
        jobs.append(job)
        if scheduled is not None:
            appointments.append(
                AppointmentMigrationRecord(
                    source_id=f"{source_id}::appointment::1",
                    source_job_id=source_id,
                    source_customer_id=parent.customer_source_id,
                    source_service_location_id=parent.service_location_source_id,
                    status="draft",
                    arrival_window_start_at=None,
                    arrival_window_end_at=None,
                    duration_minutes=None,
                    external_metadata={
                        "export_version": EXPORT_VERSION,
                        "source_scheduled_at": scheduled.isoformat(),
                        "scheduling_window_deferred": True,
                    },
                )
            )
    ordered_jobs = tuple(sorted(jobs, key=lambda item: _sha256_text(item.source_id)))
    appointment_by_job = {item.source_job_id: item for item in appointments}
    ordered_appointments = tuple(
        appointment_by_job[item.source_id]
        for item in ordered_jobs
        if item.source_id in appointment_by_job
    )
    transform_payload = {
        "transformation_version": TRANSFORMATION_VERSION,
        "jobs": [asdict(item) for item in ordered_jobs],
        "appointments": [asdict(item) for item in ordered_appointments],
        "dispositions": [asdict(item) for item in dispositions],
    }
    return Phase1Review(
        source_sha256=_sha256_bytes(source_bytes),
        customer_review_sha256=str(reviewed_customer["review_sha256"]),
        customer_manifest_sha256=str(customer_manifest["manifest_sha256"]),
        transformation_sha256=_sha256_text(_canonical(transform_payload)),
        jobs=ordered_jobs,
        appointments=ordered_appointments,
        dispositions=tuple(dispositions),
        source_count=len(jobs) + len(dispositions),
    )


def reviewed_output(review: Phase1Review) -> ReviewedOperationalOutput:
    payload = review.payload()
    payload["review_sha256"] = _sha256_text(_canonical(payload))
    return ReviewedOperationalOutput.model_validate(payload)


def select_stage(
    reviewed: ReviewedOperationalOutput,
    *,
    stage_identifier: str,
    limit: int | None,
    prior: OperationalPhase1Manifest | None,
    generated_at: datetime,
) -> OperationalPhase1Manifest:
    jobs = reviewed.job_records()
    selected = jobs if limit is None else jobs[:limit]
    selected_ids = tuple(item.source_id for item in selected)
    if (
        prior
        and selected_ids[: prior.expected_jobs] != prior.ordered_job_source_identities
    ):
        raise ValueError("stage is not a cumulative extension of its prior stage")
    appointments = tuple(
        item
        for item in reviewed.appointment_records()
        if item.source_job_id in set(selected_ids)
    )
    replay_digest = _sha256_text(
        _canonical(
            {
                "source_system": SOURCE_SYSTEM,
                "jobs": [asdict(item) for item in selected],
                "appointments": [asdict(item) for item in appointments],
            }
        )
    )
    payload: dict[str, object] = {
        "manifest_version": MANIFEST_VERSION,
        "selection_version": SELECTION_VERSION,
        "stage_identifier": stage_identifier,
        "prior_stage_identifier": prior.stage_identifier if prior else None,
        "prior_stage_manifest_sha256": prior.manifest_sha256 if prior else None,
        "source_system": SOURCE_SYSTEM,
        "source_sha256": reviewed.source_sha256,
        "export_version": EXPORT_VERSION,
        "transformation_version": TRANSFORMATION_VERSION,
        "transformation_sha256": reviewed.transformation_sha256,
        "reviewed_output_sha256": reviewed.review_sha256,
        "customer_manifest_sha256": reviewed.customer_manifest_sha256,
        "ordered_job_source_identities": selected_ids,
        "ordered_job_identity_sha256": tuple(map(_sha256_text, selected_ids)),
        "ordered_appointment_source_identities": tuple(
            item.source_id for item in appointments
        ),
        "expected_jobs": len(selected),
        "expected_appointments": len(appointments),
        "expected_business_events": len(selected) + len(appointments),
        "eligibility": {
            "source": reviewed.source_count,
            "eligible_jobs": reviewed.eligible_job_count,
            "eligible_appointments": reviewed.eligible_appointment_count,
            **reviewed.disposition_counts,
        },
        "replay_digest": replay_digest,
        "generated_at": generated_at,
    }
    payload["manifest_sha256"] = "0" * 64
    provisional = OperationalPhase1Manifest.model_construct(**payload)
    payload["manifest_sha256"] = _sha256_text(
        _canonical(provisional.model_dump(exclude={"manifest_sha256"}, mode="json"))
    )
    return OperationalPhase1Manifest.model_validate(payload)


def load_restricted_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def stage_records(
    reviewed: ReviewedOperationalOutput,
    manifest: OperationalPhase1Manifest,
) -> tuple[tuple[JobMigrationRecord, ...], tuple[AppointmentMigrationRecord, ...]]:
    if (
        reviewed.review_sha256 != manifest.reviewed_output_sha256
        or reviewed.source_sha256 != manifest.source_sha256
        or reviewed.transformation_sha256 != manifest.transformation_sha256
    ):
        raise ValueError("reviewed output does not match operational manifest")
    jobs_by_id = {item.source_id: item for item in reviewed.job_records()}
    appointments_by_id = {
        item.source_id: item for item in reviewed.appointment_records()
    }
    jobs = tuple(jobs_by_id[item] for item in manifest.ordered_job_source_identities)
    appointments = tuple(
        appointments_by_id[item]
        for item in manifest.ordered_appointment_source_identities
    )
    digest = _sha256_text(
        _canonical(
            {
                "source_system": SOURCE_SYSTEM,
                "jobs": [asdict(item) for item in jobs],
                "appointments": [asdict(item) for item in appointments],
            }
        )
    )
    if digest != manifest.replay_digest:
        raise ValueError("operational stage replay digest mismatch")
    return jobs, appointments
