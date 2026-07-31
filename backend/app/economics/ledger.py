import hashlib
import json
import string
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
    AccountingPeriodRecord,
    AllocationPolicyRecord,
    AllocationRecord,
    AllocationRunRecord,
    BusinessFactRecord,
    EvidenceReferenceRecord,
    FactEvidenceRecord,
    ProfitMeasurementRecord,
    RecalculationScopeRecord,
)
from app.events.models import BusinessEvent


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


def _command_digest(command: RecordBusinessFact) -> str:
    content = {
        "branch_id": str(command.branch_id) if command.branch_id else None,
        "subject_type": command.subject_type,
        "subject_id": str(command.subject_id),
        "category": command.category.value,
        "fact_key": command.fact_key,
        "amount_minor": command.amount_minor,
        "currency": command.currency.upper(),
        "confidence_status": command.confidence.status.value,
        "confidence_percentage": command.confidence.percentage,
        "evidence": sorted(item.content_digest for item in command.evidence),
        "occurred_at": command.occurred_at.isoformat(),
        "period_start": command.period_start.isoformat(),
        "period_end": command.period_end.isoformat(),
        "measurement_method": command.measurement_method,
        "accounting_basis": command.accounting_basis,
        "correction_kind": command.correction_kind,
        "corrects_fact_id": (
            str(command.corrects_fact_id) if command.corrects_fact_id else None
        ),
        "effective_at": (
            command.effective_at.isoformat() if command.effective_at else None
        ),
    }
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _measurement_digest(company_id: UUID, measurement: ProfitMeasurement) -> str:
    canonical = json.dumps(
        {
            "company_id": str(company_id),
            "subject_type": measurement.subject_type,
            "subject_id": str(measurement.subject_id),
            "period_start": measurement.period_start.isoformat(),
            "period_end": measurement.period_end.isoformat(),
            "input_fact_ids": sorted(str(item) for item in measurement.input_fact_ids),
            "input_allocation_ids": sorted(
                str(item) for item in measurement.input_allocation_ids
            ),
            "engine_version": measurement.engine_version,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class EconomicsLedgerService:
    """Stages immutable economics ledger records in the caller's transaction."""

    @staticmethod
    async def _record_evidence(
        session: AsyncSession, company_id: UUID, item: EvidenceInput
    ) -> EvidenceReferenceRecord:
        if len(item.content_digest) != 64 or any(
            character not in string.hexdigits for character in item.content_digest
        ):
            raise EconomicsLedgerError("evidence content digest must be SHA-256")
        if item.business_event_id is not None:
            event_company_id = await session.scalar(
                select(BusinessEvent.company_id).where(
                    BusinessEvent.id == item.business_event_id
                )
            )
            if event_company_id != company_id:
                raise EconomicsLedgerError(
                    "Business Event evidence does not match the economics Company"
                )
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
        accounting_period = await session.scalar(
            select(AccountingPeriodRecord).where(
                AccountingPeriodRecord.company_id == company_id,
                AccountingPeriodRecord.period_start <= command.period_start,
                AccountingPeriodRecord.period_end >= command.period_end,
            )
        )
        if accounting_period is not None and accounting_period.status in {
            "closing",
            "closed",
        }:
            raise EconomicsLedgerError(
                "closed or closing accounting periods cannot accept evidence; "
                "use controlled reopening"
            )
        if (
            command.amount_minor is None
            and command.confidence.status.value != "unknown"
        ):
            raise EconomicsLedgerError("a known fact requires an amount")
        if command.amount_minor is not None and not command.evidence:
            raise EconomicsLedgerError("a known fact requires evidence")
        if command.period_end < command.period_start:
            raise EconomicsLedgerError("fact period is invalid")
        if command.accounting_basis not in {"accrual", "cash", "operational"}:
            raise EconomicsLedgerError("accounting basis is invalid")
        if len(command.currency) != 3 or not command.currency.isalpha():
            raise EconomicsLedgerError("currency must be an ISO 4217 alpha code")
        if command.confidence.status.value != "unknown" and not any(
            item.business_event_id is not None for item in command.evidence
        ):
            raise EconomicsLedgerError("a known fact requires Business Event linkage")
        if command.correction_kind not in {
            "original",
            "reversal",
            "supersession",
            "effective_date",
        }:
            raise EconomicsLedgerError("correction kind is invalid")
        if (command.correction_kind == "original") != (
            command.corrects_fact_id is None
        ):
            raise EconomicsLedgerError("correction reference is invalid")
        corrected: BusinessFactRecord | None = None
        if command.corrects_fact_id is not None:
            corrected = await session.scalar(
                select(BusinessFactRecord).where(
                    BusinessFactRecord.company_id == company_id,
                    BusinessFactRecord.id == command.corrects_fact_id,
                )
            )
            if corrected is None:
                raise EconomicsLedgerError("corrected fact does not exist")
            if (
                corrected.subject_type != command.subject_type
                or corrected.subject_id != command.subject_id
                or corrected.category != command.category.value
                or corrected.fact_key != command.fact_key
                or corrected.currency != command.currency.upper()
            ):
                raise EconomicsLedgerError("correction must preserve fact identity")
            if command.correction_kind == "reversal" and command.amount_minor != -(
                corrected.amount_minor or 0
            ):
                raise EconomicsLedgerError("reversal must negate the corrected fact")
            if command.correction_kind == "effective_date" and (
                corrected.period_start == command.period_start
                and corrected.period_end == command.period_end
            ):
                raise EconomicsLedgerError(
                    "effective-date correction must change the fact period"
                )
        input_digest = _command_digest(command)
        existing_fact = await session.scalar(
            select(BusinessFactRecord).where(
                BusinessFactRecord.company_id == company_id,
                BusinessFactRecord.input_digest == input_digest,
            )
        )
        if existing_fact is not None:
            return existing_fact
        if command.corrects_fact_id is not None:
            prior_correction = await session.scalar(
                select(BusinessFactRecord.id).where(
                    BusinessFactRecord.company_id == company_id,
                    BusinessFactRecord.corrects_fact_id == command.corrects_fact_id,
                    BusinessFactRecord.correction_kind == command.correction_kind,
                )
            )
            if prior_correction is not None:
                raise EconomicsLedgerError(
                    "fact already has a different correction of this kind"
                )
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
            accounting_basis=command.accounting_basis,
            correction_kind=command.correction_kind,
            corrects_fact_id=command.corrects_fact_id,
            input_digest=input_digest,
            effective_at=command.effective_at or command.occurred_at,
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
        if corrected is not None and (
            corrected.period_start != command.period_start
            or corrected.period_end != command.period_end
        ):
            corrected_scopes = [
                (corrected.subject_type, corrected.subject_id, corrected.branch_id)
            ]
            if corrected.branch_id is not None and corrected.subject_type != "branch":
                corrected_scopes.append(
                    ("branch", corrected.branch_id, corrected.branch_id)
                )
            if corrected.subject_type != "company":
                corrected_scopes.append(("company", company_id, corrected.branch_id))
            session.add_all(
                RecalculationScopeRecord(
                    company_id=company_id,
                    branch_id=branch_id,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    period_start=corrected.period_start,
                    period_end=corrected.period_end,
                    reason_fact_id=fact.id,
                )
                for scope_type, scope_id, branch_id in corrected_scopes
                if scope_type in {"job", "branch", "company"}
            )
        await session.flush()
        scopes = [(command.subject_type, command.subject_id, command.branch_id)]
        if command.branch_id is not None and command.subject_type != "branch":
            scopes.append(("branch", command.branch_id, command.branch_id))
        if command.subject_type != "company":
            scopes.append(("company", company_id, command.branch_id))
        session.add_all(
            RecalculationScopeRecord(
                company_id=company_id,
                branch_id=branch_id,
                scope_type=scope_type,
                scope_id=scope_id,
                period_start=command.period_start,
                period_end=command.period_end,
                reason_fact_id=fact.id,
            )
            for scope_type, scope_id, branch_id in scopes
            if scope_type in {"job", "branch", "company"}
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
        input_digest = _measurement_digest(company_id, measurement)
        existing = await session.scalar(
            select(ProfitMeasurementRecord).where(
                ProfitMeasurementRecord.company_id == company_id,
                ProfitMeasurementRecord.input_digest == input_digest,
            )
        )
        if existing is not None:
            return existing
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
            input_digest=input_digest,
            engine_version=measurement.engine_version,
            version=version,
        )
        session.add(record)
        await session.flush()
        return record

    @classmethod
    async def record_correction(
        cls,
        session: AsyncSession,
        company_id: UUID,
        command: RecordBusinessFact,
    ) -> BusinessFactRecord:
        if command.correction_kind == "original":
            raise EconomicsLedgerError("correction command must identify its kind")
        return await cls.record_fact(session, company_id, command)

    @classmethod
    async def record_reversal(
        cls, session: AsyncSession, company_id: UUID, command: RecordBusinessFact
    ) -> BusinessFactRecord:
        if command.correction_kind != "reversal":
            raise EconomicsLedgerError("reversal command must use reversal kind")
        return await cls.record_correction(session, company_id, command)

    @classmethod
    async def record_supersession(
        cls, session: AsyncSession, company_id: UUID, command: RecordBusinessFact
    ) -> BusinessFactRecord:
        if command.correction_kind != "supersession":
            raise EconomicsLedgerError(
                "supersession command must use supersession kind"
            )
        return await cls.record_correction(session, company_id, command)

    @classmethod
    async def record_effective_date_correction(
        cls, session: AsyncSession, company_id: UUID, command: RecordBusinessFact
    ) -> BusinessFactRecord:
        if command.correction_kind != "effective_date":
            raise EconomicsLedgerError(
                "effective-date command must use effective_date kind"
            )
        return await cls.record_correction(session, company_id, command)


economics_ledger_service = EconomicsLedgerService()
