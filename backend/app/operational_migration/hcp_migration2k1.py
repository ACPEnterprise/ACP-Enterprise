"""Evidence-preserving deterministic Appointment sequence correction."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.models import JobAppointmentLink
from app.operational_migration.hcp_migration2b import canonical_sha256
from app.operational_migration.models import HcpAppointmentSequenceCorrection
from app.operational_migration.service import AppointmentMigrationRecord

SEQUENCING_CONTRACT_VERSION = "hcp-migration-2k1-appointment-sequence/v1"
SEQUENCE_PLAN_NAMESPACE = UUID("20a56724-ed88-51ca-af3d-e6e9f43848c5")
CORRECTION_NAMESPACE = UUID("5cc0fce4-c3c5-57e0-9723-5a031ce73962")


class AppointmentSequenceError(ValueError):
    """Safe sequencing failure whose text never contains protected evidence."""


@dataclass(frozen=True)
class AppointmentSequencePlan:
    appointments: tuple[AppointmentMigrationRecord, ...]
    job_count: int
    single_visit_job_count: int
    multi_visit_job_count: int
    multi_visit_appointment_count: int
    visits_beyond_first: int
    maximum_visits: int
    digest: str

    def sequence_by_source_id(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for item in self.appointments:
            value = (item.external_metadata or {}).get("visit_sequence")
            if not isinstance(value, int):
                raise AppointmentSequenceError("sequence_plan_projection_invalid")
            result[item.source_id] = value
        return result


def build_appointment_sequence_plan(
    appointments: Sequence[AppointmentMigrationRecord],
) -> AppointmentSequencePlan:
    """Assign canonical per-Job sequences without relying on input/target order."""
    source_ids = [item.source_id for item in appointments]
    if len(source_ids) != len(set(source_ids)):
        raise AppointmentSequenceError("duplicate_appointment_source_identity")
    grouped: dict[str, list[AppointmentMigrationRecord]] = defaultdict(list)
    for item in appointments:
        if item.arrival_window_start_at is None or item.arrival_window_end_at is None:
            raise AppointmentSequenceError("appointment_sequence_evidence_incomplete")
        grouped[item.source_job_id].append(item)
    sequenced: list[AppointmentMigrationRecord] = []
    counts: list[int] = []
    for job_id in sorted(grouped):
        ordered = sorted(
            grouped[job_id],
            key=lambda item: (
                item.arrival_window_start_at,
                item.arrival_window_end_at,
                item.source_id,
            ),
        )
        counts.append(len(ordered))
        sequenced.extend(
            replace(
                item,
                external_metadata={
                    **(item.external_metadata or {}),
                    "visit_sequence": index,
                    "visit_sequence_contract": SEQUENCING_CONTRACT_VERSION,
                },
            )
            for index, item in enumerate(ordered, start=1)
        )
    canonical = tuple(sorted(sequenced, key=lambda item: item.source_id))
    payload = {
        "version": SEQUENCING_CONTRACT_VERSION,
        "appointments": [
            {
                "source_id_digest": canonical_sha256(item.source_id),
                "job_id_digest": canonical_sha256(item.source_job_id),
                "start": item.arrival_window_start_at,
                "end": item.arrival_window_end_at,
                "visit_sequence": (item.external_metadata or {})["visit_sequence"],
            }
            for item in canonical
        ],
    }
    multi = [count for count in counts if count > 1]
    return AppointmentSequencePlan(
        appointments=canonical,
        job_count=len(counts),
        single_visit_job_count=sum(count == 1 for count in counts),
        multi_visit_job_count=len(multi),
        multi_visit_appointment_count=sum(multi),
        visits_beyond_first=sum(count - 1 for count in multi),
        maximum_visits=max(counts, default=0),
        digest=canonical_sha256(payload),
    )


@dataclass(frozen=True)
class RetainedAppointmentProjection:
    link_id: UUID
    job_id: UUID
    appointment_id: UUID
    source_id: str
    current_sequence: int


@dataclass(frozen=True)
class AppointmentCorrection:
    retained: RetainedAppointmentProjection
    corrected_sequence: int
    digest: str


@dataclass(frozen=True)
class AppointmentCorrectionCheckpoint:
    accepted_job_count: int
    retained_count: int
    reused_count: int
    correction_count: int
    remaining_count: int
    corrections: tuple[AppointmentCorrection, ...]
    digest: str


def qualify_retained_checkpoint(
    *,
    plan: AppointmentSequencePlan,
    retained: Sequence[RetainedAppointmentProjection],
    accepted_job_count: int,
) -> AppointmentCorrectionCheckpoint:
    expected = plan.sequence_by_source_id()
    seen: set[str] = set()
    corrections: list[AppointmentCorrection] = []
    for item in sorted(retained, key=lambda value: value.source_id):
        if item.source_id in seen:
            raise AppointmentSequenceError("duplicate_retained_appointment_identity")
        seen.add(item.source_id)
        corrected = expected.get(item.source_id)
        if corrected is None:
            raise AppointmentSequenceError("retained_appointment_not_in_plan")
        if item.current_sequence != corrected:
            digest = canonical_sha256(
                {
                    "version": SEQUENCING_CONTRACT_VERSION,
                    "link_id": str(item.link_id),
                    "job_id": str(item.job_id),
                    "appointment_id": str(item.appointment_id),
                    "source_identity_digest": canonical_sha256(item.source_id),
                    "prior": item.current_sequence,
                    "corrected": corrected,
                }
            )
            corrections.append(AppointmentCorrection(item, corrected, digest))
    payload = {
        "version": SEQUENCING_CONTRACT_VERSION,
        "accepted_job_count": accepted_job_count,
        "plan_digest": plan.digest,
        "retained": sorted(canonical_sha256(item.source_id) for item in retained),
        "corrections": [item.digest for item in corrections],
    }
    return AppointmentCorrectionCheckpoint(
        accepted_job_count=accepted_job_count,
        retained_count=len(retained),
        reused_count=len(retained) - len(corrections),
        correction_count=len(corrections),
        remaining_count=len(plan.appointments) - len(retained),
        corrections=tuple(corrections),
        digest=canonical_sha256(payload),
    )


@dataclass(frozen=True)
class SupersedingAppointmentRepairPlan:
    id: UUID
    generation: int
    original_repair_plan_digest: str
    sequencing_contract_version: str
    sequencing_digest: str
    checkpoint_digest: str
    digest: str

    @classmethod
    def build(
        cls,
        *,
        master_id: UUID,
        repair_id: UUID,
        original_repair_plan_digest: str,
        sequence_plan: AppointmentSequencePlan,
        checkpoint: AppointmentCorrectionCheckpoint,
        generation: int = 2,
    ) -> SupersedingAppointmentRepairPlan:
        payload = {
            "master_id": str(master_id),
            "repair_id": str(repair_id),
            "original_repair_plan_digest": original_repair_plan_digest,
            "generation": generation,
            "sequencing_contract_version": SEQUENCING_CONTRACT_VERSION,
            "sequencing_digest": sequence_plan.digest,
            "checkpoint_digest": checkpoint.digest,
            "appointment_commands": [
                (
                    canonical_sha256(item.source_id),
                    (item.external_metadata or {})["visit_sequence"],
                )
                for item in sequence_plan.appointments
            ],
        }
        digest = canonical_sha256(payload)
        return cls(
            id=uuid5(SEQUENCE_PLAN_NAMESPACE, digest),
            generation=generation,
            original_repair_plan_digest=original_repair_plan_digest,
            sequencing_contract_version=SEQUENCING_CONTRACT_VERSION,
            sequencing_digest=sequence_plan.digest,
            checkpoint_digest=checkpoint.digest,
            digest=digest,
        )


async def apply_job_sequence_corrections(
    session: AsyncSession,
    *,
    company_id: UUID,
    branch_id: UUID,
    sequence_plan_id: UUID,
    failed_child_run_id: UUID,
    corrections: Sequence[AppointmentCorrection],
) -> int:
    """Atomically reproject each Job while retaining append-only prior evidence."""
    by_job: dict[UUID, list[AppointmentCorrection]] = defaultdict(list)
    for correction in corrections:
        by_job[correction.retained.job_id].append(correction)
    applied = 0
    for job_id, job_corrections in sorted(
        by_job.items(), key=lambda item: str(item[0])
    ):
        new_evidence: list[HcpAppointmentSequenceCorrection] = []
        links = tuple(
            (
                await session.scalars(
                    select(JobAppointmentLink)
                    .where(
                        JobAppointmentLink.company_id == company_id,
                        JobAppointmentLink.branch_id == branch_id,
                        JobAppointmentLink.job_id == job_id,
                    )
                    .with_for_update()
                )
            ).all()
        )
        by_id = {item.id: item for item in links}
        target_sequences = {
            correction.retained.link_id: correction.corrected_sequence
            for correction in job_corrections
        }
        final = [target_sequences.get(item.id, item.visit_sequence) for item in links]
        if len(final) != len(set(final)):
            raise AppointmentSequenceError("corrected_job_sequence_conflict")
        offset = max(final, default=0) + len(links) + 1
        for correction in job_corrections:
            link = by_id.get(correction.retained.link_id)
            if (
                link is None
                or link.appointment_id != correction.retained.appointment_id
            ):
                raise AppointmentSequenceError("retained_appointment_link_conflict")
            existing = await session.scalar(
                select(HcpAppointmentSequenceCorrection).where(
                    HcpAppointmentSequenceCorrection.sequence_plan_id
                    == sequence_plan_id,
                    HcpAppointmentSequenceCorrection.appointment_link_id == link.id,
                )
            )
            if existing is not None:
                if existing.correction_digest != correction.digest:
                    raise AppointmentSequenceError(
                        "appointment_correction_replay_conflict"
                    )
                continue
            evidence = HcpAppointmentSequenceCorrection(
                id=uuid5(CORRECTION_NAMESPACE, correction.digest),
                company_id=company_id,
                branch_id=branch_id,
                sequence_plan_id=sequence_plan_id,
                appointment_link_id=link.id,
                job_id=job_id,
                appointment_id=link.appointment_id,
                failed_child_run_id=failed_child_run_id,
                prior_sequence=link.visit_sequence,
                corrected_sequence=correction.corrected_sequence,
                source_identity_digest=canonical_sha256(correction.retained.source_id),
                correction_digest=correction.digest,
                status="qualified",
            )
            session.add(evidence)
            new_evidence.append(evidence)
        # A high positive temporary band avoids transient unique-key collisions;
        # both flushes remain inside the caller-owned transaction.
        for link in links:
            if link.id in target_sequences:
                link.visit_sequence += offset
        await session.flush()
        for link in links:
            if link.id in target_sequences:
                link.visit_sequence = target_sequences[link.id]
        for evidence in new_evidence:
            evidence.status = "applied"
            evidence.applied_at = datetime.now(timezone.utc)
        await session.flush()
        applied += len(job_corrections)
    return applied


def sequence_distribution(plan: AppointmentSequencePlan) -> Mapping[int, int]:
    """Safe aggregate visit-count distribution for diagnostics."""
    per_job = Counter(item.source_job_id for item in plan.appointments)
    return dict(sorted(Counter(per_job.values()).items()))
