"""Plan-conformance and evidence-preserving child repair for HCP.MIGRATION.2."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.operational_migration.financial import (
    EstimateMigrationRecord,
    InvoiceMigrationRecord,
    PaymentMigrationRecord,
)
from app.operational_migration.hcp_migration2b import canonical_sha256
from app.operational_migration.models import (
    HcpMigrationChildAdmission,
    HcpMigrationChildRepair,
    HcpMigrationMasterRun,
    OperationalMigrationRun,
)
from app.operational_migration.service import (
    AppointmentMigrationRecord,
    JobMigrationRecord,
)
from app.platform.permissions.authorization import AuthorizationContext

REPAIR_VERSION = "hcp-migration-2i-child-repair/v1"
REPAIR_NAMESPACE = UUID("e25de6e5-c944-5a22-9dc7-dd8cf8fb65cf")
ADMISSION_NAMESPACE = UUID("92f54c73-28f0-5ae7-a08b-14a4f9b91329")


def canonical_nonzero_counts(counts: Mapping[str, int]) -> dict[str, int]:
    """Canonicalize unused zero buckets without hiding non-zero evidence."""
    if any(not isinstance(value, int) or value < 0 for value in counts.values()):
        raise ValueError("outcome counts must be non-negative integers")
    return dict(sorted((key, value) for key, value in counts.items() if value != 0))


def require_equivalent_hold_counts(
    actual: Mapping[str, int], expected: Mapping[str, int]
) -> str:
    actual_canonical = canonical_nonzero_counts(actual)
    expected_canonical = canonical_nonzero_counts(expected)
    if actual_canonical != expected_canonical:
        raise ValueError("HOLD entity accounting is incomplete")
    return canonical_sha256(actual_canonical)


@dataclass(frozen=True)
class ChildOutcomeCounts:
    source: int
    accepted: int
    rejected: int
    duplicate: int
    unresolved: int

    def validate(self) -> None:
        values = asdict(self)
        if any(value < 0 for value in values.values()):
            raise ValueError("child outcome count is negative")
        if self.source != sum(
            (self.accepted, self.rejected, self.duplicate, self.unresolved)
        ):
            raise ValueError("child outcome accounting mismatch")


@dataclass(frozen=True)
class OperationalEligibility:
    jobs: tuple[JobMigrationRecord, ...]
    appointments: tuple[AppointmentMigrationRecord, ...]
    job_exceptions: dict[str, int]
    appointment_exceptions: dict[str, int]
    job_outcomes: tuple[tuple[str, str], ...]
    appointment_outcomes: tuple[tuple[str, str], ...]
    digest: str


def requalify_operational_commands(
    *,
    jobs: Sequence[JobMigrationRecord],
    appointments: Sequence[AppointmentMigrationRecord],
    created_at_by_job: Mapping[str, datetime | None],
    persisted_customer_ids: frozenset[str],
    persisted_location_ids: frozenset[str],
) -> OperationalEligibility:
    """Requalify using durable native parents and native Job lifecycle invariants."""
    admitted: list[JobMigrationRecord] = []
    exceptions: dict[str, int] = {}
    job_outcomes: list[tuple[str, str]] = []

    def reject(identity: str, code: str) -> None:
        exceptions[code] = exceptions.get(code, 0) + 1
        job_outcomes.append((identity, code))

    seen_source: set[str] = set()
    seen_job_fingerprints: set[tuple[object, ...]] = set()
    for job in sorted(jobs, key=lambda item: item.source_id):
        job_fingerprint = (
            job.source_customer_id,
            job.source_service_location_id,
            job.source_job_number,
            job.summary,
            job.scheduled_start_at,
        )
        if job.source_id in seen_source or job_fingerprint in seen_job_fingerprints:
            reject(job.source_id, "duplicate_native_job_identity")
            continue
        seen_source.add(job.source_id)
        seen_job_fingerprints.add(job_fingerprint)
        if job.source_customer_id not in persisted_customer_ids:
            reject(job.source_id, "authoritative_customer_parent_unavailable")
            continue
        if job.source_service_location_id not in persisted_location_ids:
            reject(job.source_id, "authoritative_location_parent_unavailable")
            continue
        if job.status == "cancelled":
            reject(job.source_id, "cancelled_history_requires_non_operational_outcome")
            continue
        created_at = created_at_by_job.get(job.source_id)
        if created_at is None:
            reject(job.source_id, "source_activation_timestamp_unavailable")
            continue
        if job.status in {"in_progress", "completed"} and job.started_at is None:
            reject(job.source_id, "source_started_timestamp_unavailable")
            continue
        if job.status == "completed" and job.completed_at is None:
            reject(job.source_id, "source_completion_timestamp_unavailable")
            continue
        if (
            job.started_at is not None
            and job.completed_at is not None
            and job.completed_at < job.started_at
        ):
            reject(job.source_id, "source_lifecycle_timestamp_conflict")
            continue
        # A source started event proves activation no later than that event. This
        # preserves both timestamps and avoids inventing a new lifecycle fact.
        activated_at = min(
            value for value in (created_at, job.started_at) if value is not None
        )
        admitted.append(
            replace(
                job,
                activated_at=activated_at,
                external_metadata={
                    **(job.external_metadata or {}),
                    "activation_mapping": "earliest_source_created_or_started",
                    "repair_contract": REPAIR_VERSION,
                },
            )
        )

    admitted_ids = frozenset(item.source_id for item in admitted)
    admitted_appointments: list[AppointmentMigrationRecord] = []
    appointment_exceptions: dict[str, int] = {}
    appointment_outcomes: list[tuple[str, str]] = []
    seen_appointments: set[str] = set()
    seen_appointment_fingerprints: set[tuple[object, ...]] = set()
    for appointment in sorted(appointments, key=lambda item: item.source_id):
        code: str | None = None
        appointment_fingerprint = (
            appointment.source_job_id,
            appointment.arrival_window_start_at,
            appointment.arrival_window_end_at,
        )
        if (
            appointment.source_id in seen_appointments
            or appointment_fingerprint in seen_appointment_fingerprints
        ):
            code = "duplicate_native_appointment_identity"
        elif appointment.source_job_id not in admitted_ids:
            code = "authoritative_job_parent_not_admitted"
        elif appointment.source_customer_id not in persisted_customer_ids:
            code = "authoritative_customer_parent_unavailable"
        elif appointment.source_service_location_id not in persisted_location_ids:
            code = "authoritative_location_parent_unavailable"
        seen_appointments.add(appointment.source_id)
        seen_appointment_fingerprints.add(appointment_fingerprint)
        if code is None:
            admitted_appointments.append(appointment)
        else:
            appointment_exceptions[code] = appointment_exceptions.get(code, 0) + 1
            appointment_outcomes.append((appointment.source_id, code))
    payload = {
        "version": REPAIR_VERSION,
        "jobs": [asdict(item) for item in admitted],
        "appointments": [asdict(item) for item in admitted_appointments],
        "job_exceptions": exceptions,
        "appointment_exceptions": appointment_exceptions,
        "job_outcomes": job_outcomes,
        "appointment_outcomes": appointment_outcomes,
    }
    return OperationalEligibility(
        tuple(admitted),
        tuple(admitted_appointments),
        dict(sorted(exceptions.items())),
        dict(sorted(appointment_exceptions.items())),
        tuple(sorted(job_outcomes)),
        tuple(sorted(appointment_outcomes)),
        canonical_sha256(payload),
    )


@dataclass(frozen=True)
class FinancialEligibility:
    estimates: tuple[EstimateMigrationRecord, ...]
    invoices: tuple[InvoiceMigrationRecord, ...]
    payments: tuple[PaymentMigrationRecord, ...]
    estimate_exceptions: int
    invoice_exceptions: int
    payment_exceptions: int
    estimate_outcomes: tuple[str, ...]
    invoice_outcomes: tuple[str, ...]
    payment_outcomes: tuple[str, ...]
    digest: str


@dataclass(frozen=True)
class ChildRepairPlan:
    original_plan_id: UUID
    original_plan_digest: str
    operational: OperationalEligibility
    financial: FinancialEligibility
    persisted_counts: dict[str, int]
    exception_counts: dict[str, int]
    repair_plan_digest: str

    @classmethod
    def build(
        cls,
        *,
        original_plan_id: UUID,
        original_plan_digest: str,
        operational: OperationalEligibility,
        financial: FinancialEligibility,
        original_persisted_counts: Mapping[str, int] | None = None,
        original_exception_counts: Mapping[str, int] | None = None,
    ) -> ChildRepairPlan:
        persisted = dict(original_persisted_counts or {})
        persisted.update(
            {
                "job": len(operational.jobs),
                "appointment": len(operational.appointments),
                "estimate": len(financial.estimates),
                "invoice": len(financial.invoices),
                "payment": len(financial.payments),
            }
        )
        exceptions = dict(original_exception_counts or {})
        exceptions.update(
            {
                "job": exceptions.get("job", 0) + len(operational.job_outcomes),
                "appointment": exceptions.get("appointment", 0)
                + len(operational.appointment_outcomes),
                "estimate": exceptions.get("estimate", 0)
                + len(financial.estimate_outcomes),
                "invoice": exceptions.get("invoice", 0)
                + len(financial.invoice_outcomes),
                "payment": exceptions.get("payment", 0)
                + len(financial.payment_outcomes),
            }
        )
        digest = canonical_sha256(
            {
                "version": REPAIR_VERSION,
                "original_plan_id": str(original_plan_id),
                "original_plan_digest": original_plan_digest,
                "operational_digest": operational.digest,
                "financial_digest": financial.digest,
                "persisted_counts": persisted,
                "exception_counts": exceptions,
            }
        )
        return cls(
            original_plan_id,
            original_plan_digest,
            operational,
            financial,
            dict(sorted(persisted.items())),
            dict(sorted(exceptions.items())),
            digest,
        )


def requalify_financial_commands(
    *,
    estimates: Sequence[EstimateMigrationRecord] = (),
    invoices: Sequence[InvoiceMigrationRecord],
    payments: Sequence[PaymentMigrationRecord],
    admitted_job_ids: frozenset[str],
) -> FinancialEligibility:
    admitted_estimates = tuple(
        sorted(
            (item for item in estimates if item.source_job_id in admitted_job_ids),
            key=lambda item: item.source_id,
        )
    )
    admitted_invoices = tuple(
        sorted(
            (item for item in invoices if item.source_job_id in admitted_job_ids),
            key=lambda item: item.source_id,
        )
    )
    invoice_ids = frozenset(item.source_id for item in admitted_invoices)
    admitted_payments = tuple(
        sorted(
            (item for item in payments if item.source_invoice_id in invoice_ids),
            key=lambda item: item.source_id,
        )
    )
    payload = {
        "version": REPAIR_VERSION,
        "estimate_ids": [item.source_id for item in admitted_estimates],
        "invoice_ids": [item.source_id for item in admitted_invoices],
        "payment_ids": [item.source_id for item in admitted_payments],
        "financial_truth": False,
    }
    return FinancialEligibility(
        admitted_estimates,
        admitted_invoices,
        admitted_payments,
        len(estimates) - len(admitted_estimates),
        len(invoices) - len(admitted_invoices),
        len(payments) - len(admitted_payments),
        tuple(
            sorted(
                item.source_id
                for item in estimates
                if item.source_job_id not in admitted_job_ids
            )
        ),
        tuple(
            sorted(
                item.source_id
                for item in invoices
                if item.source_job_id not in admitted_job_ids
            )
        ),
        tuple(
            sorted(
                item.source_id
                for item in payments
                if item.source_invoice_id not in invoice_ids
            )
        ),
        canonical_sha256(payload),
    )


def _counts_payload(counts: ChildOutcomeCounts) -> dict[str, int]:
    counts.validate()
    return asdict(counts)


async def record_child_admission(
    session: AsyncSession,
    *,
    context: AuthorizationContext,
    master_run_id: UUID,
    child_run_id: UUID,
    domain: str,
    execution_status: str,
    plan_digest: str,
    expected: ChildOutcomeCounts,
    actual: ChildOutcomeCounts,
    reason_code: str,
) -> HcpMigrationChildAdmission:
    expected_payload = _counts_payload(expected)
    actual_payload = _counts_payload(actual)
    conformance = (
        "PLAN_CONFORMING"
        if execution_status in {"completed", "completed_with_exceptions"}
        and expected_payload == actual_payload
        else "PLAN_NONCONFORMING"
    )
    payload = {
        "master": str(master_run_id),
        "child": str(child_run_id),
        "domain": domain,
        "execution_status": execution_status,
        "conformance": conformance,
        "plan_digest": plan_digest,
        "expected": expected_payload,
        "actual": actual_payload,
        "reason": reason_code,
    }
    digest = canonical_sha256(payload)
    existing = await session.scalar(
        select(HcpMigrationChildAdmission).where(
            HcpMigrationChildAdmission.master_run_id == master_run_id,
            HcpMigrationChildAdmission.domain == domain,
            HcpMigrationChildAdmission.child_run_id == child_run_id,
        )
    )
    if existing is not None:
        if existing.admission_digest != digest:
            raise ValueError("contradictory child admission evidence")
        return existing
    assert context.active_branch is not None
    row = HcpMigrationChildAdmission(
        id=uuid5(ADMISSION_NAMESPACE, digest),
        company_id=context.company.id,
        branch_id=context.active_branch.id,
        master_run_id=master_run_id,
        child_run_id=child_run_id,
        domain=domain,
        execution_status=execution_status,
        conformance=conformance,
        plan_digest=plan_digest,
        expected_counts=expected_payload,
        actual_counts=actual_payload,
        reason_code=reason_code,
        admission_digest=digest,
    )
    session.add(row)
    await session.flush()
    return row


async def qualify_child_repair(
    session: AsyncSession,
    *,
    context: AuthorizationContext,
    master_run_id: UUID,
    original_child_run_id: UUID,
    domain: str,
    original_plan_digest: str,
    repair_plan_digest: str,
    immutable_input_digest: str,
    reason_code: str,
) -> HcpMigrationChildRepair:
    master = await session.get(HcpMigrationMasterRun, master_run_id)
    original = await session.get(OperationalMigrationRun, original_child_run_id)
    if (
        master is None
        or original is None
        or original.master_run_id != master_run_id
        or original.master_domain != domain
        or original.company_id != context.company.id
        or context.active_branch is None
        or original.branch_id != context.active_branch.id
    ):
        raise ValueError("child repair scope is invalid")
    payload = {
        "version": REPAIR_VERSION,
        "master": str(master_run_id),
        "original_child": str(original_child_run_id),
        "domain": domain,
        "original_plan": original_plan_digest,
        "repair_plan": repair_plan_digest,
        "immutable_input": immutable_input_digest,
        "reason": reason_code,
    }
    digest = canonical_sha256(payload)
    existing = await session.scalar(
        select(HcpMigrationChildRepair).where(
            HcpMigrationChildRepair.master_run_id == master_run_id,
            HcpMigrationChildRepair.domain == domain,
            HcpMigrationChildRepair.repair_digest == digest,
        )
    )
    if existing is not None:
        return existing
    contradictory = await session.scalar(
        select(HcpMigrationChildRepair).where(
            HcpMigrationChildRepair.master_run_id == master_run_id,
            HcpMigrationChildRepair.domain == domain,
            HcpMigrationChildRepair.original_child_run_id == original_child_run_id,
        )
    )
    if contradictory is not None:
        raise ValueError("contradictory child repair qualification")
    row = HcpMigrationChildRepair(
        id=uuid5(REPAIR_NAMESPACE, digest),
        company_id=context.company.id,
        branch_id=context.active_branch.id,
        master_run_id=master_run_id,
        original_child_run_id=original_child_run_id,
        domain=domain,
        reason_code=reason_code,
        original_plan_digest=original_plan_digest,
        repair_plan_digest=repair_plan_digest,
        immutable_input_digest=immutable_input_digest,
        repair_digest=digest,
        status="qualified",
    )
    session.add(row)
    await session.flush()
    return row
