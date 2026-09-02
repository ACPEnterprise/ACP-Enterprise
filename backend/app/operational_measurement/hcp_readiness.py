"""Provider-neutral readiness over Migration-admitted operational evidence.

This module never reads sealed HCP rows and owns no Migration disposition.  It
accepts digest-bound projections supplied through the sanctioned Migration
contract and reports whether downstream operational measurements are usable.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Final
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.dispatch.intelligence import EvidenceRef, EvidenceState, TimeWindow
from app.dispatch.intelligence_runtime import MeasuredDuration
from app.operational_migration.service import (
    AppointmentMigrationRecord,
    JobMigrationRecord,
)

CONTRACT_VERSION: Final = "hcp-operational-measurement-readiness.v1"
ACCEPTANCE_VERSION: Final = "hcp-operational-date-acceptance.v1"
MAX_BATCH_SIZE: Final = 10_000
MAX_WINDOW_HOURS: Final = 24


class ReadinessState(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    ABSENT = "ABSENT"
    CONFLICTING = "CONFLICTING"
    SOURCE_REQUIRED = "SOURCE_REQUIRED"


class DurationCandidateClass(StrEnum):
    QUALIFIED_MEASURED_DURATION = "QUALIFIED_MEASURED_DURATION"
    SCHEDULED_DURATION_ONLY = "SCHEDULED_DURATION_ONLY"
    PARTIAL_DURATION_EVIDENCE = "PARTIAL_DURATION_EVIDENCE"
    INVALID_DURATION = "INVALID_DURATION"
    SOURCE_REQUIRED = "SOURCE_REQUIRED"


class DateDisposition(StrEnum):
    ADMITTED = "ADMITTED"
    HELD = "HELD"
    UNMAPPED_TECHNICIAN = "UNMAPPED_TECHNICIAN"
    INCOMPLETE_WINDOW = "INCOMPLETE_WINDOW"
    CANCELED_HISTORICAL = "CANCELED_HISTORICAL"
    OTHER_EXPLICIT_DISPOSITION = "OTHER_EXPLICIT_DISPOSITION"


class TechnicianMappingState(StrEnum):
    MAPPED_ACTIVE = "MAPPED_ACTIVE"
    MAPPED_HISTORICAL_INACTIVE = "MAPPED_HISTORICAL_INACTIVE"
    UNMAPPED = "UNMAPPED"
    MULTIPLE = "MULTIPLE"
    NONE_REPORTED = "NONE_REPORTED"


@dataclass(frozen=True, slots=True)
class SourceFieldAudit:
    field: str
    state: ReadinessState
    admitted_contract: str | None
    limitation: str | None = None


@dataclass(frozen=True, slots=True)
class TechnicianCrosswalk:
    source_technician_id: str
    employee_id: UUID | None
    employee_active: bool | None
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class OperationalJobEvidence:
    source_id: str
    source_digest: str
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID
    status: str
    scheduled_start_at: datetime | None
    scheduled_end_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    service_category: str | None
    source_technician_ids: tuple[str, ...]
    pause_intervals: tuple[TimeWindow, ...] = ()


@dataclass(frozen=True, slots=True)
class OperationalAppointmentEvidence:
    source_id: str
    source_digest: str
    source_job_id: str
    company_id: UUID
    branch_id: UUID
    customer_id: UUID | None
    service_location_id: UUID | None
    status: str
    window_start_at: datetime | None
    window_end_at: datetime | None
    scheduled_duration_minutes: int | None
    source_technician_ids: tuple[str, ...]
    parent_admitted: bool
    migration_held: bool = False


@dataclass(frozen=True, slots=True)
class WindowValidation:
    state: ReadinessState
    window: TimeWindow | None
    conditions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DurationCandidate:
    source_job_id: str
    classification: DurationCandidateClass
    scheduled_minutes: int | None
    elapsed_work_minutes: int | None
    active_minutes: int | None
    limitations: tuple[str, ...]
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class TechnicianMapping:
    state: TechnicianMappingState
    employee_ids: tuple[UUID, ...]
    unresolved_source_ids: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AppointmentAcceptance:
    source_appointment_id: str
    source_digest: str
    disposition: DateDisposition
    conditions: tuple[str, ...]
    technician_state: TechnicianMappingState


@dataclass(frozen=True, slots=True)
class DateAcceptanceReport:
    contract_version: str
    local_date: date
    timezone: str
    source_count: int
    dispositions: tuple[AppointmentAcceptance, ...]
    disposition_counts: dict[str, int]
    reconciliation_delta: int
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class DispatchReadiness:
    state: EvidenceState
    admitted_constraints: tuple[str, ...]
    unknown_constraints: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DataQualityCondition:
    source_type: str
    source_id: str
    code: str
    state: ReadinessState
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class EconomicsOperationalReadiness:
    state: ReadinessState
    admissible_dimensions: tuple[str, ...]
    missing_dimensions: tuple[str, ...]
    prohibited_inferences: tuple[str, ...]
    evidence_digest: str


def source_field_audit() -> tuple[SourceFieldAudit, ...]:
    """Describe accepted SOURCE.4 layout versus current downstream authority."""
    available = (
        ("source_job_identity", "JobMigrationRecord.source_id"),
        ("source_appointment_identity", "AppointmentMigrationRecord.source_id"),
        ("customer_relationship", "AppointmentMigrationRecord.source_customer_id"),
        (
            "service_location_relationship",
            "AppointmentMigrationRecord.source_service_location_id",
        ),
        ("job_lifecycle", "JobMigrationRecord.status"),
        ("appointment_lifecycle", "AppointmentMigrationRecord.status"),
        ("scheduled_window", "AppointmentMigrationRecord.arrival_window_*"),
        ("scheduled_duration", "AppointmentMigrationRecord.duration_minutes"),
        ("source_technician_identity", "assigned_technician_source_ids"),
        ("work_started", "JobMigrationRecord.started_at"),
        ("work_completed", "JobMigrationRecord.completed_at"),
    )
    result = [
        SourceFieldAudit(field, ReadinessState.AVAILABLE, contract)
        for field, contract in available
    ]
    result.extend(
        (
            SourceFieldAudit(
                "arrival_timestamp",
                ReadinessState.PARTIAL,
                "SOURCE.4 work_timestamps.on_my_way_at",
                "Present in sealed layout but not retained by JobMigrationRecord.",
            ),
            SourceFieldAudit(
                "pause_resume",
                ReadinessState.ABSENT,
                None,
                "No accepted pause interval contract.",
            ),
            SourceFieldAudit(
                "service_category",
                ReadinessState.PARTIAL,
                "SOURCE.4 job_fields.job_type",
                "Validated in the source layout but not retained by JobMigrationRecord.",
            ),
            SourceFieldAudit(
                "business_unit_branch",
                ReadinessState.PARTIAL,
                "SOURCE.4 job_fields.business_unit",
                "Validated but not admitted as Branch provenance.",
            ),
            SourceFieldAudit(
                "priority",
                ReadinessState.SOURCE_REQUIRED,
                None,
                "No accepted HCP priority mapping.",
            ),
            SourceFieldAudit(
                "timezone_provenance",
                ReadinessState.PARTIAL,
                "SOURCE.4 schedule.time_zone",
                "Parsed timestamps exist, but the provider timezone field is not retained downstream.",
            ),
            SourceFieldAudit(
                "technician_crosswalk",
                ReadinessState.PARTIAL,
                "hcp-employee-crosswalk/v1",
                "A source ID must resolve explicitly; no Employee creation or name matching is permitted.",
            ),
        )
    )
    return tuple(result)


def adapt_migration_job(
    record: JobMigrationRecord,
    *,
    company_id: UUID,
    branch_id: UUID,
    customer_id: UUID,
    service_location_id: UUID,
) -> OperationalJobEvidence:
    metadata = record.external_metadata or {}
    return OperationalJobEvidence(
        source_id=record.source_id,
        source_digest=_required_digest(metadata.get("source_digest")),
        company_id=company_id,
        branch_id=branch_id,
        customer_id=customer_id,
        service_location_id=service_location_id,
        status=record.status,
        scheduled_start_at=record.scheduled_start_at,
        scheduled_end_at=record.scheduled_end_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        service_category=None,
        source_technician_ids=record.assigned_technician_source_ids,
    )


def adapt_migration_appointment(
    record: AppointmentMigrationRecord,
    *,
    company_id: UUID,
    branch_id: UUID,
    customer_id: UUID | None,
    service_location_id: UUID | None,
    parent_admitted: bool,
    migration_held: bool = False,
) -> OperationalAppointmentEvidence:
    metadata = record.external_metadata or {}
    return OperationalAppointmentEvidence(
        source_id=record.source_id,
        source_digest=_required_digest(metadata.get("source_digest")),
        source_job_id=record.source_job_id,
        company_id=company_id,
        branch_id=branch_id,
        customer_id=customer_id,
        service_location_id=service_location_id,
        status=record.status,
        window_start_at=record.arrival_window_start_at,
        window_end_at=record.arrival_window_end_at,
        scheduled_duration_minutes=record.duration_minutes,
        source_technician_ids=record.assigned_technician_source_ids,
        parent_admitted=parent_admitted,
        migration_held=migration_held,
    )


def validate_window(
    start_at: datetime | None,
    end_at: datetime | None,
    *,
    accepted_timezone: str,
) -> WindowValidation:
    try:
        zone = ZoneInfo(accepted_timezone)
    except ZoneInfoNotFoundError:
        return WindowValidation(ReadinessState.CONFLICTING, None, ("TIMEZONE_INVALID",))
    if start_at is None or end_at is None:
        return WindowValidation(ReadinessState.ABSENT, None, ("WINDOW_MISSING",))
    if start_at.tzinfo is None or end_at.tzinfo is None:
        return WindowValidation(ReadinessState.CONFLICTING, None, ("TIMEZONE_MISSING",))
    if end_at <= start_at:
        return WindowValidation(ReadinessState.CONFLICTING, None, ("WINDOW_REVERSED",))
    conditions: list[str] = []
    if end_at - start_at > timedelta(hours=MAX_WINDOW_HOURS):
        conditions.append("WINDOW_BROAD_POLICY_REQUIRED")
    if start_at.astimezone(zone).date() != end_at.astimezone(zone).date():
        conditions.append("WINDOW_CROSSES_MIDNIGHT")
    return WindowValidation(
        ReadinessState.PARTIAL
        if "WINDOW_BROAD_POLICY_REQUIRED" in conditions
        else ReadinessState.AVAILABLE,
        TimeWindow(start_at, end_at),
        tuple(conditions),
    )


def classify_duration(
    job: OperationalJobEvidence,
    appointment: OperationalAppointmentEvidence | None,
) -> DurationCandidate:
    scheduled = appointment.scheduled_duration_minutes if appointment else None
    elapsed: int | None = None
    active: int | None = None
    limitations: list[str] = []
    classification = DurationCandidateClass.SOURCE_REQUIRED
    if job.started_at is not None and job.completed_at is not None:
        if (
            job.started_at.tzinfo is None
            or job.completed_at.tzinfo is None
            or job.completed_at <= job.started_at
        ):
            classification = DurationCandidateClass.INVALID_DURATION
            limitations.append("Work start/completion chronology is invalid.")
        else:
            elapsed = int((job.completed_at - job.started_at).total_seconds() // 60)
            if job.pause_intervals:
                ordered_pauses = tuple(
                    sorted(job.pause_intervals, key=lambda item: item.start_at)
                )
                if any(
                    item.start_at < job.started_at
                    or item.end_at > job.completed_at
                    or (index > 0 and item.start_at < ordered_pauses[index - 1].end_at)
                    for index, item in enumerate(ordered_pauses)
                ):
                    classification = DurationCandidateClass.INVALID_DURATION
                    limitations.append(
                        "Pause evidence falls outside work or overlaps another pause."
                    )
                    ordered_pauses = ()
                pause_minutes = sum(
                    int((item.end_at - item.start_at).total_seconds() // 60)
                    for item in ordered_pauses
                )
                active = elapsed - pause_minutes
                if (
                    classification is not DurationCandidateClass.INVALID_DURATION
                    and active > 0
                ):
                    classification = DurationCandidateClass.QUALIFIED_MEASURED_DURATION
                elif classification is not DurationCandidateClass.INVALID_DURATION:
                    classification = DurationCandidateClass.INVALID_DURATION
            else:
                classification = DurationCandidateClass.PARTIAL_DURATION_EVIDENCE
                limitations.append(
                    "Pause/resume evidence is absent; elapsed work is not active duration."
                )
    elif any(value is not None for value in (job.started_at, job.completed_at)):
        classification = DurationCandidateClass.PARTIAL_DURATION_EVIDENCE
        limitations.append("Both work-start and completion evidence are required.")
    elif scheduled is not None and scheduled > 0:
        classification = DurationCandidateClass.SCHEDULED_DURATION_ONLY
        limitations.append("Scheduled duration is not measured work duration.")
    payload = {
        "contract": CONTRACT_VERSION,
        "source_job_id": job.source_id,
        "source_digest": job.source_digest,
        "appointment_digest": appointment.source_digest if appointment else None,
        "classification": classification.value,
        "scheduled": scheduled,
        "elapsed": elapsed,
        "active": active,
    }
    return DurationCandidate(
        job.source_id,
        classification,
        scheduled,
        elapsed,
        active,
        tuple(limitations),
        _digest(payload),
    )


def measured_duration_evidence(
    job: OperationalJobEvidence, candidate: DurationCandidate
) -> MeasuredDuration:
    if (
        candidate.classification
        is not DurationCandidateClass.QUALIFIED_MEASURED_DURATION
        or candidate.active_minutes is None
        or job.started_at is None
        or job.completed_at is None
    ):
        raise ValueError("only qualified active duration may become measured evidence")
    return MeasuredDuration(
        job_id=UUID(job.source_id)
        if _is_uuid(job.source_id)
        else UUID(int=int(candidate.evidence_digest[:32], 16)),
        company_id=job.company_id,
        branch_id=job.branch_id,
        service_category=job.service_category,
        started_at=job.started_at,
        completed_at=job.completed_at,
        active_minutes=candidate.active_minutes,
        evidence=(
            EvidenceRef(CONTRACT_VERSION, job.source_id, candidate.evidence_digest),
        ),
    )


def technician_mapping(
    source_ids: tuple[str, ...], crosswalks: tuple[TechnicianCrosswalk, ...]
) -> TechnicianMapping:
    lookup = {item.source_technician_id: item for item in crosswalks}
    if not source_ids:
        return TechnicianMapping(
            TechnicianMappingState.NONE_REPORTED,
            (),
            (),
            ("No source technician was reported.",),
        )
    mapped = tuple(
        lookup[item]
        for item in source_ids
        if item in lookup and lookup[item].employee_id is not None
    )
    unresolved = tuple(
        sorted(set(source_ids) - {item.source_technician_id for item in mapped})
    )
    employee_ids = tuple(
        sorted(
            {item.employee_id for item in mapped if item.employee_id is not None},
            key=str,
        )
    )
    if unresolved:
        state = TechnicianMappingState.UNMAPPED
    elif len(source_ids) > 1:
        state = TechnicianMappingState.MULTIPLE
    elif mapped and mapped[0].employee_active is False:
        state = TechnicianMappingState.MAPPED_HISTORICAL_INACTIVE
    else:
        state = TechnicianMappingState.MAPPED_ACTIVE
    limitations = (
        ()
        if not unresolved
        else ("One or more source technician identities are unmapped.",)
    )
    return TechnicianMapping(state, employee_ids, unresolved, limitations)


def reconcile_date(
    appointments: tuple[OperationalAppointmentEvidence, ...],
    *,
    local_date: date,
    timezone_name: str,
    crosswalks: tuple[TechnicianCrosswalk, ...] = (),
) -> DateAcceptanceReport:
    if len(appointments) > MAX_BATCH_SIZE:
        raise ValueError("operational acceptance batch exceeds its bound")
    zone = ZoneInfo(timezone_name)
    results: list[AppointmentAcceptance] = []
    for item in sorted(
        appointments, key=lambda value: (value.source_id, value.source_digest)
    ):
        mapping = technician_mapping(item.source_technician_ids, crosswalks)
        window = validate_window(
            item.window_start_at, item.window_end_at, accepted_timezone=timezone_name
        )
        conditions = list(window.conditions)
        if (
            item.migration_held
            or not item.parent_admitted
            or item.customer_id is None
            or item.service_location_id is None
        ):
            disposition = DateDisposition.HELD
            conditions.append("PARENT_AUTHORITY_INCOMPLETE")
        elif window.window is None:
            disposition = DateDisposition.INCOMPLETE_WINDOW
        elif window.window.start_at.astimezone(zone).date() != local_date:
            disposition = DateDisposition.OTHER_EXPLICIT_DISPOSITION
            conditions.append("OUTSIDE_ACCEPTANCE_DATE")
        elif item.status == "cancelled":
            disposition = DateDisposition.CANCELED_HISTORICAL
        elif mapping.state is TechnicianMappingState.UNMAPPED:
            disposition = DateDisposition.UNMAPPED_TECHNICIAN
        else:
            disposition = DateDisposition.ADMITTED
        results.append(
            AppointmentAcceptance(
                item.source_id,
                item.source_digest,
                disposition,
                tuple(sorted(set(conditions))),
                mapping.state,
            )
        )
    counts = dict(sorted(Counter(item.disposition.value for item in results).items()))
    payload = {
        "contract": ACCEPTANCE_VERSION,
        "date": local_date.isoformat(),
        "timezone": timezone_name,
        "dispositions": [asdict(item) for item in results],
    }
    return DateAcceptanceReport(
        ACCEPTANCE_VERSION,
        local_date,
        timezone_name,
        len(appointments),
        tuple(results),
        counts,
        len(appointments) - sum(counts.values()),
        _digest(payload),
    )


def dispatch_readiness(
    appointment: OperationalAppointmentEvidence,
    *,
    crosswalks: tuple[TechnicianCrosswalk, ...] = (),
) -> DispatchReadiness:
    admitted = ["company", "branch", "job", "customer", "service_location"]
    unknown: list[str] = []
    limitations: list[str] = []
    window = validate_window(
        appointment.window_start_at,
        appointment.window_end_at,
        accepted_timezone="America/New_York",
    )
    if window.window is None:
        unknown.append("customer_window")
    else:
        admitted.append("customer_window")
    mapping = technician_mapping(appointment.source_technician_ids, crosswalks)
    if mapping.state in {
        TechnicianMappingState.MAPPED_ACTIVE,
        TechnicianMappingState.MAPPED_HISTORICAL_INACTIVE,
        TechnicianMappingState.MULTIPLE,
    }:
        admitted.append("historical_technician_identity")
    else:
        unknown.append("technician_mapping")
    if appointment.scheduled_duration_minutes:
        admitted.append("scheduled_duration")
    else:
        unknown.append("duration")
    unknown.extend(("travel", "fleet", "capability", "certification"))
    limitations.append(
        "Unknown optional evidence remains explicit and does not erase valid schedule evidence."
    )
    state = EvidenceState.KNOWN if not unknown else EvidenceState.UNKNOWN
    return DispatchReadiness(state, tuple(admitted), tuple(unknown), tuple(limitations))


def economics_operational_readiness(
    job: OperationalJobEvidence,
    duration: DurationCandidate,
) -> EconomicsOperationalReadiness:
    """Admit operational dimensions without manufacturing monetary truth."""
    admissible = ["company", "branch", "customer", "service_location", "job"]
    missing: list[str] = []
    if job.completed_at is not None:
        admissible.append("work_period")
    else:
        missing.append("work_period")
    if job.service_category:
        admissible.append("service_category")
    else:
        missing.append("service_category")
    if duration.classification is DurationCandidateClass.QUALIFIED_MEASURED_DURATION:
        admissible.append("measured_active_duration")
    else:
        missing.append("measured_active_duration")
    prohibited = ("revenue", "cash", "labor_cost", "material_cost", "profitability")
    state = ReadinessState.AVAILABLE if not missing else ReadinessState.PARTIAL
    payload = {
        "contract": CONTRACT_VERSION,
        "source_id": job.source_id,
        "source_digest": job.source_digest,
        "duration_digest": duration.evidence_digest,
        "admissible": admissible,
        "missing": missing,
        "prohibited": prohibited,
    }
    return EconomicsOperationalReadiness(
        state,
        tuple(admissible),
        tuple(missing),
        prohibited,
        _digest(payload),
    )


def data_quality_conditions(
    jobs: tuple[OperationalJobEvidence, ...],
    appointments: tuple[OperationalAppointmentEvidence, ...],
    *,
    accepted_timezone: str,
    crosswalks: tuple[TechnicianCrosswalk, ...] = (),
) -> tuple[DataQualityCondition, ...]:
    """Return source-bound conditions; never repair or disposition source rows."""
    if len(jobs) + len(appointments) > MAX_BATCH_SIZE:
        raise ValueError("operational quality batch exceeds its bound")
    results: list[DataQualityCondition] = []
    jobs_by_source_id = {item.source_id: item for item in jobs}
    seen: dict[tuple[str, str], str] = {}

    def add(
        source_type: str, source_id: str, code: str, state: ReadinessState, digest: str
    ) -> None:
        results.append(
            DataQualityCondition(source_type, source_id, code, state, digest)
        )

    for source_type, records in (("JOB", jobs), ("APPOINTMENT", appointments)):
        for item in records:
            key = (source_type, item.source_id)
            prior = seen.get(key)
            if prior is not None and prior != item.source_digest:
                add(
                    source_type,
                    item.source_id,
                    "DUPLICATE_SOURCE_IDENTITY",
                    ReadinessState.CONFLICTING,
                    item.source_digest,
                )
            seen[key] = item.source_digest

    for item in jobs:
        if not item.service_category:
            add(
                "JOB",
                item.source_id,
                "UNKNOWN_CATEGORY",
                ReadinessState.SOURCE_REQUIRED,
                item.source_digest,
            )
        duration = classify_duration(item, None)
        if (
            duration.classification
            is not DurationCandidateClass.QUALIFIED_MEASURED_DURATION
        ):
            add(
                "JOB",
                item.source_id,
                "MISSING_DURATION_EVIDENCE",
                ReadinessState.PARTIAL,
                item.source_digest,
            )

    for item in appointments:
        if not item.parent_admitted:
            add(
                "APPOINTMENT",
                item.source_id,
                "MISSING_JOB",
                ReadinessState.SOURCE_REQUIRED,
                item.source_digest,
            )
        parent = jobs_by_source_id.get(item.source_job_id)
        if (
            parent is not None
            and item.status == "completed"
            and parent.status == "cancelled"
        ):
            add(
                "APPOINTMENT",
                item.source_id,
                "CONFLICTING_LIFECYCLE",
                ReadinessState.CONFLICTING,
                item.source_digest,
            )
        if item.customer_id is None:
            add(
                "APPOINTMENT",
                item.source_id,
                "MISSING_CUSTOMER",
                ReadinessState.SOURCE_REQUIRED,
                item.source_digest,
            )
        if item.service_location_id is None:
            add(
                "APPOINTMENT",
                item.source_id,
                "MISSING_LOCATION",
                ReadinessState.SOURCE_REQUIRED,
                item.source_digest,
            )
        window = validate_window(
            item.window_start_at,
            item.window_end_at,
            accepted_timezone=accepted_timezone,
        )
        for code in window.conditions:
            add("APPOINTMENT", item.source_id, code, window.state, item.source_digest)
        mapping = technician_mapping(item.source_technician_ids, crosswalks)
        if mapping.state in {
            TechnicianMappingState.UNMAPPED,
            TechnicianMappingState.NONE_REPORTED,
        }:
            add(
                "APPOINTMENT",
                item.source_id,
                "UNMAPPED_TECHNICIAN",
                ReadinessState.PARTIAL,
                item.source_digest,
            )
    return tuple(
        sorted(
            results,
            key=lambda item: (
                item.source_type,
                item.source_id,
                item.code,
                item.evidence_digest,
            ),
        )
    )


def luminary_readiness_explanations(
    *,
    scheduled: bool,
    technician_mapped: bool,
    duration: DurationCandidateClass,
    category_available: bool,
    economics_complete: bool,
) -> tuple[str, ...]:
    values = []
    if scheduled:
        values.append("Historical schedule evidence is available.")
    if not technician_mapped:
        values.append("Technician mapping is incomplete.")
    if duration is not DurationCandidateClass.QUALIFIED_MEASURED_DURATION:
        values.append("Duration evidence is partial or unavailable.")
    if not category_available:
        values.append("Service category evidence is unavailable.")
    if not economics_complete:
        values.append(
            "Operational history may be admitted while Economics remains incomplete; no revenue or cost is inferred."
        )
    return tuple(values)


def _required_digest(value: object) -> str:
    text = str(value or "")
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise ValueError(
            "Migration source evidence requires a lowercase SHA-256 digest"
        )
    return text


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True
