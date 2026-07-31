from dataclasses import asdict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.economics.contracts import (
    DefineAllocationPolicy,
    EvidenceInput,
    RecordBusinessFact,
)
from app.economics.domain import (
    Allocation,
    BusinessFact,
    EvidenceReference,
    ProfitMeasurement,
)
from app.economics.models import (
    AllocationPolicyRecord,
    AllocationRecord,
    AllocationRunRecord,
    BusinessFactRecord,
    EvidenceReferenceRecord,
    FactEvidenceRecord,
    ProfitMeasurementRecord,
)


class EconomicsLedgerError(ValueError):
    pass


def _required(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise EconomicsLedgerError(f"{label} is required")
    return normalized


def _evidence_snapshot(reference: EvidenceReference) -> dict[str, object]:
    return {
        "kind": reference.kind.value,
        "reference_id": reference.reference_id,
        "source_system": reference.source_system,
        "source_record_type": reference.source_record_type,
        "source_version": reference.source_version,
        "content_digest": reference.content_digest,
        "observed_at": reference.observed_at.isoformat(),
        "explanation": reference.explanation,
    }


class EconomicsLedgerService:
    """Stages immutable economics ledger records in the caller's transaction."""

    @staticmethod
    async def _record_evidence(
        session: AsyncSession, company_id: UUID, item: EvidenceInput
    ) -> EvidenceReferenceRecord:
        if len(item.content_digest) != 64:
            raise EconomicsLedgerError("evidence content digest must be SHA-256")
        existing = await session.scalar(
            select(EvidenceReferenceRecord).where(
                EvidenceReferenceRecord.company_id == company_id,
                EvidenceReferenceRecord.kind == item.kind.value,
                EvidenceReferenceRecord.source_system == item.source_system,
                EvidenceReferenceRecord.source_record_type == item.source_record_type,
                EvidenceReferenceRecord.reference_id == item.reference_id,
                EvidenceReferenceRecord.source_version == item.source_version,
            )
        )
        if existing is not None:
            if existing.content_digest != item.content_digest:
                raise EconomicsLedgerError(
                    "evidence source version does not match its recorded digest"
                )
            return existing
        record = EvidenceReferenceRecord(
            company_id=company_id,
            kind=item.kind.value,
            reference_id=_required(item.reference_id, "evidence reference"),
            source_system=_required(item.source_system, "evidence source system"),
            source_record_type=_required(
                item.source_record_type, "evidence source record type"
            ),
            source_version=_required(item.source_version, "evidence source version"),
            content_digest=item.content_digest,
            explanation=_required(item.explanation, "evidence explanation"),
            business_event_id=item.business_event_id,
            observed_at=item.observed_at,
        )
        session.add(record)
        await session.flush()
        return record

    @classmethod
    async def record_fact(
        cls, session: AsyncSession, company_id: UUID, command: RecordBusinessFact
    ) -> BusinessFactRecord:
        if (
            command.amount_minor is None
            and command.confidence.status.value != "unknown"
        ):
            raise EconomicsLedgerError("a known fact requires an amount")
        if command.amount_minor is not None and not command.evidence:
            raise EconomicsLedgerError("a known fact requires evidence")
        if command.period_end < command.period_start:
            raise EconomicsLedgerError("fact period is invalid")
        version = (
            int(
                await session.scalar(
                    select(
                        func.coalesce(func.max(BusinessFactRecord.version), 0)
                    ).where(
                        BusinessFactRecord.company_id == company_id,
                        BusinessFactRecord.subject_type == command.subject_type,
                        BusinessFactRecord.subject_id == command.subject_id,
                        BusinessFactRecord.fact_key == command.fact_key,
                        BusinessFactRecord.period_start == command.period_start,
                        BusinessFactRecord.period_end == command.period_end,
                    )
                )
                or 0
            )
            + 1
        )
        evidence = tuple(
            [
                await cls._record_evidence(session, company_id, item)
                for item in command.evidence
            ]
        )
        snapshot = [
            {
                **asdict(item),
                "kind": item.kind.value,
                "observed_at": item.observed_at.isoformat(),
                "business_event_id": (
                    str(item.business_event_id) if item.business_event_id else None
                ),
            }
            for item in command.evidence
        ]
        fact = BusinessFactRecord(
            company_id=company_id,
            branch_id=command.branch_id,
            subject_type=_required(command.subject_type, "subject type"),
            subject_id=command.subject_id,
            category=command.category.value,
            fact_key=_required(command.fact_key, "fact key"),
            amount_minor=command.amount_minor,
            currency=command.currency.upper(),
            confidence_status=command.confidence.status.value,
            confidence_percentage=command.confidence.percentage,
            confidence_explanation=command.confidence.explanation,
            evidence_snapshot=snapshot,
            occurred_at=command.occurred_at,
            period_start=command.period_start,
            period_end=command.period_end,
            measurement_method=_required(
                command.measurement_method, "measurement method"
            ),
            version=version,
        )
        session.add(fact)
        await session.flush()
        session.add_all(
            FactEvidenceRecord(
                company_id=company_id, fact_id=fact.id, evidence_id=item.id
            )
            for item in evidence
        )
        await session.flush()
        return fact

    @staticmethod
    async def define_allocation_policy(
        session: AsyncSession, company_id: UUID, command: DefineAllocationPolicy
    ) -> AllocationPolicyRecord:
        version = (
            int(
                await session.scalar(
                    select(
                        func.coalesce(func.max(AllocationPolicyRecord.version), 0)
                    ).where(
                        AllocationPolicyRecord.company_id == company_id,
                        AllocationPolicyRecord.policy_key == command.policy_key,
                    )
                )
                or 0
            )
            + 1
        )
        policy = AllocationPolicyRecord(
            company_id=company_id,
            policy_key=_required(command.policy_key, "policy key"),
            strategy=_required(command.strategy, "allocation strategy"),
            driver_fact_key=_required(command.driver_fact_key, "driver fact key"),
            rationale=_required(command.rationale, "policy rationale"),
            version=version,
        )
        session.add(policy)
        await session.flush()
        return policy

    @staticmethod
    async def record_allocation_run(
        session: AsyncSession,
        company_id: UUID,
        policy: AllocationPolicyRecord,
        source_fact: BusinessFact,
        allocations: tuple[Allocation, ...],
    ) -> AllocationRunRecord:
        if not allocations or any(
            item.source_fact_id != source_fact.id for item in allocations
        ):
            raise EconomicsLedgerError(
                "allocation run inputs do not share a source fact"
            )
        if source_fact.amount_minor is None:
            raise EconomicsLedgerError("unknown facts cannot be allocated")
        digest = allocations[0].input_digest
        if any(item.input_digest != digest for item in allocations):
            raise EconomicsLedgerError("allocation run inputs do not share a digest")
        existing = await session.scalar(
            select(AllocationRunRecord).where(
                AllocationRunRecord.company_id == company_id,
                AllocationRunRecord.input_digest == digest,
            )
        )
        if existing is not None:
            return existing
        allocated = sum(item.allocated_amount_minor for item in allocations)
        run = AllocationRunRecord(
            company_id=company_id,
            policy_id=policy.id,
            source_fact_id=source_fact.id,
            source_amount_minor=source_fact.amount_minor,
            allocated_amount_minor=allocated,
            residual_amount_minor=source_fact.amount_minor - allocated,
            input_digest=digest,
            confidence_status=source_fact.confidence.status.value,
            confidence_percentage=source_fact.confidence.percentage,
            confidence_explanation=source_fact.confidence.explanation,
            explanation=(
                f"Allocated source fact {source_fact.id} with policy {policy.id}; "
                f"residual {source_fact.amount_minor - allocated} minor units."
            ),
        )
        session.add(run)
        await session.flush()
        session.add_all(
            AllocationRecord(
                company_id=company_id,
                source_fact_id=item.source_fact_id,
                run_id=run.id,
                subject_type=item.subject_type,
                subject_id=item.subject_id,
                strategy=item.strategy,
                strategy_version=item.strategy_version,
                numerator=item.numerator,
                denominator=item.denominator,
                allocated_amount_minor=item.allocated_amount_minor,
                evidence_snapshot=[
                    _evidence_snapshot(reference) for reference in item.evidence
                ],
            )
            for item in allocations
        )
        await session.flush()
        return run

    @staticmethod
    async def record_profit_measurement(
        session: AsyncSession,
        company_id: UUID,
        branch_id: UUID | None,
        measurement: ProfitMeasurement,
    ) -> ProfitMeasurementRecord:
        version = (
            int(
                await session.scalar(
                    select(
                        func.coalesce(func.max(ProfitMeasurementRecord.version), 0)
                    ).where(
                        ProfitMeasurementRecord.company_id == company_id,
                        ProfitMeasurementRecord.subject_type
                        == measurement.subject_type,
                        ProfitMeasurementRecord.subject_id == measurement.subject_id,
                        ProfitMeasurementRecord.period_start
                        == measurement.period_start,
                        ProfitMeasurementRecord.period_end == measurement.period_end,
                    )
                )
                or 0
            )
            + 1
        )
        record = ProfitMeasurementRecord(
            company_id=company_id,
            branch_id=branch_id,
            subject_type=measurement.subject_type,
            subject_id=measurement.subject_id,
            period_start=measurement.period_start,
            period_end=measurement.period_end,
            currency=measurement.currency,
            revenue_minor=measurement.revenue.amount_minor,
            labor_minor=measurement.labor.amount_minor,
            materials_minor=measurement.materials.amount_minor,
            equipment_minor=measurement.equipment.amount_minor,
            truck_minor=measurement.truck.amount_minor,
            overhead_minor=measurement.overhead.amount_minor,
            gross_profit_minor=measurement.gross_profit.amount_minor,
            net_profit_minor=measurement.net_profit.amount_minor,
            confidence_status=measurement.confidence.status.value,
            confidence_percentage=measurement.confidence.percentage,
            confidence_explanation=measurement.confidence.explanation,
            evidence_snapshot=[
                _evidence_snapshot(item) for item in measurement.evidence
            ],
            input_fact_ids=[str(item) for item in measurement.input_fact_ids],
            input_allocation_ids=[
                str(item) for item in measurement.input_allocation_ids
            ],
            engine_version=measurement.engine_version,
            version=version,
        )
        session.add(record)
        await session.flush()
        return record


economics_ledger_service = EconomicsLedgerService()
