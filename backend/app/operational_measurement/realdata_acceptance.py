"""Read-only post-admission acceptance for real operational projections.

Migration owns SOURCE.4 admission and source/native identity reconciliation.
This module consumes only admitted, digest-bound projections and verifies that
their operational relationships and Schedule/Dispatch views remain coherent.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final
from uuid import UUID

from app.operational_measurement.hcp_readiness import (
    NativeScheduleProjection,
    OperationalAppointmentEvidence,
    ScheduleComparisonState,
    TechnicianCrosswalk,
    compare_source4_schedule,
)

CONTRACT_VERSION: Final = "operations.realdata.acceptance.v1"
MAX_RECORDS: Final = 10_000


class OperationalDomain(StrEnum):
    CUSTOMER = "CUSTOMER"
    SERVICE_LOCATION = "SERVICE_LOCATION"
    JOB = "JOB"
    APPOINTMENT = "APPOINTMENT"


class AcceptanceClassification(StrEnum):
    MATCHED = "MATCHED"
    PARTIAL = "PARTIAL"
    CONFLICTING = "CONFLICTING"
    MISSING_NATIVE = "MISSING_NATIVE"
    ORPHANED = "ORPHANED"


@dataclass(frozen=True, slots=True)
class ParentLineage:
    domain: OperationalDomain
    source_id: str
    native_id: UUID | None


@dataclass(frozen=True, slots=True)
class OperationalLineageProjection:
    domain: OperationalDomain
    source_id: str
    source_digest: str
    native_id: UUID | None
    company_id: UUID
    branch_id: UUID | None
    parents: tuple[ParentLineage, ...]
    native_evidence_digest: str | None


@dataclass(frozen=True, slots=True)
class DispatchAcceptanceProjection:
    source_appointment_id: str
    company_id: UUID
    branch_id: UUID
    status: str
    window_start_at: datetime | None
    window_end_at: datetime | None
    employee_ids: tuple[UUID, ...]
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class AcceptanceFinding:
    stage: str
    domain: str
    source_id: str
    classification: AcceptanceClassification
    conditions: tuple[str, ...]
    source_digest: str
    native_digest: str | None


@dataclass(frozen=True, slots=True)
class OperationalAcceptanceReport:
    contract_version: str
    company_id: UUID
    branch_id: UUID | None
    findings: tuple[AcceptanceFinding, ...]
    counts: dict[str, int]
    source_record_count: int
    appointment_count: int
    evidence_digest: str
    mutation_authority: str = "none"


def _digest(value: object) -> str:
    def default(item: object) -> str:
        if isinstance(item, (UUID, datetime, StrEnum)):
            return str(item)
        raise TypeError(f"unsupported digest value: {type(item).__name__}")

    encoded = json.dumps(
        value,
        default=default,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _lineage_findings(
    records: tuple[OperationalLineageProjection, ...],
    *,
    company_id: UUID,
    branch_id: UUID | None,
) -> tuple[AcceptanceFinding, ...]:
    grouped: dict[tuple[OperationalDomain, str], list[OperationalLineageProjection]] = {}
    for record in records:
        grouped.setdefault((record.domain, record.source_id), []).append(record)
    findings: list[AcceptanceFinding] = []
    for key in sorted(grouped, key=lambda item: (item[0].value, item[1])):
        duplicates = grouped[key]
        record = min(
            duplicates,
            key=lambda item: (item.source_digest, item.native_evidence_digest or ""),
        )
        conditions: list[str] = []
        classification = AcceptanceClassification.MATCHED
        if len(duplicates) > 1:
            conditions.append("DUPLICATE_NATIVE_SOURCE_IDENTITY")
            classification = AcceptanceClassification.CONFLICTING
        elif record.company_id != company_id or (
            branch_id is not None
            and record.branch_id is not None
            and record.branch_id != branch_id
        ):
            conditions.append("COMPANY_OR_BRANCH_SCOPE_CONFLICT")
            classification = AcceptanceClassification.CONFLICTING
        elif record.native_id is None or record.native_evidence_digest is None:
            conditions.append("NATIVE_IDENTITY_MISSING")
            classification = AcceptanceClassification.MISSING_NATIVE
        else:
            for parent in record.parents:
                parent_records = grouped.get((parent.domain, parent.source_id), [])
                if not parent_records:
                    conditions.append(f"ORPHANED_{parent.domain.value}_SOURCE")
                    classification = AcceptanceClassification.ORPHANED
                    continue
                parent_record = parent_records[0]
                if parent_record.native_id is None:
                    conditions.append(f"ORPHANED_{parent.domain.value}_NATIVE")
                    classification = AcceptanceClassification.ORPHANED
                elif parent.native_id != parent_record.native_id:
                    conditions.append(f"{parent.domain.value}_RELATIONSHIP_CONFLICT")
                    classification = AcceptanceClassification.CONFLICTING
                if parent_record.company_id != record.company_id or (
                    parent_record.branch_id is not None
                    and record.branch_id is not None
                    and parent_record.branch_id != record.branch_id
                ):
                    conditions.append(f"{parent.domain.value}_SCOPE_CONFLICT")
                    classification = AcceptanceClassification.CONFLICTING
        findings.append(
            AcceptanceFinding(
                "LINEAGE",
                record.domain.value,
                record.source_id,
                classification,
                tuple(sorted(set(conditions))),
                record.source_digest,
                record.native_evidence_digest,
            )
        )
    return tuple(findings)


def _projection_findings(
    lineage: tuple[OperationalLineageProjection, ...],
    appointments: tuple[OperationalAppointmentEvidence, ...],
    schedules: tuple[NativeScheduleProjection, ...],
    dispatches: tuple[DispatchAcceptanceProjection, ...],
    *,
    crosswalks: tuple[TechnicianCrosswalk, ...],
) -> tuple[AcceptanceFinding, ...]:
    schedule_report = compare_source4_schedule(
        appointments, schedules, crosswalks=crosswalks
    )
    schedule_by_source = {
        item.source_appointment_id: item for item in schedule_report.rows
    }
    schedule_native = {item.source_appointment_id: item for item in schedules}
    dispatch_grouped: dict[str, list[DispatchAcceptanceProjection]] = {}
    for dispatch_item in dispatches:
        dispatch_grouped.setdefault(
            dispatch_item.source_appointment_id, []
        ).append(dispatch_item)
    source_grouped: dict[str, list[OperationalAppointmentEvidence]] = {}
    for source_item in appointments:
        source_grouped.setdefault(source_item.source_id, []).append(source_item)
    source_digests = {
        source_id: min(item.source_digest for item in rows)
        for source_id, rows in source_grouped.items()
    }
    appointment_lineage = {
        item.source_id: item
        for item in lineage
        if item.domain is OperationalDomain.APPOINTMENT
    }
    source_by_id = {
        source_id: min(rows, key=lambda item: item.source_digest)
        for source_id, rows in source_grouped.items()
    }
    findings: list[AcceptanceFinding] = []
    for source_id in sorted(source_digests):
        schedule = schedule_native.get(source_id)
        schedule_result = schedule_by_source[source_id]
        dispatch_rows = dispatch_grouped.get(source_id, [])
        conditions = list(schedule_result.conditions)
        if schedule is None:
            classification = AcceptanceClassification.MISSING_NATIVE
        elif schedule_result.state is ScheduleComparisonState.CONFLICTING:
            classification = AcceptanceClassification.CONFLICTING
        elif schedule_result.state is ScheduleComparisonState.PARTIAL:
            classification = AcceptanceClassification.PARTIAL
        else:
            classification = AcceptanceClassification.MATCHED
        if len({item.source_digest for item in source_grouped[source_id]}) > 1:
            conditions.append("CONFLICTING_SOURCE_REPLAY")
            classification = AcceptanceClassification.CONFLICTING
        source = source_by_id[source_id]
        lineage_record = appointment_lineage.get(source_id)
        if lineage_record is None:
            conditions.append("APPOINTMENT_LINEAGE_MISSING")
            classification = AcceptanceClassification.ORPHANED
        else:
            parent_by_domain = {item.domain: item for item in lineage_record.parents}
            job_parent = parent_by_domain.get(OperationalDomain.JOB)
            customer_parent = parent_by_domain.get(OperationalDomain.CUSTOMER)
            location_parent = parent_by_domain.get(OperationalDomain.SERVICE_LOCATION)
            if job_parent is None or job_parent.source_id != source.source_job_id:
                conditions.append("JOB_RELATIONSHIP_CONFLICT")
            if customer_parent is None or customer_parent.native_id != source.customer_id:
                conditions.append("CUSTOMER_RELATIONSHIP_CONFLICT")
            if (
                location_parent is None
                or location_parent.native_id != source.service_location_id
            ):
                conditions.append("SERVICE_LOCATION_RELATIONSHIP_CONFLICT")
            if any(item.endswith("RELATIONSHIP_CONFLICT") for item in conditions):
                classification = AcceptanceClassification.CONFLICTING
        dispatch = dispatch_rows[0] if dispatch_rows else None
        if not dispatch_rows:
            conditions.append("DISPATCH_PROJECTION_MISSING")
            if classification is AcceptanceClassification.MATCHED:
                classification = AcceptanceClassification.MISSING_NATIVE
        elif len(dispatch_rows) > 1:
            conditions.append("DUPLICATE_DISPATCH_SOURCE_IDENTITY")
            classification = AcceptanceClassification.CONFLICTING
        elif schedule is not None and dispatch is not None:
            if (schedule.company_id, schedule.branch_id) != (
                dispatch.company_id,
                dispatch.branch_id,
            ):
                conditions.append("SCHEDULE_DISPATCH_SCOPE_DISAGREEMENT")
            if schedule.status != dispatch.status:
                conditions.append("SCHEDULE_DISPATCH_STATUS_DISAGREEMENT")
            if (schedule.window_start_at, schedule.window_end_at) != (
                dispatch.window_start_at,
                dispatch.window_end_at,
            ):
                conditions.append("SCHEDULE_DISPATCH_WINDOW_DISAGREEMENT")
            if tuple(sorted(schedule.employee_ids, key=str)) != tuple(
                sorted(dispatch.employee_ids, key=str)
            ):
                conditions.append("SCHEDULE_DISPATCH_TECHNICIAN_DISAGREEMENT")
            if any(item.startswith("SCHEDULE_DISPATCH_") for item in conditions):
                classification = AcceptanceClassification.CONFLICTING
        native_digests = sorted(
            item
            for item in (
                schedule.evidence_digest if schedule else None,
                dispatch.evidence_digest if dispatch else None,
            )
            if item is not None
        )
        findings.append(
            AcceptanceFinding(
                "OPERATIONAL_PROJECTION",
                OperationalDomain.APPOINTMENT.value,
                source_id,
                classification,
                tuple(sorted(set(conditions))),
                source_digests[source_id],
                _digest(native_digests) if native_digests else None,
            )
        )
    return tuple(findings)


def verify_operational_chain(
    lineage: tuple[OperationalLineageProjection, ...],
    appointments: tuple[OperationalAppointmentEvidence, ...],
    schedules: tuple[NativeScheduleProjection, ...],
    dispatches: tuple[DispatchAcceptanceProjection, ...],
    *,
    company_id: UUID,
    branch_id: UUID | None,
    crosswalks: tuple[TechnicianCrosswalk, ...] = (),
) -> OperationalAcceptanceReport:
    """Verify admitted operational lineage and product projections without writes."""
    if any(
        len(items) > MAX_RECORDS
        for items in (lineage, appointments, schedules, dispatches)
    ):
        raise ValueError("operational acceptance input exceeds its bound")
    findings = tuple(
        sorted(
            (
                *_lineage_findings(
                    lineage, company_id=company_id, branch_id=branch_id
                ),
                *_projection_findings(
                    lineage,
                    appointments,
                    schedules,
                    dispatches,
                    crosswalks=crosswalks,
                ),
            ),
            key=lambda item: (item.stage, item.domain, item.source_id),
        )
    )
    counts = dict(
        sorted(Counter(item.classification.value for item in findings).items())
    )
    payload = {
        "contract": CONTRACT_VERSION,
        "company_id": company_id,
        "branch_id": branch_id,
        "findings": [asdict(item) for item in findings],
    }
    return OperationalAcceptanceReport(
        CONTRACT_VERSION,
        company_id,
        branch_id,
        findings,
        counts,
        len(lineage),
        len(appointments),
        _digest(payload),
    )
