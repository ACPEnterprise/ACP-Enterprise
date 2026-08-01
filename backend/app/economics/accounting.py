import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.economics.ledger import EconomicsLedgerError
from app.economics.models import (
    AccountingExportRecord,
    AccountingJournalLineRecord,
    AccountingMappingRecord,
    AccountingPeriodHistoryRecord,
    AccountingPeriodRecord,
    AllocationRunRecord,
    BusinessFactRecord,
    CloseReadinessRecord,
    EconomicsSourceBindingRecord,
    EvidenceReferenceRecord,
    FactEvidenceRecord,
    FinancialIntegrityPublicationRecord,
    GeneralLedgerReconciliationRecord,
    PeriodAuditPackageRecord,
    ProfitabilityProjectionRecord,
    ProfitMeasurementRecord,
    RecalculationScopeRecord,
    ReconciliationResultRecord,
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class ChartMapping:
    mapping_key: str
    classification: str
    account_code: str
    rationale: str
    branch_dimension_key: str | None = None
    dimensions: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class JournalLine:
    account_code: str
    side: str
    amount_minor: int
    source_reference: str
    evidence_digest: str
    branch_id: UUID | None = None
    dimensions: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class JournalExport:
    export_key: str
    currency: str
    lines: tuple[JournalLine, ...]
    source_projection_ids: tuple[UUID, ...]
    corrects_export_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ExportAcknowledgement:
    accepted: bool
    reference: str
    explanation: str | None = None


class SourceBindingService:
    """Records where economics consumes evidence without owning source tables."""

    definitions = (
        ("invoice", "financials", "invoices", "invoice", "bound"),
        ("payment", "financials", "payments", "payment", "bound"),
        ("business_event", "events", "business_events", "business_event", "bound"),
        ("job", "jobs", "jobs", "job", "read_only"),
        ("appointment", "scheduling", "appointments", "appointment", "read_only"),
        ("labor", "workforce", None, "labor_time_entry", "contract_ready"),
        ("materials", "inventory", None, "material_usage", "contract_ready"),
        ("equipment", "workforce", None, "equipment_utilization", "contract_ready"),
        ("fleet", "fleet", None, "truck_activity", "contract_ready"),
        ("overhead", "accounting", None, "overhead", "contract_ready"),
    )

    @classmethod
    async def bind_available_sources(
        cls, session: AsyncSession, company_id: UUID
    ) -> tuple[EconomicsSourceBindingRecord, ...]:
        records: list[EconomicsSourceBindingRecord] = []
        for source_type, owner, table, adapter, status in cls.definitions:
            content = {
                "source_type": source_type,
                "owner_domain": owner,
                "source_table": table,
                "adapter_key": adapter,
                "status": status,
                "requirements": [
                    "source identity",
                    "SHA-256 evidence",
                    "source version",
                    "Business Event linkage for measured facts",
                ],
            }
            digest = _digest(content)
            existing = await session.scalar(
                select(EconomicsSourceBindingRecord).where(
                    EconomicsSourceBindingRecord.company_id == company_id,
                    EconomicsSourceBindingRecord.input_digest == digest,
                )
            )
            if existing is not None:
                records.append(existing)
                continue
            version = (
                int(
                    await session.scalar(
                        select(
                            func.coalesce(
                                func.max(EconomicsSourceBindingRecord.version), 0
                            )
                        ).where(
                            EconomicsSourceBindingRecord.company_id == company_id,
                            EconomicsSourceBindingRecord.source_type == source_type,
                        )
                    )
                    or 0
                )
                + 1
            )
            record = EconomicsSourceBindingRecord(
                company_id=company_id,
                source_type=source_type,
                owner_domain=owner,
                source_table=table,
                adapter_key=adapter,
                status=status,
                evidence_requirements=content["requirements"],
                version=version,
                input_digest=digest,
            )
            session.add(record)
            records.append(record)
        await session.flush()
        return tuple(records)


class AccountingContractService:
    @staticmethod
    async def define_mapping(
        session: AsyncSession, company_id: UUID, mapping: ChartMapping
    ) -> AccountingMappingRecord:
        if not all(
            value.strip()
            for value in (
                mapping.mapping_key,
                mapping.classification,
                mapping.account_code,
                mapping.rationale,
            )
        ):
            raise EconomicsLedgerError("accounting mapping fields are required")
        version = (
            int(
                await session.scalar(
                    select(
                        func.coalesce(func.max(AccountingMappingRecord.version), 0)
                    ).where(
                        AccountingMappingRecord.company_id == company_id,
                        AccountingMappingRecord.mapping_key == mapping.mapping_key,
                    )
                )
                or 0
            )
            + 1
        )
        record = AccountingMappingRecord(
            company_id=company_id,
            mapping_key=mapping.mapping_key,
            classification=mapping.classification,
            account_code=mapping.account_code,
            branch_dimension_key=mapping.branch_dimension_key,
            dimensions=mapping.dimensions or {},
            rationale=mapping.rationale,
            version=version,
        )
        session.add(record)
        await session.flush()
        return record

    @staticmethod
    async def prepare_export(
        session: AsyncSession,
        company_id: UUID,
        period_id: UUID,
        command: JournalExport,
    ) -> AccountingExportRecord:
        period = await session.scalar(
            select(AccountingPeriodRecord).where(
                AccountingPeriodRecord.company_id == company_id,
                AccountingPeriodRecord.id == period_id,
            )
        )
        if period is None:
            raise EconomicsLedgerError("accounting period was not found")
        if not command.lines:
            raise EconomicsLedgerError("journal export requires lines")
        if len(command.currency) != 3 or not command.currency.isalpha():
            raise EconomicsLedgerError("journal export currency is invalid")
        if any(
            line.side not in {"debit", "credit"}
            or line.amount_minor <= 0
            or len(line.evidence_digest) != 64
            for line in command.lines
        ):
            raise EconomicsLedgerError("journal export line is invalid")
        debit = sum(line.amount_minor for line in command.lines if line.side == "debit")
        credit = sum(
            line.amount_minor for line in command.lines if line.side == "credit"
        )
        if debit != credit:
            raise EconomicsLedgerError("journal export must balance")
        canonical = {
            "company_id": str(company_id),
            "period_id": str(period_id),
            "export_key": command.export_key,
            "currency": command.currency.upper(),
            "lines": [asdict(item) for item in command.lines],
            "source_projection_ids": sorted(
                str(item) for item in command.source_projection_ids
            ),
            "corrects_export_id": (
                str(command.corrects_export_id) if command.corrects_export_id else None
            ),
        }
        checksum = _digest(canonical)
        existing = await session.scalar(
            select(AccountingExportRecord).where(
                AccountingExportRecord.company_id == company_id,
                AccountingExportRecord.checksum == checksum,
            )
        )
        if existing is not None:
            return existing
        if command.corrects_export_id is not None:
            corrected = await session.scalar(
                select(AccountingExportRecord).where(
                    AccountingExportRecord.company_id == company_id,
                    AccountingExportRecord.id == command.corrects_export_id,
                )
            )
            if corrected is None or corrected.period_id != period_id:
                raise EconomicsLedgerError("corrected export was not found in period")
        version = (
            int(
                await session.scalar(
                    select(
                        func.coalesce(func.max(AccountingExportRecord.version), 0)
                    ).where(
                        AccountingExportRecord.company_id == company_id,
                        AccountingExportRecord.export_key == command.export_key,
                    )
                )
                or 0
            )
            + 1
        )
        export = AccountingExportRecord(
            company_id=company_id,
            period_id=period_id,
            export_key=command.export_key,
            status="corrected" if command.corrects_export_id else "prepared",
            currency=command.currency.upper(),
            debit_minor=debit,
            credit_minor=credit,
            checksum=checksum,
            source_projection_ids=[str(item) for item in command.source_projection_ids],
            corrects_export_id=command.corrects_export_id,
            version=version,
        )
        session.add(export)
        await session.flush()
        session.add_all(
            AccountingJournalLineRecord(
                company_id=company_id,
                export_id=export.id,
                line_number=index,
                account_code=line.account_code,
                side=line.side,
                amount_minor=line.amount_minor,
                branch_id=line.branch_id,
                source_reference=line.source_reference,
                evidence_digest=line.evidence_digest,
                dimensions=line.dimensions or {},
            )
            for index, line in enumerate(command.lines, start=1)
        )
        await session.flush()
        return export

    @staticmethod
    async def mark_exported(
        session: AsyncSession, company_id: UUID, export_id: UUID, checksum: str
    ) -> AccountingExportRecord:
        export = await session.scalar(
            select(AccountingExportRecord)
            .where(
                AccountingExportRecord.company_id == company_id,
                AccountingExportRecord.id == export_id,
            )
            .with_for_update()
        )
        if export is None or export.checksum != checksum:
            raise EconomicsLedgerError("accounting export checksum does not match")
        if export.status in {"acknowledged", "rejected"}:
            return export
        export.status = "exported"
        await session.flush()
        return export

    @staticmethod
    async def acknowledge_export(
        session: AsyncSession,
        company_id: UUID,
        export_id: UUID,
        acknowledgement: ExportAcknowledgement,
    ) -> AccountingExportRecord:
        export = await session.scalar(
            select(AccountingExportRecord)
            .where(
                AccountingExportRecord.company_id == company_id,
                AccountingExportRecord.id == export_id,
            )
            .with_for_update()
        )
        if export is None:
            raise EconomicsLedgerError("accounting export was not found")
        if export.status in {"acknowledged", "rejected"}:
            if export.acknowledgement_reference == acknowledgement.reference:
                return export
            raise EconomicsLedgerError(
                "accounting export already has an acknowledgement"
            )
        export.status = "acknowledged" if acknowledgement.accepted else "rejected"
        export.acknowledgement_reference = acknowledgement.reference
        export.rejection_reason = (
            None if acknowledgement.accepted else acknowledgement.explanation
        )
        export.acknowledged_at = datetime.now(timezone.utc)
        await session.flush()
        return export


class GeneralLedgerReconciliationService:
    @staticmethod
    async def reconcile(
        session: AsyncSession, company_id: UUID, period_id: UUID
    ) -> GeneralLedgerReconciliationRecord:
        period = await session.scalar(
            select(AccountingPeriodRecord).where(
                AccountingPeriodRecord.company_id == company_id,
                AccountingPeriodRecord.id == period_id,
            )
        )
        if period is None:
            raise EconomicsLedgerError("accounting period was not found")
        correcting_fact = BusinessFactRecord.__table__.alias("gl_correcting_fact")
        facts = tuple(
            (
                await session.scalars(
                    select(BusinessFactRecord).where(
                        BusinessFactRecord.company_id == company_id,
                        BusinessFactRecord.period_start >= period.period_start,
                        BusinessFactRecord.period_end <= period.period_end,
                        BusinessFactRecord.accounting_basis == "accrual",
                        ~exists(
                            select(1).where(
                                correcting_fact.c.company_id == company_id,
                                correcting_fact.c.corrects_fact_id
                                == BusinessFactRecord.id,
                                correcting_fact.c.correction_kind.in_(
                                    ("supersession", "effective_date")
                                ),
                            )
                        ),
                    )
                )
            ).all()
        )
        correcting_export = AccountingExportRecord.__table__.alias("correcting_export")
        exports = tuple(
            (
                await session.scalars(
                    select(AccountingExportRecord).where(
                        AccountingExportRecord.company_id == company_id,
                        AccountingExportRecord.period_id == period_id,
                        ~exists(
                            select(1).where(
                                correcting_export.c.company_id == company_id,
                                correcting_export.c.corrects_export_id
                                == AccountingExportRecord.id,
                            )
                        ),
                    )
                )
            ).all()
        )
        amounts = [item.amount_minor for item in facts]
        known = all(item is not None for item in amounts)
        source_amount = (
            sum(abs(item) for item in amounts if item is not None) if known else None
        )
        accepted = [item for item in exports if item.status == "acknowledged"]
        exported = sum(item.debit_minor for item in accepted) if exports else None
        rejected = sum(item.status == "rejected" for item in exports)
        corrections = sum(item.corrects_export_id is not None for item in exports)
        duplicate_count = len(exports) - len({item.checksum for item in exports})
        journal_balance = sum(item.debit_minor - item.credit_minor for item in exports)
        ownership_mismatch = int(
            await session.scalar(
                select(func.count())
                .select_from(AccountingJournalLineRecord)
                .join(
                    AccountingExportRecord,
                    AccountingExportRecord.id == AccountingJournalLineRecord.export_id,
                )
                .where(
                    AccountingExportRecord.period_id == period_id,
                    AccountingJournalLineRecord.company_id != company_id,
                )
            )
            or 0
        )
        variance = (
            source_amount - exported
            if source_amount is not None and exported is not None
            else None
        )
        residual = variance
        status = (
            "unknown"
            if variance is None
            else "passed"
            if variance == 0
            and journal_balance == 0
            and rejected == 0
            and duplicate_count == 0
            and ownership_mismatch == 0
            else "failed"
        )
        content = {
            "period_id": str(period_id),
            "fact_ids": sorted(str(item.id) for item in facts),
            "export_checksums": sorted(item.checksum for item in exports),
            "source": source_amount,
            "exported": exported,
            "balance": journal_balance,
            "rejected": rejected,
            "duplicates": duplicate_count,
            "corrections": corrections,
            "variance": variance,
            "ownership_mismatch": ownership_mismatch,
        }
        digest = _digest(content)
        existing = await session.scalar(
            select(GeneralLedgerReconciliationRecord).where(
                GeneralLedgerReconciliationRecord.company_id == company_id,
                GeneralLedgerReconciliationRecord.input_digest == digest,
            )
        )
        if existing is not None:
            return existing
        version = (
            int(
                await session.scalar(
                    select(
                        func.coalesce(
                            func.max(GeneralLedgerReconciliationRecord.version), 0
                        )
                    ).where(
                        GeneralLedgerReconciliationRecord.company_id == company_id,
                        GeneralLedgerReconciliationRecord.period_id == period_id,
                    )
                )
                or 0
            )
            + 1
        )
        record = GeneralLedgerReconciliationRecord(
            company_id=company_id,
            period_id=period_id,
            status=status,
            source_represented_minor=source_amount,
            exported_minor=exported,
            journal_balance_minor=journal_balance,
            rejected_line_count=rejected,
            duplicate_export_count=duplicate_count,
            correction_count=corrections,
            period_variance_minor=variance,
            ownership_mismatch_count=ownership_mismatch,
            unexplained_residual_minor=residual,
            explanation=(
                "Source evidence is incomplete or no export exists."
                if status == "unknown"
                else "General ledger representation reconciled."
                if status == "passed"
                else "General ledger representation has unresolved variance."
            ),
            input_digest=digest,
            version=version,
        )
        session.add(record)
        await session.flush()
        return record


class FinancialCloseService:
    @staticmethod
    async def evaluate_readiness(
        session: AsyncSession,
        company_id: UUID,
        period_id: UUID,
        responsible_owner_id: UUID,
    ) -> CloseReadinessRecord:
        period = await session.scalar(
            select(AccountingPeriodRecord).where(
                AccountingPeriodRecord.company_id == company_id,
                AccountingPeriodRecord.id == period_id,
            )
        )
        if period is None:
            raise EconomicsLedgerError("accounting period was not found")
        facts = tuple(
            (
                await session.scalars(
                    select(BusinessFactRecord).where(
                        BusinessFactRecord.company_id == company_id,
                        BusinessFactRecord.period_start >= period.period_start,
                        BusinessFactRecord.period_end <= period.period_end,
                    )
                )
            ).all()
        )
        fact_ids = [item.id for item in facts]
        source_linked = (
            int(
                await session.scalar(
                    select(func.count(func.distinct(FactEvidenceRecord.fact_id)))
                    .join(
                        EvidenceReferenceRecord,
                        EvidenceReferenceRecord.id == FactEvidenceRecord.evidence_id,
                    )
                    .where(
                        FactEvidenceRecord.company_id == company_id,
                        FactEvidenceRecord.fact_id.in_(fact_ids),
                        EvidenceReferenceRecord.kind == "source_record",
                    )
                )
                or 0
            )
            if fact_ids
            else 0
        )
        allocation_imbalance = int(
            await session.scalar(
                select(func.count())
                .select_from(AllocationRunRecord)
                .where(
                    AllocationRunRecord.company_id == company_id,
                    AllocationRunRecord.period_id == period_id,
                    AllocationRunRecord.residual_amount_minor != 0,
                )
            )
            or 0
        )
        incomplete_measurements = int(
            await session.scalar(
                select(func.count())
                .select_from(ProfitMeasurementRecord)
                .where(
                    ProfitMeasurementRecord.company_id == company_id,
                    ProfitMeasurementRecord.period_start >= period.period_start,
                    ProfitMeasurementRecord.period_end <= period.period_end,
                    (
                        ProfitMeasurementRecord.net_profit_minor.is_(None)
                        | ProfitMeasurementRecord.gross_profit_minor.is_(None)
                    ),
                )
            )
            or 0
        )
        pending = int(
            await session.scalar(
                select(func.count())
                .select_from(RecalculationScopeRecord)
                .where(
                    RecalculationScopeRecord.company_id == company_id,
                    RecalculationScopeRecord.period_start >= period.period_start,
                    RecalculationScopeRecord.period_end <= period.period_end,
                    RecalculationScopeRecord.processed_at.is_(None),
                )
            )
            or 0
        )
        unresolved_corrections = int(
            await session.scalar(
                select(func.count(func.distinct(BusinessFactRecord.id)))
                .join(
                    RecalculationScopeRecord,
                    RecalculationScopeRecord.reason_fact_id == BusinessFactRecord.id,
                )
                .where(
                    BusinessFactRecord.company_id == company_id,
                    BusinessFactRecord.correction_kind != "original",
                    RecalculationScopeRecord.processed_at.is_(None),
                )
            )
            or 0
        )
        latest_reconciliations = tuple(
            (
                await session.scalars(
                    select(ReconciliationResultRecord)
                    .where(
                        ReconciliationResultRecord.company_id == company_id,
                        ReconciliationResultRecord.period_id == period_id,
                    )
                    .order_by(ReconciliationResultRecord.reconciled_at.desc())
                )
            ).all()
        )
        latest_by_kind = {item.kind: item for item in reversed(latest_reconciliations)}
        gl = await session.scalar(
            select(GeneralLedgerReconciliationRecord)
            .where(
                GeneralLedgerReconciliationRecord.company_id == company_id,
                GeneralLedgerReconciliationRecord.period_id == period_id,
            )
            .order_by(GeneralLedgerReconciliationRecord.version.desc())
            .limit(1)
        )
        checks: dict[str, object] = {
            "period_version": period.version,
            "source_completeness": {
                "expected": len(facts),
                "represented": source_linked,
                "complete": source_linked == len(facts),
            },
            "allocation_balance": allocation_imbalance == 0,
            "measurement_completeness": incomplete_measurements == 0 and bool(facts),
            "stale_measurements": pending,
            "reconciliation_status": {
                key: value.status for key, value in latest_by_kind.items()
            },
            "unresolved_corrections": unresolved_corrections,
            "general_ledger_status": gl.status if gl else "unknown",
            "responsible_owner": str(responsible_owner_id),
        }
        blockers: list[str] = []
        if source_linked != len(facts) or not facts:
            blockers.append("source_completeness")
        if allocation_imbalance:
            blockers.append("allocation_balance")
        if incomplete_measurements or not facts:
            blockers.append("measurement_completeness")
        if pending:
            blockers.append("stale_measurements")
        required = {"source", "ledger", "allocation", "measurement", "evidence"}
        if set(latest_by_kind) != required or any(
            item.status != "passed" for item in latest_by_kind.values()
        ):
            blockers.append("reconciliation_status")
        if unresolved_corrections:
            blockers.append("unresolved_corrections")
        if gl is None or gl.status != "passed":
            blockers.append("general_ledger_reconciliation")
        content = {
            "period_version": period.version,
            "checks": checks,
            "blockers": blockers,
        }
        digest = _digest(content)
        existing = await session.scalar(
            select(CloseReadinessRecord).where(
                CloseReadinessRecord.company_id == company_id,
                CloseReadinessRecord.input_digest == digest,
            )
        )
        if existing is not None:
            return existing
        version = (
            int(
                await session.scalar(
                    select(
                        func.coalesce(func.max(CloseReadinessRecord.version), 0)
                    ).where(
                        CloseReadinessRecord.company_id == company_id,
                        CloseReadinessRecord.period_id == period_id,
                    )
                )
                or 0
            )
            + 1
        )
        record = CloseReadinessRecord(
            company_id=company_id,
            period_id=period_id,
            responsible_owner_id=responsible_owner_id,
            ready=not blockers,
            checks=checks,
            blockers=blockers,
            input_digest=digest,
            version=version,
        )
        session.add(record)
        await session.flush()
        return record


class PeriodAuditPackageService:
    tables = (
        ("transition_history", AccountingPeriodHistoryRecord, "period_id"),
        ("facts", BusinessFactRecord, None),
        ("allocation_runs", AllocationRunRecord, "period_id"),
        ("measurements", ProfitMeasurementRecord, None),
        ("projections", ProfitabilityProjectionRecord, None),
        ("reconciliation", ReconciliationResultRecord, "period_id"),
        ("close_readiness", CloseReadinessRecord, "period_id"),
        ("exports", AccountingExportRecord, "period_id"),
        ("gl_reconciliation", GeneralLedgerReconciliationRecord, "period_id"),
    )

    @classmethod
    async def build(
        cls, session: AsyncSession, company_id: UUID, period_id: UUID
    ) -> PeriodAuditPackageRecord:
        period = await session.scalar(
            select(AccountingPeriodRecord).where(
                AccountingPeriodRecord.company_id == company_id,
                AccountingPeriodRecord.id == period_id,
            )
        )
        if period is None:
            raise EconomicsLedgerError("accounting period was not found")
        manifest: dict[str, object] = {
            "period": {
                "id": str(period.id),
                "start": period.period_start.isoformat(),
                "end": period.period_end.isoformat(),
                "status": period.status,
                "version": period.version,
                "responsible_owner_id": str(period.responsible_owner_id),
                "reason": period.reason,
            }
        }
        for name, model, period_field in cls.tables:
            statement = select(model.id).where(model.company_id == company_id)
            if period_field:
                statement = statement.where(getattr(model, period_field) == period_id)
            elif model in {
                BusinessFactRecord,
                ProfitMeasurementRecord,
                ProfitabilityProjectionRecord,
            }:
                period_model = cast(Any, model)
                statement = statement.where(
                    period_model.period_start >= period.period_start,
                    period_model.period_end <= period.period_end,
                )
            manifest[name] = sorted(
                str(item) for item in (await session.scalars(statement)).all()
            )
        evidence_digests = tuple(
            (
                await session.scalars(
                    select(BusinessFactRecord.input_digest).where(
                        BusinessFactRecord.company_id == company_id,
                        BusinessFactRecord.period_start >= period.period_start,
                        BusinessFactRecord.period_end <= period.period_end,
                    )
                )
            ).all()
        )
        manifest["evidence_digests"] = sorted(evidence_digests)
        manifest["facts_detail"] = [
            {
                "id": str(item.id),
                "category": item.category,
                "amount_minor": item.amount_minor,
                "confidence": item.confidence_status,
                "confidence_percentage": item.confidence_percentage,
                "explanation": item.confidence_explanation,
                "correction_kind": item.correction_kind,
                "corrects_fact_id": str(item.corrects_fact_id)
                if item.corrects_fact_id
                else None,
                "evidence_digests": sorted(
                    str(evidence.get("content_digest"))
                    for evidence in item.evidence_snapshot
                ),
            }
            for item in (
                await session.scalars(
                    select(BusinessFactRecord).where(
                        BusinessFactRecord.company_id == company_id,
                        BusinessFactRecord.period_start >= period.period_start,
                        BusinessFactRecord.period_end <= period.period_end,
                    )
                )
            ).all()
        ]
        manifest["measurement_confidence"] = [
            {
                "id": str(item.id),
                "status": item.confidence_status,
                "percentage": item.confidence_percentage,
                "explanation": item.confidence_explanation,
                "engine_version": item.engine_version,
            }
            for item in (
                await session.scalars(
                    select(ProfitMeasurementRecord).where(
                        ProfitMeasurementRecord.company_id == company_id,
                        ProfitMeasurementRecord.period_start >= period.period_start,
                        ProfitMeasurementRecord.period_end <= period.period_end,
                    )
                )
            ).all()
        ]
        manifest["corrections"] = sorted(
            str(item)
            for item in (
                await session.scalars(
                    select(BusinessFactRecord.id).where(
                        BusinessFactRecord.company_id == company_id,
                        BusinessFactRecord.period_start >= period.period_start,
                        BusinessFactRecord.period_end <= period.period_end,
                        BusinessFactRecord.correction_kind != "original",
                    )
                )
            ).all()
        )
        digest = _digest(manifest)
        existing = await session.scalar(
            select(PeriodAuditPackageRecord).where(
                PeriodAuditPackageRecord.company_id == company_id,
                PeriodAuditPackageRecord.package_digest == digest,
            )
        )
        if existing is not None:
            return existing
        version = (
            int(
                await session.scalar(
                    select(
                        func.coalesce(func.max(PeriodAuditPackageRecord.version), 0)
                    ).where(
                        PeriodAuditPackageRecord.company_id == company_id,
                        PeriodAuditPackageRecord.period_id == period_id,
                    )
                )
                or 0
            )
            + 1
        )
        record = PeriodAuditPackageRecord(
            company_id=company_id,
            period_id=period_id,
            manifest=manifest,
            package_digest=digest,
            version=version,
        )
        session.add(record)
        await session.flush()
        return record


class FinancialIntegrityPublicationService:
    @staticmethod
    async def publish(
        session: AsyncSession,
        company_id: UUID,
        period_id: UUID,
        projection_id: UUID,
    ) -> FinancialIntegrityPublicationRecord:
        projection = await session.scalar(
            select(ProfitabilityProjectionRecord).where(
                ProfitabilityProjectionRecord.company_id == company_id,
                ProfitabilityProjectionRecord.id == projection_id,
            )
        )
        readiness = await session.scalar(
            select(CloseReadinessRecord)
            .where(
                CloseReadinessRecord.company_id == company_id,
                CloseReadinessRecord.period_id == period_id,
            )
            .order_by(CloseReadinessRecord.version.desc())
            .limit(1)
        )
        if projection is None or readiness is None:
            raise EconomicsLedgerError(
                "projection or financial integrity evidence is missing"
            )
        if not readiness.ready:
            raise EconomicsLedgerError(
                "only reconciled, complete projections may be published downstream"
            )
        evidence = sorted(projection.input_measurement_ids)
        complete = (
            100 if readiness.ready else max(0, 100 - len(readiness.blockers) * 10)
        )
        integrity = "reconciled"
        content = {
            "projection": str(projection.id),
            "projection_digest": projection.input_digest,
            "readiness_digest": readiness.input_digest,
            "integrity": integrity,
            "lineage": evidence,
        }
        digest = _digest(content)
        existing = await session.scalar(
            select(FinancialIntegrityPublicationRecord).where(
                FinancialIntegrityPublicationRecord.company_id == company_id,
                FinancialIntegrityPublicationRecord.input_digest == digest,
            )
        )
        if existing is not None:
            return existing
        version = (
            int(
                await session.scalar(
                    select(
                        func.coalesce(
                            func.max(FinancialIntegrityPublicationRecord.version), 0
                        )
                    ).where(
                        FinancialIntegrityPublicationRecord.company_id == company_id,
                        FinancialIntegrityPublicationRecord.projection_id
                        == projection_id,
                    )
                )
                or 0
            )
            + 1
        )
        record = FinancialIntegrityPublicationRecord(
            company_id=company_id,
            projection_id=projection_id,
            period_id=period_id,
            confidence_status=projection.confidence_status,
            confidence_percentage=projection.confidence_percentage,
            completeness_percentage=complete,
            freshness_status="current" if readiness.ready else "unknown",
            evidence_lineage=evidence,
            integrity_status=integrity,
            input_digest=digest,
            version=version,
        )
        session.add(record)
        await session.flush()
        return record
