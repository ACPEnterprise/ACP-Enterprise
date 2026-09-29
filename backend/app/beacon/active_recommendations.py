"""Read-only active owner recommendations from exact canonical evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_migration.models import CustomerPopulationRefreshRun
from app.luminary.models import LuminaryFindingRecord
from app.platform.branch.models import Branch
from app.platform.permissions.authorization import AuthorizationContext
from app.scheduling.models import (
    BranchSchedulingCalendar,
    BranchSchedulingWeeklyInterval,
)

PriorityWindow = Literal["NOW", "TODAY", "THIS_WEEK", "WATCH"]
RecommendationKind = Literal["EVIDENCE_GAP", "MEASURED_FINDING"]


@dataclass(frozen=True, slots=True)
class RecommendationEvidence:
    entity_type: str
    entity_id: UUID
    digest: str | None
    as_of: datetime


@dataclass(frozen=True, slots=True)
class ActiveOwnerRecommendation:
    recommendation_id: UUID
    definition_id: str
    definition_version: int
    kind: RecommendationKind
    title: str
    measured_fact: str
    interpretation: str
    recommended_human_action: str
    source_authority: str
    evidence_as_of: datetime
    coverage: str
    confidence: str
    limitations: tuple[str, ...]
    priority_window: PriorityWindow
    priority_score: int
    priority_reason: str
    improves_if_resolved: str
    drilldown_path: str
    action_destination: str
    evidence: tuple[RecommendationEvidence, ...]
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class SchedulingGapFact:
    branch_id: UUID
    branch_name: str
    calendar_id: UUID | None
    interval_count: int
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class CustomerAdmissionGapFact:
    run_id: UUID
    branch_id: UUID
    source_system: str
    total_count: int
    bound_count: int
    held_count: int
    ambiguous_count: int
    unexplained_count: int
    evidence_digest: str
    completed_at: datetime


@dataclass(frozen=True, slots=True)
class LuminaryFindingFact:
    finding_id: UUID
    branch_id: UUID | None
    finding_class: str
    finding_type: str
    title: str
    summary: str
    explanation: str
    confidence_percent: int
    completeness: str
    freshness: str
    limitations: tuple[str, ...]
    investigate_next: tuple[str, ...]
    finding_digest: str
    period_start: str
    period_end: str
    generated_at: datetime


class ActiveRecommendationReasoner:
    """Maps accepted facts to explanation; it performs no source-domain inference."""

    def reason(
        self,
        *,
        scheduling: tuple[SchedulingGapFact, ...] = (),
        customers: tuple[CustomerAdmissionGapFact, ...] = (),
        luminary: tuple[LuminaryFindingFact, ...] = (),
        evaluated_at: datetime,
    ) -> tuple[ActiveOwnerRecommendation, ...]:
        values = [
            *(self._scheduling(item, evaluated_at) for item in scheduling),
            *(self._customers(item, evaluated_at) for item in customers),
            *(self._luminary(item, evaluated_at) for item in luminary),
        ]
        return tuple(
            sorted(
                values,
                key=lambda item: (
                    -item.priority_score,
                    item.evidence_as_of,
                    str(item.recommendation_id),
                ),
            )
        )

    def _scheduling(
        self, fact: SchedulingGapFact, evaluated_at: datetime
    ) -> ActiveOwnerRecommendation:
        missing = (
            "no Branch scheduling calendar exists"
            if fact.calendar_id is None
            else "the Branch calendar has no operating-hour intervals"
        )
        return self._build(
            definition_id="evidence_gap.branch_scheduling_policy",
            kind="EVIDENCE_GAP",
            subject=fact.branch_id,
            title=f"{fact.branch_name} scheduling policy is incomplete",
            measured_fact=f"{fact.branch_name}: {missing}.",
            interpretation=(
                "Scheduling and Dispatch cannot reliably evaluate bookable capacity "
                "for this Branch."
            ),
            action="Configure and review the Branch scheduling calendar.",
            source="Scheduling Branch calendar authority",
            as_of=fact.observed_at,
            coverage="One authorized Branch",
            confidence="HIGH",
            limitations=(
                "This is a configuration-readiness finding, not evidence of poor employee performance.",
            ),
            window="TODAY",
            score=80,
            reason=(
                "Owner configuration is required and Scheduling/Dispatch decisions are blocked; "
                "no financial impact is inferred."
            ),
            improves="Bookable capacity and Dispatch scheduling readiness become evaluable.",
            path="/administration#branch-scheduling-setup",
            destination="Administration → Branch Scheduling Setup",
            evidence=(
                RecommendationEvidence(
                    "branch_scheduling_calendar",
                    fact.calendar_id or fact.branch_id,
                    None,
                    fact.observed_at,
                ),
            ),
            evaluated_at=evaluated_at,
        )

    def _customers(
        self, fact: CustomerAdmissionGapFact, evaluated_at: datetime
    ) -> ActiveOwnerRecommendation:
        unresolved = fact.held_count + fact.ambiguous_count + fact.unexplained_count
        return self._build(
            definition_id="evidence_gap.customer_population_admission",
            kind="EVIDENCE_GAP",
            subject=fact.run_id,
            title="Customer source reconciliation is incomplete",
            measured_fact=(
                f"The latest {fact.source_system} population reconciliation bound "
                f"{fact.bound_count} of {fact.total_count} records; {unresolved} remain "
                "held, ambiguous, or unexplained."
            ),
            interpretation=(
                "Customer history and downstream attribution coverage remain limited "
                "for the unresolved source population."
            ),
            action="Review the exact unresolved Customer reconciliation queue.",
            source="Customer population reconciliation authority",
            as_of=fact.completed_at,
            coverage=f"Latest Branch population run · {fact.total_count} source records",
            confidence="HIGH",
            limitations=(
                "Beacon does not infer Customer identity or perform fuzzy matching.",
                "This recommendation does not authorize source admission.",
            ),
            window="THIS_WEEK",
            score=60,
            reason=(
                "A completed canonical run proves unresolved coverage; urgency is limited "
                "because no current operational dependency is inferred."
            ),
            improves="Customer history and attribution coverage become more complete.",
            path="/administration#migration-readiness",
            destination="Administration → Customer source reconciliation",
            evidence=(
                RecommendationEvidence(
                    "customer_population_refresh_run",
                    fact.run_id,
                    fact.evidence_digest,
                    fact.completed_at,
                ),
            ),
            evaluated_at=evaluated_at,
        )

    def _luminary(
        self, fact: LuminaryFindingFact, evaluated_at: datetime
    ) -> ActiveOwnerRecommendation:
        evidence_gap = fact.finding_class in {
            "insufficient_evidence",
            "conflicting_evidence",
            "policy_required",
        }
        window: PriorityWindow = "TODAY" if evidence_gap else "THIS_WEEK"
        score = 75 if fact.finding_class == "conflicting_evidence" else 65
        if not evidence_gap:
            score = 55
        action = (
            fact.investigate_next[0]
            if fact.investigate_next
            else "Review the accepted Luminary finding and its supporting evidence."
        )
        return self._build(
            definition_id=f"luminary.{fact.finding_type}",
            kind="EVIDENCE_GAP" if evidence_gap else "MEASURED_FINDING",
            subject=fact.finding_id,
            title=fact.title,
            measured_fact=fact.summary,
            interpretation=fact.explanation,
            action=action,
            source="Accepted Luminary finding",
            as_of=fact.generated_at,
            coverage=f"{fact.period_start} through {fact.period_end}",
            confidence=f"{fact.confidence_percent}% (Luminary canonical confidence)",
            limitations=fact.limitations,
            window=window,
            score=score,
            reason=(
                "Accepted Luminary evidence is conflicting and blocks reliable conclusions."
                if fact.finding_class == "conflicting_evidence"
                else "Accepted Luminary evidence identifies a management evidence or policy gap."
                if evidence_gap
                else "Accepted Luminary measured evidence warrants human investigation; no cause is asserted."
            ),
            improves=(
                "Economics interpretation and owner decision confidence improve."
                if evidence_gap
                else "Management can investigate the strongest measured drivers with source evidence."
            ),
            path="/luminary",
            destination="Luminary → Accepted finding evidence",
            evidence=(
                RecommendationEvidence(
                    "luminary_finding",
                    fact.finding_id,
                    fact.finding_digest,
                    fact.generated_at,
                ),
            ),
            evaluated_at=evaluated_at,
        )

    @staticmethod
    def _build(
        *,
        definition_id: str,
        kind: RecommendationKind,
        subject: UUID,
        title: str,
        measured_fact: str,
        interpretation: str,
        action: str,
        source: str,
        as_of: datetime,
        coverage: str,
        confidence: str,
        limitations: tuple[str, ...],
        window: PriorityWindow,
        score: int,
        reason: str,
        improves: str,
        path: str,
        destination: str,
        evidence: tuple[RecommendationEvidence, ...],
        evaluated_at: datetime,
    ) -> ActiveOwnerRecommendation:
        identity = json.dumps(
            {
                "definition": definition_id,
                "subject": str(subject),
                "evidence": [item.digest or str(item.entity_id) for item in evidence],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        recommendation_id = uuid5(NAMESPACE_URL, f"beacon-recommendation:{identity}")
        return ActiveOwnerRecommendation(
            recommendation_id=recommendation_id,
            definition_id=definition_id,
            definition_version=1,
            kind=kind,
            title=title,
            measured_fact=measured_fact,
            interpretation=interpretation,
            recommended_human_action=action,
            source_authority=source,
            evidence_as_of=as_of,
            coverage=coverage,
            confidence=confidence,
            limitations=limitations,
            priority_window=window,
            priority_score=score,
            priority_reason=reason,
            improves_if_resolved=improves,
            drilldown_path=path,
            action_destination=destination,
            evidence=evidence,
            expires_at=evaluated_at + timedelta(minutes=15),
        )


class ActiveRecommendationService:
    def __init__(self, reasoner: ActiveRecommendationReasoner | None = None) -> None:
        self.reasoner = reasoner or ActiveRecommendationReasoner()

    async def list(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        evaluated_at: datetime | None = None,
    ) -> tuple[ActiveOwnerRecommendation, ...]:
        now = evaluated_at or datetime.now(timezone.utc)
        branch_ids = (
            frozenset({context.active_branch.id})
            if context.active_branch
            else context.authorized_branch_ids
        )
        scheduling = await self._scheduling(
            session, context.company.id, branch_ids, now
        )
        customers = await self._customers(session, context.company.id, branch_ids)
        luminary = await self._luminary(session, context.company.id, branch_ids)
        return self.reasoner.reason(
            scheduling=scheduling,
            customers=customers,
            luminary=luminary,
            evaluated_at=now,
        )

    @staticmethod
    async def _scheduling(
        session: AsyncSession,
        company_id: UUID,
        branch_ids: frozenset[UUID],
        now: datetime,
    ) -> tuple[SchedulingGapFact, ...]:
        rows = (
            await session.execute(
                select(
                    Branch.id,
                    Branch.name,
                    BranchSchedulingCalendar.id,
                    func.count(BranchSchedulingWeeklyInterval.id),
                )
                .outerjoin(
                    BranchSchedulingCalendar,
                    (BranchSchedulingCalendar.company_id == Branch.company_id)
                    & (BranchSchedulingCalendar.branch_id == Branch.id),
                )
                .outerjoin(
                    BranchSchedulingWeeklyInterval,
                    BranchSchedulingWeeklyInterval.calendar_id
                    == BranchSchedulingCalendar.id,
                )
                .where(Branch.company_id == company_id, Branch.id.in_(branch_ids))
                .group_by(Branch.id, Branch.name, BranchSchedulingCalendar.id)
                .having(func.count(BranchSchedulingWeeklyInterval.id) == 0)
                .order_by(Branch.name, Branch.id)
            )
        ).all()
        return tuple(
            SchedulingGapFact(row[0], row[1], row[2], int(row[3]), now) for row in rows
        )

    @staticmethod
    async def _customers(
        session: AsyncSession, company_id: UUID, branch_ids: frozenset[UUID]
    ) -> tuple[CustomerAdmissionGapFact, ...]:
        rows = tuple(
            (
                await session.scalars(
                    select(CustomerPopulationRefreshRun)
                    .where(
                        CustomerPopulationRefreshRun.company_id == company_id,
                        CustomerPopulationRefreshRun.branch_id.in_(branch_ids),
                    )
                    .order_by(
                        CustomerPopulationRefreshRun.branch_id,
                        CustomerPopulationRefreshRun.source_system,
                        CustomerPopulationRefreshRun.completed_at.desc(),
                        CustomerPopulationRefreshRun.id.desc(),
                    )
                    .distinct(
                        CustomerPopulationRefreshRun.branch_id,
                        CustomerPopulationRefreshRun.source_system,
                    )
                )
            ).all()
        )
        return tuple(
            CustomerAdmissionGapFact(
                row.id,
                row.branch_id,
                row.source_system,
                row.total_count,
                row.bound_count,
                row.held_count,
                row.ambiguous_count,
                row.unexplained_count,
                row.evidence_digest,
                row.completed_at,
            )
            for row in rows
            if row.held_count + row.ambiguous_count + row.unexplained_count > 0
        )

    @staticmethod
    async def _luminary(
        session: AsyncSession,
        company_id: UUID,
        branch_ids: frozenset[UUID],
    ) -> tuple[LuminaryFindingFact, ...]:
        successor = LuminaryFindingRecord.__table__.alias("accepted_successor")
        eligible_types = {
            "unprofitable_job",
            "period_change",
            "labor_cost_change",
            "material_cost_change",
            "missing_evidence",
            "allocation_policy",
            "source_readiness",
        }
        rows = tuple(
            (
                await session.scalars(
                    select(LuminaryFindingRecord)
                    .where(
                        LuminaryFindingRecord.company_id == company_id,
                        LuminaryFindingRecord.lifecycle == "accepted",
                        LuminaryFindingRecord.finding_type.in_(eligible_types),
                        or_(
                            LuminaryFindingRecord.branch_id.is_(None),
                            LuminaryFindingRecord.branch_id.in_(branch_ids),
                        ),
                        ~exists(
                            select(successor.c.id).where(
                                successor.c.company_id == company_id,
                                successor.c.lifecycle == "accepted",
                                successor.c.supersedes_finding_id
                                == LuminaryFindingRecord.id,
                            )
                        ),
                    )
                    .order_by(
                        LuminaryFindingRecord.generated_at.desc(),
                        LuminaryFindingRecord.id,
                    )
                    .limit(100)
                )
            ).all()
        )
        return tuple(
            LuminaryFindingFact(
                row.id,
                row.branch_id,
                row.finding_class,
                row.finding_type,
                row.title,
                row.summary,
                row.explanation,
                row.confidence_percent,
                row.completeness,
                row.freshness,
                tuple(row.limitations),
                tuple(row.investigate_next),
                row.finding_digest,
                row.period_start.isoformat(),
                row.period_end.isoformat(),
                row.generated_at,
            )
            for row in rows
        )


def recommendation_digest(items: tuple[ActiveOwnerRecommendation, ...]) -> str:
    return hashlib.sha256(
        json.dumps(
            [
                {
                    "id": str(item.recommendation_id),
                    "definition": item.definition_id,
                    "priority": item.priority_score,
                    "evidence": [e.digest for e in item.evidence],
                }
                for item in items
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


active_recommendation_service = ActiveRecommendationService()
