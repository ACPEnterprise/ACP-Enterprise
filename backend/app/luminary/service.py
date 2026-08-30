from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.business_economics.models import EconomicsProfitabilityResultRecord
from app.business_economics.workspace import EconomicsWorkspaceService
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import AuthorizationContext

from .contracts import (
    LUMINARY_BRIEFING_VERSION,
    BeaconConditionReference,
    EvidenceReference,
    LuminaryEvidencePackage,
)
from .engine import LUMINARY_ENGINE_VERSION, LuminaryEngine, canonical_digest
from .models import LuminaryBriefingRecord, LuminaryFindingRecord


class LuminaryNotFoundError(LookupError):
    pass


class LuminaryService:
    def __init__(self, *, audit: AuditService = audit_service) -> None:
        self.engine = LuminaryEngine()
        self.audit = audit

    async def analyze(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        period_start: date,
        period_end: date,
        generated_at: datetime | None = None,
    ) -> dict[str, object]:
        package = await self._evidence_package(
            session,
            context=context,
            period_start=period_start,
            period_end=period_end,
            generated_at=generated_at or datetime.now(timezone.utc),
        )
        findings = self.engine.analyze(package)
        briefing = self.engine.briefing(package, findings)
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"luminary:{context.company.id}:{briefing.briefing_id}"},
        )
        existing = await session.scalar(
            select(LuminaryBriefingRecord).where(
                LuminaryBriefingRecord.company_id == context.company.id,
                LuminaryBriefingRecord.briefing_identity == str(briefing.briefing_id),
            )
        )
        if existing is not None:
            return await self._projection(session, existing)

        finding_records: list[LuminaryFindingRecord] = []
        for finding in findings:
            record = await session.scalar(
                select(LuminaryFindingRecord).where(
                    LuminaryFindingRecord.company_id == context.company.id,
                    LuminaryFindingRecord.finding_identity == str(finding.finding_id),
                )
            )
            if record is None:
                predecessor = await self._latest_finding(
                    session,
                    company_id=context.company.id,
                    branch_id=context.active_branch.id
                    if context.active_branch
                    else None,
                    finding_type=finding.finding_type.value,
                    period_start=period_start,
                    period_end=period_end,
                )
                record = LuminaryFindingRecord(
                    id=finding.finding_id,
                    company_id=finding.company_id,
                    branch_id=finding.branch_id,
                    period_start=finding.period_start,
                    period_end=finding.period_end,
                    finding_class=finding.finding_class.value,
                    finding_type=finding.finding_type.value,
                    title=finding.title,
                    summary=finding.summary,
                    observations=[asdict(item) for item in finding.observations],
                    evidence=[asdict(item) for item in finding.evidence],
                    evidence_package_digest=finding.evidence_package_digest,
                    confidence_percent=finding.confidence_percent,
                    completeness=finding.completeness.value,
                    freshness=finding.freshness,
                    explanation=finding.explanation,
                    limitations=list(finding.limitations),
                    investigate_next=list(finding.investigate_next),
                    engine_version=finding.engine_version,
                    definition_version=finding.definition_version,
                    finding_identity=str(finding.finding_id),
                    finding_digest=finding.finding_digest,
                    lifecycle="accepted",
                    supersedes_finding_id=predecessor.id if predecessor else None,
                    generated_at=finding.generated_at,
                    created_by_user_id=context.user.id,
                )
                session.add(record)
            finding_records.append(record)

        briefing_predecessor = await self._latest_briefing(
            session,
            company_id=context.company.id,
            branch_id=context.active_branch.id if context.active_branch else None,
            period_start=period_start,
            period_end=period_end,
        )
        briefing_record = LuminaryBriefingRecord(
            id=briefing.briefing_id,
            company_id=briefing.company_id,
            branch_id=briefing.branch_id,
            period_start=briefing.period_start,
            period_end=briefing.period_end,
            evidence_package_digest=briefing.evidence_package_digest,
            finding_ids=[str(item) for item in briefing.finding_ids],
            finding_digests=list(briefing.finding_digests),
            sections=[
                {"name": name, "finding_ids": [str(item) for item in ids]}
                for name, ids in briefing.sections
            ],
            completeness=briefing.completeness.value,
            summary=briefing.summary,
            engine_version=LUMINARY_ENGINE_VERSION,
            definition_version=LUMINARY_BRIEFING_VERSION,
            briefing_identity=str(briefing.briefing_id),
            briefing_digest=briefing.briefing_digest,
            supersedes_briefing_id=(
                briefing_predecessor.id if briefing_predecessor else None
            ),
            generated_at=briefing.generated_at,
            created_by_user_id=context.user.id,
        )
        session.add(briefing_record)
        await session.flush()
        self._stage(
            session,
            context=context,
            record=briefing_record,
            event_type=EventType.LUMINARY_BRIEFING_ACCEPTED,
            action="luminary.briefing.accepted",
        )
        return self._serialize(briefing_record, finding_records)

    async def latest(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        period_start: date,
        period_end: date,
    ) -> dict[str, object]:
        record = await self._latest_briefing(
            session,
            company_id=context.company.id,
            branch_id=context.active_branch.id if context.active_branch else None,
            period_start=period_start,
            period_end=period_end,
        )
        if record is None:
            raise LuminaryNotFoundError("owner briefing not found")
        self._stage(
            session,
            context=context,
            record=record,
            event_type=EventType.LUMINARY_BRIEFING_ACCESSED,
            action="luminary.briefing.accessed",
        )
        return await self._projection(session, record)

    async def finding(
        self, session: AsyncSession, *, context: AuthorizationContext, finding_id: UUID
    ) -> dict[str, object]:
        query = select(LuminaryFindingRecord).where(
            LuminaryFindingRecord.id == finding_id,
            LuminaryFindingRecord.company_id == context.company.id,
        )
        if context.active_branch is not None:
            query = query.where(
                LuminaryFindingRecord.branch_id == context.active_branch.id
            )
        record = await session.scalar(query)
        if record is None:
            raise LuminaryNotFoundError("finding not found")
        return self._serialize_finding(record)

    async def history(
        self, session: AsyncSession, *, context: AuthorizationContext, limit: int = 24
    ) -> list[dict[str, object]]:
        query = (
            select(LuminaryBriefingRecord)
            .where(LuminaryBriefingRecord.company_id == context.company.id)
            .order_by(
                LuminaryBriefingRecord.period_end.desc(),
                LuminaryBriefingRecord.created_at.desc(),
                LuminaryBriefingRecord.id.desc(),
            )
            .limit(limit)
        )
        if context.active_branch is not None:
            query = query.where(
                LuminaryBriefingRecord.branch_id == context.active_branch.id
            )
        records = (await session.scalars(query)).all()
        return [self._serialize_briefing(item) for item in records]

    async def _evidence_package(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        period_start: date,
        period_end: date,
        generated_at: datetime,
    ) -> LuminaryEvidencePackage:
        economics = await EconomicsWorkspaceService().overview(
            session, context=context, period_start=period_start, period_end=period_end
        )
        query = select(EconomicsProfitabilityResultRecord).where(
            EconomicsProfitabilityResultRecord.company_id == context.company.id,
            EconomicsProfitabilityResultRecord.period_start == period_start,
            EconomicsProfitabilityResultRecord.period_end == period_end,
            EconomicsProfitabilityResultRecord.lifecycle == "admitted",
            EconomicsProfitabilityResultRecord.basis == "actual",
        )
        if context.active_branch is not None:
            query = query.where(
                EconomicsProfitabilityResultRecord.branch_id == context.active_branch.id
            )
        results = tuple((await session.scalars(query)).all())
        references = tuple(
            EvidenceReference(
                "business_economics",
                "profitability_result",
                str(item.id),
                item.result_digest,
            )
            for item in sorted(results, key=lambda value: str(value.id))
        )
        conditions = tuple(
            BeaconConditionReference(
                signal_id=str(item.get("condition_key", "")),
                condition_key=str(item.get("condition_key", "")),
                definition_id=str(item.get("definition_id", "economics.condition")),
                severity=str(item.get("severity", "attention")),
                lifecycle="observed",
                evidence_digest=canonical_digest(item),
                title=str(item.get("title", "Economics evidence needs attention")),
            )
            for item in self._sequence(economics.get("beacon_conditions"))
            if isinstance(item, dict) and item.get("condition_key")
        )
        payload = {
            "company_id": str(context.company.id),
            "branch_id": str(context.active_branch.id)
            if context.active_branch
            else None,
            "period": [period_start.isoformat(), period_end.isoformat()],
            "economics": economics,
            "economics_results": [asdict(item) for item in references],
            "beacon_conditions": [asdict(item) for item in conditions],
        }
        return LuminaryEvidencePackage(
            company_id=context.company.id,
            branch_id=context.active_branch.id if context.active_branch else None,
            period_start=period_start,
            period_end=period_end,
            economics=economics,
            economics_results=references,
            beacon_conditions=conditions,
            package_digest=canonical_digest(payload),
            generated_at=generated_at,
        )

    @staticmethod
    async def _latest_finding(
        session: AsyncSession, **scope: object
    ) -> LuminaryFindingRecord | None:
        query = select(LuminaryFindingRecord).where(
            LuminaryFindingRecord.company_id == scope["company_id"],
            LuminaryFindingRecord.finding_type == scope["finding_type"],
            LuminaryFindingRecord.period_start == scope["period_start"],
            LuminaryFindingRecord.period_end == scope["period_end"],
        )
        branch_id = scope["branch_id"]
        query = (
            query.where(LuminaryFindingRecord.branch_id == branch_id)
            if branch_id
            else query.where(LuminaryFindingRecord.branch_id.is_(None))
        )
        return await session.scalar(
            query.order_by(
                LuminaryFindingRecord.created_at.desc(),
                LuminaryFindingRecord.id.desc(),
            ).limit(1)
        )

    @staticmethod
    def _sequence(value: object) -> list[object]:
        return value if isinstance(value, list) else []

    @staticmethod
    async def _latest_briefing(
        session: AsyncSession, **scope: object
    ) -> LuminaryBriefingRecord | None:
        query = select(LuminaryBriefingRecord).where(
            LuminaryBriefingRecord.company_id == scope["company_id"],
            LuminaryBriefingRecord.period_start == scope["period_start"],
            LuminaryBriefingRecord.period_end == scope["period_end"],
        )
        branch_id = scope["branch_id"]
        query = (
            query.where(LuminaryBriefingRecord.branch_id == branch_id)
            if branch_id
            else query.where(LuminaryBriefingRecord.branch_id.is_(None))
        )
        return await session.scalar(
            query.order_by(
                LuminaryBriefingRecord.created_at.desc(),
                LuminaryBriefingRecord.id.desc(),
            ).limit(1)
        )

    async def _projection(
        self, session: AsyncSession, record: LuminaryBriefingRecord
    ) -> dict[str, object]:
        ids = [UUID(value) for value in record.finding_ids]
        query = select(LuminaryFindingRecord).where(
            LuminaryFindingRecord.id.in_(ids),
            LuminaryFindingRecord.company_id == record.company_id,
        )
        query = (
            query.where(LuminaryFindingRecord.branch_id == record.branch_id)
            if record.branch_id is not None
            else query.where(LuminaryFindingRecord.branch_id.is_(None))
        )
        records = tuple(
            (
                await session.scalars(query)
            ).all()
        )
        by_id = {item.id: item for item in records}
        if len(by_id) != len(ids) or len(record.finding_digests) != len(ids):
            raise RuntimeError("Luminary briefing finding authority is incomplete.")
        ordered = [by_id[value] for value in ids]
        if any(
            finding.finding_digest != digest
            for finding, digest in zip(ordered, record.finding_digests, strict=True)
        ):
            raise RuntimeError("Luminary briefing finding authority conflicts.")
        return self._serialize(record, ordered)

    @classmethod
    def _serialize(
        cls, briefing: LuminaryBriefingRecord, findings: list[LuminaryFindingRecord]
    ) -> dict[str, object]:
        return {
            **cls._serialize_briefing(briefing),
            "findings": [cls._serialize_finding(item) for item in findings],
        }

    @staticmethod
    def _serialize_briefing(record: LuminaryBriefingRecord) -> dict[str, object]:
        return {
            "id": str(record.id),
            "company_id": str(record.company_id),
            "branch_id": str(record.branch_id) if record.branch_id else None,
            "period": {
                "start": record.period_start.isoformat(),
                "end": record.period_end.isoformat(),
            },
            "summary": record.summary,
            "completeness": record.completeness,
            "sections": record.sections,
            "briefing_digest": record.briefing_digest,
            "evidence_package_digest": record.evidence_package_digest,
            "supersedes_briefing_id": str(record.supersedes_briefing_id)
            if record.supersedes_briefing_id
            else None,
            "generated_at": record.generated_at.isoformat(),
        }

    @staticmethod
    def _serialize_finding(record: LuminaryFindingRecord) -> dict[str, object]:
        return {
            "id": str(record.id),
            "finding_class": record.finding_class,
            "finding_type": record.finding_type,
            "title": record.title,
            "summary": record.summary,
            "observations": record.observations,
            "confidence_percent": record.confidence_percent,
            "completeness": record.completeness,
            "freshness": record.freshness,
            "explanation": record.explanation,
            "limitations": record.limitations,
            "investigate_next": record.investigate_next,
            "evidence": record.evidence,
            "finding_digest": record.finding_digest,
            "supersedes_finding_id": str(record.supersedes_finding_id)
            if record.supersedes_finding_id
            else None,
        }

    def _stage(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        record: LuminaryBriefingRecord,
        event_type: EventType,
        action: str,
    ) -> None:
        details: dict[str, object] = {
            "briefing_id": str(record.id),
            "briefing_digest": record.briefing_digest,
            "period_start": record.period_start.isoformat(),
            "period_end": record.period_end.isoformat(),
            "completeness": record.completeness,
        }
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="luminary_briefing",
                entity_id=record.id,
                company_id=record.company_id,
                branch_id=record.branch_id,
                user_id=context.user.id,
                payload=details,
            ),
        )
        self.audit.stage(
            session,
            AuditEntry(
                action=action,
                resource_type="luminary_briefing",
                actor_user_id=context.user.id,
                company_id=record.company_id,
                branch_id=record.branch_id,
                resource_id=record.id,
                details=details,
            ),
        )


luminary_service = LuminaryService()
