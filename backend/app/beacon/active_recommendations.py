"""Read-only active owner recommendations from exact canonical evidence."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_migration.models import CustomerPopulationRefreshRun
from app.luminary.models import LuminaryFindingRecord
from app.marketing.provider_service import marketing_provider_service
from app.payroll.models import PayrollRunMemberRecord, PayrollRunRecord
from app.platform.branch.models import Branch
from app.platform.permissions.authorization import AuthorizationContext
from app.qbo_source.application_models import (
    QboNativeApplicationRecord,
    QboNativeReviewItem,
)
from app.scheduling.models import (
    BranchSchedulingCalendar,
    BranchSchedulingWeeklyInterval,
)

PriorityWindow = Literal["NOW", "TODAY", "THIS_WEEK", "WATCH"]
RecommendationKind = Literal["EVIDENCE_GAP", "MEASURED_FINDING"]
RecommendationResponsibility = Literal["OWNER", "ACCOUNTANT", "SYSTEM"]
ReadinessAdapterState = Literal["EVALUATED", "SOURCE_UNAVAILABLE", "ADAPTER_GATED"]


@dataclass(frozen=True, slots=True)
class RecommendationEvidence:
    entity_type: str
    entity_id: UUID
    digest: str | None
    as_of: datetime


@dataclass(frozen=True, slots=True)
class RecommendationPriorityFactor:
    factor: str
    available: bool
    contribution: int
    explanation: str


@dataclass(frozen=True, slots=True)
class RelatedRecommendation:
    recommendation_id: UUID
    title: str
    measured_fact: str
    interpretation: str
    evidence_digest: str | None


@dataclass(frozen=True, slots=True)
class ActiveOwnerRecommendation:
    recommendation_id: UUID
    definition_id: str
    definition_version: int
    root_issue_key: str
    kind: RecommendationKind
    title: str
    measured_fact: str
    interpretation: str
    recommended_human_action: str
    responsibility: RecommendationResponsibility
    source_authority: str
    evidence_as_of: datetime
    coverage: str
    confidence: str
    limitations: tuple[str, ...]
    affected_capabilities: tuple[str, ...]
    decisions_blocked: tuple[str, ...]
    priority_window: PriorityWindow
    priority_score: int
    priority_reason: str
    priority_factors: tuple[RecommendationPriorityFactor, ...]
    improves_if_resolved: str
    drilldown_path: str
    action_destination: str
    evidence: tuple[RecommendationEvidence, ...]
    related_recommendations: tuple[RelatedRecommendation, ...]
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ReadinessAdapterEvaluation:
    domain: str
    state: ReadinessAdapterState
    source_authority: str
    fact_count: int
    evaluated_at: datetime
    limitation: str | None


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
class PayrollReadinessGapFact:
    run_id: UUID
    pay_period_id: UUID
    blocked_employee_count: int
    total_employee_count: int
    blocker_counts: tuple[tuple[str, int], ...]
    run_digest: str
    assembled_at: datetime


@dataclass(frozen=True, slots=True)
class QboReadinessGapFact:
    company_id: UUID
    total_count: int
    applied_count: int
    bound_count: int
    quarantined_count: int
    open_review_count: int
    evidence_digest: str
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class MarketingReadinessGapFact:
    company_id: UUID
    connection_status: str
    bound_account_count: int
    live_ingestion_enabled: bool
    blockers: tuple[str, ...]
    evidence_digest: str
    observed_at: datetime


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
    finding_identity: str
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
        payroll: tuple[PayrollReadinessGapFact, ...] = (),
        qbo: tuple[QboReadinessGapFact, ...] = (),
        marketing: tuple[MarketingReadinessGapFact, ...] = (),
        luminary: tuple[LuminaryFindingFact, ...] = (),
        evaluated_at: datetime,
    ) -> tuple[ActiveOwnerRecommendation, ...]:
        values = [
            *(self._scheduling(item, evaluated_at) for item in scheduling),
            *(self._customers(item, evaluated_at) for item in customers),
            *(self._payroll(item, evaluated_at) for item in payroll),
            *(self._qbo(item, evaluated_at) for item in qbo),
            *(self._marketing(item, evaluated_at) for item in marketing),
            *(self._luminary(item, evaluated_at) for item in luminary),
        ]
        grouped = self._group(values)
        return tuple(
            sorted(
                grouped,
                key=lambda item: (
                    -item.priority_score,
                    item.evidence_as_of,
                    str(item.recommendation_id),
                ),
            )
        )

    @staticmethod
    def _group(
        values: list[ActiveOwnerRecommendation],
    ) -> tuple[ActiveOwnerRecommendation, ...]:
        groups: dict[str, list[ActiveOwnerRecommendation]] = {}
        for value in values:
            groups.setdefault(value.root_issue_key, []).append(value)
        result: list[ActiveOwnerRecommendation] = []
        for group in groups.values():
            primary = max(
                group,
                key=lambda item: (item.priority_score, item.evidence_as_of),
            )
            if len(group) == 1:
                result.append(primary)
                continue
            related = tuple(
                RelatedRecommendation(
                    item.recommendation_id,
                    item.title,
                    item.measured_fact,
                    item.interpretation,
                    item.evidence[0].digest if item.evidence else None,
                )
                for item in group
                if item.recommendation_id != primary.recommendation_id
            )
            breadth = min(10, (len(group) - 1) * 2)
            score = min(100, primary.priority_score + breadth)
            result.append(
                replace(
                    primary,
                    coverage=f"{primary.coverage} · {len(group)} related accepted findings",
                    limitations=tuple(
                        dict.fromkeys(
                            limitation
                            for item in group
                            for limitation in item.limitations
                        )
                    ),
                    affected_capabilities=tuple(
                        dict.fromkeys(
                            capability
                            for item in group
                            for capability in item.affected_capabilities
                        )
                    ),
                    decisions_blocked=tuple(
                        dict.fromkeys(
                            decision
                            for item in group
                            for decision in item.decisions_blocked
                        )
                    ),
                    priority_score=score,
                    priority_window=ActiveRecommendationReasoner._window(score),
                    priority_reason=(
                        f"{primary.priority_reason} {len(group)} accepted findings share "
                        "the same canonical root-condition key."
                    ),
                    priority_factors=(
                        *primary.priority_factors,
                        RecommendationPriorityFactor(
                            "root_condition_breadth",
                            True,
                            breadth,
                            f"{len(group)} accepted findings share this deterministic root key.",
                        ),
                    ),
                    evidence=tuple(
                        dict.fromkeys(
                            evidence for item in group for evidence in item.evidence
                        )
                    ),
                    related_recommendations=related,
                )
            )
        return tuple(result)

    @staticmethod
    def _window(score: int) -> PriorityWindow:
        if score >= 85:
            return "NOW"
        if score >= 60:
            return "TODAY"
        if score >= 30:
            return "THIS_WEEK"
        return "WATCH"

    @classmethod
    def _priority(
        cls,
        *,
        operational_blocker: bool,
        economic_materiality: bool,
        decisions_blocked: tuple[str, ...],
        owner_action_required: bool,
        explicit_urgency: PriorityWindow | None,
        evidence_quality: str,
    ) -> tuple[int, PriorityWindow, tuple[RecommendationPriorityFactor, ...]]:
        urgency_points = {"NOW": 15, "TODAY": 10, "THIS_WEEK": 5, "WATCH": 0}
        factors = (
            RecommendationPriorityFactor(
                "operational_blocker",
                True,
                30 if operational_blocker else 0,
                "Canonical evidence proves an operating capability is blocked."
                if operational_blocker
                else "No current operating block is asserted.",
            ),
            RecommendationPriorityFactor(
                "economic_materiality",
                economic_materiality,
                15 if economic_materiality else 0,
                "An accepted Luminary economic finding supports management review."
                if economic_materiality
                else "No authoritative economic-materiality classification is available for priority scoring.",
            ),
            RecommendationPriorityFactor(
                "decisions_blocked",
                bool(decisions_blocked),
                min(20, len(decisions_blocked) * 10),
                f"{len(decisions_blocked)} explicitly identified decision areas are blocked."
                if decisions_blocked
                else "No blocked management decision is asserted.",
            ),
            RecommendationPriorityFactor(
                "owner_action_required",
                owner_action_required,
                15 if owner_action_required else 0,
                "A normal owner or office workflow can advance this condition."
                if owner_action_required
                else "No direct owner action is established.",
            ),
            RecommendationPriorityFactor(
                "age_or_urgency",
                explicit_urgency is not None,
                urgency_points.get(explicit_urgency or "WATCH", 0),
                f"Canonical domain semantics support {explicit_urgency or 'no'} urgency."
                if explicit_urgency
                else "No deadline or urgency is inferred from record age alone.",
            ),
            RecommendationPriorityFactor(
                "evidence_quality",
                True,
                5,
                f"Canonical evidence quality is {evidence_quality}; the state is shown without invented confidence.",
            ),
            RecommendationPriorityFactor(
                "reversibility_and_risk",
                True,
                0,
                "The recommendation is human review or configuration; Beacon performs no mutation.",
            ),
        )
        score = sum(item.contribution for item in factors)
        return score, cls._window(score), factors

    def _scheduling(
        self, fact: SchedulingGapFact, evaluated_at: datetime
    ) -> ActiveOwnerRecommendation:
        missing = (
            "no Branch scheduling calendar exists"
            if fact.calendar_id is None
            else "the Branch calendar has no operating-hour intervals"
        )
        blocked = ("Scheduling capacity", "Dispatch assignment readiness")
        score, window, factors = self._priority(
            operational_blocker=True,
            economic_materiality=False,
            decisions_blocked=blocked,
            owner_action_required=True,
            explicit_urgency="TODAY",
            evidence_quality="complete configuration evidence",
        )
        return self._build(
            definition_id="evidence_gap.branch_scheduling_policy",
            root_issue_key=f"branch-scheduling:{fact.branch_id}",
            kind="EVIDENCE_GAP",
            subject=fact.branch_id,
            title=f"{fact.branch_name} scheduling policy is incomplete",
            measured_fact=f"{fact.branch_name}: {missing}.",
            interpretation=(
                "Scheduling and Dispatch cannot reliably evaluate bookable capacity "
                "for this Branch."
            ),
            action="Configure and review the Branch scheduling calendar.",
            responsibility="OWNER",
            source="Scheduling Branch calendar authority",
            as_of=fact.observed_at,
            coverage="One authorized Branch",
            confidence="HIGH",
            limitations=(
                "This is a configuration-readiness finding, not evidence of poor employee performance.",
            ),
            affected_capabilities=("Scheduling", "Dispatch"),
            decisions_blocked=blocked,
            window=window,
            score=score,
            priority_factors=factors,
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
        blocked = ("Customer history coverage", "Customer attribution coverage")
        score, window, factors = self._priority(
            operational_blocker=False,
            economic_materiality=False,
            decisions_blocked=blocked,
            owner_action_required=True,
            explicit_urgency=None,
            evidence_quality="incomplete admitted population",
        )
        return self._build(
            definition_id="evidence_gap.customer_population_admission",
            root_issue_key=(
                f"customer-admission:{fact.branch_id}:{fact.source_system}"
            ),
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
            responsibility="SYSTEM",
            source="Customer population reconciliation authority",
            as_of=fact.completed_at,
            coverage=f"Latest Branch population run · {fact.total_count} source records",
            confidence="HIGH",
            limitations=(
                "Beacon does not infer Customer identity or perform fuzzy matching.",
                "This recommendation does not authorize source admission.",
            ),
            affected_capabilities=(
                "Customer history",
                "Customer lifetime analysis",
                "Attribution analysis",
            ),
            decisions_blocked=blocked,
            window=window,
            score=score,
            priority_factors=factors,
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

    def _payroll(
        self, fact: PayrollReadinessGapFact, evaluated_at: datetime
    ) -> ActiveOwnerRecommendation:
        blocked = ("First real Payroll readiness", "Accepted Payroll calculation")
        score, window, factors = self._priority(
            operational_blocker=True,
            economic_materiality=False,
            decisions_blocked=blocked,
            owner_action_required=True,
            explicit_urgency="TODAY",
            evidence_quality="canonical Payroll run-member readiness",
        )
        blocker_summary = ", ".join(
            f"{code}: {count}" for code, count in fact.blocker_counts[:5]
        )
        return self._build(
            definition_id="evidence_gap.payroll_run_readiness",
            root_issue_key=f"payroll-readiness:{fact.run_id}",
            kind="EVIDENCE_GAP",
            subject=fact.run_id,
            title="Payroll readiness evidence is incomplete",
            measured_fact=(
                f"{fact.blocked_employee_count} of {fact.total_employee_count} Employees "
                f"in the latest Payroll run are blocked. Aggregate blocker evidence: "
                f"{blocker_summary or 'blocker details unavailable'}."
            ),
            interpretation=(
                "The current Payroll run cannot proceed through its accepted calculation "
                "and review workflow until Payroll authority resolves these blockers."
            ),
            action="Review the first real Payroll readiness blockers.",
            responsibility="ACCOUNTANT",
            source="Payroll run-member readiness authority",
            as_of=fact.assembled_at,
            coverage=f"Latest Payroll run · {fact.total_employee_count} Employees",
            confidence="HIGH",
            limitations=(
                "Beacon exposes aggregate blocker codes only; compensation and tax values remain protected.",
                "Beacon does not calculate, approve, or execute Payroll.",
            ),
            affected_capabilities=("Payroll", "Economic Health", "Labor burden"),
            decisions_blocked=blocked,
            window=window,
            score=score,
            priority_factors=factors,
            reason=(
                "Canonical Payroll admission evidence proves an operating blocker; no "
                "employee performance conclusion or dollar impact is inferred."
            ),
            improves="Payroll calculation readiness and downstream labor evidence become reviewable.",
            path="/payroll#first-real-payroll-readiness",
            destination="Payroll → First real Payroll readiness",
            evidence=(
                RecommendationEvidence(
                    "payroll_run", fact.run_id, fact.run_digest, fact.assembled_at
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
        blocked = (
            ("Economic interpretation", "Owner economic decision")
            if evidence_gap
            else ("Management investigation",)
        )
        score, window, factors = self._priority(
            operational_blocker=False,
            economic_materiality=False,
            decisions_blocked=blocked,
            owner_action_required=True,
            explicit_urgency=(
                "TODAY" if fact.finding_class == "conflicting_evidence" else None
            ),
            evidence_quality=(
                f"{fact.completeness}/{fact.freshness}/{fact.finding_class}"
            ),
        )
        action = (
            fact.investigate_next[0]
            if fact.investigate_next
            else "Review the accepted Luminary finding and its supporting evidence."
        )
        return self._build(
            definition_id=f"luminary.{fact.finding_type}",
            root_issue_key=(f"luminary:{fact.finding_type}:{fact.finding_identity}"),
            kind="EVIDENCE_GAP" if evidence_gap else "MEASURED_FINDING",
            subject=fact.finding_id,
            title=fact.title,
            measured_fact=fact.summary,
            interpretation=fact.explanation,
            action=action,
            responsibility="OWNER",
            source="Accepted Luminary finding",
            as_of=fact.generated_at,
            coverage=f"{fact.period_start} through {fact.period_end}",
            confidence=f"{fact.confidence_percent}% (Luminary canonical confidence)",
            limitations=fact.limitations,
            affected_capabilities=(
                ("Luminary", "Economic Health", "Management reporting")
                if evidence_gap
                else ("Luminary", "Management investigation")
            ),
            decisions_blocked=blocked,
            window=window,
            score=score,
            priority_factors=factors,
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

    def _qbo(
        self, fact: QboReadinessGapFact, evaluated_at: datetime
    ) -> ActiveOwnerRecommendation:
        blocked = ("QBO Accounting admission", "Authoritative financial reporting")
        score, window, factors = self._priority(
            operational_blocker=True,
            economic_materiality=False,
            decisions_blocked=blocked,
            owner_action_required=True,
            explicit_urgency="THIS_WEEK",
            evidence_quality="canonical QBO application dispositions",
        )
        return self._build(
            definition_id="evidence_gap.qbo_accounting_admission",
            root_issue_key=f"qbo-accounting-admission:{fact.company_id}",
            kind="EVIDENCE_GAP",
            subject=fact.company_id,
            title="QBO Accounting admission needs review",
            measured_fact=(
                f"The current QBO application population contains {fact.total_count} "
                f"records: {fact.applied_count} applied, {fact.bound_count} bound, "
                f"{fact.quarantined_count} quarantined, and {fact.open_review_count} "
                "open review items."
            ),
            interpretation=(
                "Unresolved QBO dispositions limit the Accounting evidence available "
                "to downstream reporting and management decisions."
            ),
            action="Review the canonical QuickBooks Migration queue.",
            responsibility="ACCOUNTANT",
            source="QBO native application and review authority",
            as_of=fact.observed_at,
            coverage=f"{fact.total_count} current QBO application records",
            confidence="HIGH",
            limitations=(
                "Source-backed QBO evidence is not ACP Accounting truth.",
                "Beacon does not inspect provider payloads or resolve review items.",
            ),
            affected_capabilities=(
                "Accounting reporting",
                "Economic Health",
                "Management reporting",
            ),
            decisions_blocked=blocked,
            window=window,
            score=score,
            priority_factors=factors,
            reason=(
                "Canonical review evidence proves an Accounting admission blocker; "
                "no financial impact is inferred."
            ),
            improves="Accepted Accounting evidence becomes available to authorized reporting.",
            path="/accounting/quickbooks-migration",
            destination="Accounting → QuickBooks Migration / Review Queue",
            evidence=(
                RecommendationEvidence(
                    "qbo_native_application_population",
                    fact.company_id,
                    fact.evidence_digest,
                    fact.observed_at,
                ),
            ),
            evaluated_at=evaluated_at,
        )

    def _marketing(
        self, fact: MarketingReadinessGapFact, evaluated_at: datetime
    ) -> ActiveOwnerRecommendation:
        blocked = ("Google Ads evidence acquisition", "Marketing attribution coverage")
        score, window, factors = self._priority(
            operational_blocker=False,
            economic_materiality=False,
            decisions_blocked=blocked,
            owner_action_required=True,
            explicit_urgency=None,
            evidence_quality="canonical Marketing provider readiness",
        )
        return self._build(
            definition_id="evidence_gap.marketing_google_ads_readiness",
            root_issue_key=f"marketing-google-ads:{fact.company_id}",
            kind="EVIDENCE_GAP",
            subject=fact.company_id,
            title="Google Ads evidence is not operationally ready",
            measured_fact=(
                f"Google Ads connection status is {fact.connection_status}; "
                f"{fact.bound_account_count} accounts are bound and live ingestion is "
                f"{'enabled' if fact.live_ingestion_enabled else 'disabled'}."
            ),
            interpretation=(
                "Marketing spend and attribution coverage cannot be treated as current "
                "operating evidence until the accepted readiness blockers are cleared."
            ),
            action="Review the Google Ads connection workspace.",
            responsibility="OWNER",
            source="Marketing Google Ads connection readiness authority",
            as_of=fact.observed_at,
            coverage="Company Google Ads provider readiness",
            confidence="HIGH",
            limitations=tuple(
                f"Readiness blocker: {blocker}." for blocker in fact.blockers
            )
            or ("No blocker detail was exposed by Marketing authority.",),
            affected_capabilities=("Marketing evidence", "Attribution analysis"),
            decisions_blocked=blocked,
            window=window,
            score=score,
            priority_factors=factors,
            reason=(
                "Canonical provider readiness limits Marketing evidence; no campaign "
                "performance or economic impact is inferred."
            ),
            improves="Authorized Google Ads evidence can support Marketing reporting.",
            path="/marketing/provider-connections",
            destination="Marketing → Provider Connections",
            evidence=(
                RecommendationEvidence(
                    "marketing_google_ads_readiness",
                    fact.company_id,
                    fact.evidence_digest,
                    fact.observed_at,
                ),
            ),
            evaluated_at=evaluated_at,
        )

    @staticmethod
    def _build(
        *,
        definition_id: str,
        root_issue_key: str,
        kind: RecommendationKind,
        subject: UUID,
        title: str,
        measured_fact: str,
        interpretation: str,
        action: str,
        responsibility: RecommendationResponsibility,
        source: str,
        as_of: datetime,
        coverage: str,
        confidence: str,
        limitations: tuple[str, ...],
        affected_capabilities: tuple[str, ...],
        decisions_blocked: tuple[str, ...],
        window: PriorityWindow,
        score: int,
        priority_factors: tuple[RecommendationPriorityFactor, ...],
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
            root_issue_key=root_issue_key,
            kind=kind,
            title=title,
            measured_fact=measured_fact,
            interpretation=interpretation,
            recommended_human_action=action,
            responsibility=responsibility,
            source_authority=source,
            evidence_as_of=as_of,
            coverage=coverage,
            confidence=confidence,
            limitations=limitations,
            affected_capabilities=affected_capabilities,
            decisions_blocked=decisions_blocked,
            priority_window=window,
            priority_score=score,
            priority_reason=reason,
            priority_factors=priority_factors,
            improves_if_resolved=improves,
            drilldown_path=path,
            action_destination=destination,
            evidence=evidence,
            related_recommendations=(),
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
        payroll = await self._payroll(session, context.company.id)
        qbo = await self._qbo(session, context.company.id, now)
        marketing = await self._marketing(session, context, now)
        luminary = await self._luminary(session, context.company.id, branch_ids)
        return self.reasoner.reason(
            scheduling=scheduling,
            customers=customers,
            payroll=payroll,
            qbo=qbo,
            marketing=marketing,
            luminary=luminary,
            evaluated_at=now,
        )

    async def adapter_evaluations(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        evaluated_at: datetime,
    ) -> tuple[ReadinessAdapterEvaluation, ...]:
        branch_ids = (
            frozenset({context.active_branch.id})
            if context.active_branch
            else context.authorized_branch_ids
        )
        scheduling = await self._scheduling(
            session, context.company.id, branch_ids, evaluated_at
        )
        customers = await self._customers(session, context.company.id, branch_ids)
        payroll = await self._payroll(session, context.company.id)
        qbo = await self._qbo(session, context.company.id, evaluated_at)
        marketing = await self._marketing(session, context, evaluated_at)
        payroll_source_available = bool(
            await session.scalar(
                select(
                    exists().where(PayrollRunRecord.company_id == context.company.id)
                )
            )
        )
        return (
            ReadinessAdapterEvaluation(
                "CUSTOMERS",
                "EVALUATED",
                "Customer population reconciliation authority",
                len(customers),
                evaluated_at,
                None,
            ),
            ReadinessAdapterEvaluation(
                "PAYROLL",
                "EVALUATED" if payroll_source_available else "SOURCE_UNAVAILABLE",
                "Payroll run-member readiness authority",
                len(payroll),
                evaluated_at,
                None
                if payroll_source_available
                else "No canonical Payroll run-member population is available for direct evaluation.",
            ),
            ReadinessAdapterEvaluation(
                "QBO_ACCOUNTING",
                "EVALUATED",
                "QBO native application and review authority",
                len(qbo),
                evaluated_at,
                None,
            ),
            ReadinessAdapterEvaluation(
                "SCHEDULING_DISPATCH",
                "EVALUATED",
                "Scheduling Branch calendar authority",
                len(scheduling),
                evaluated_at,
                None,
            ),
            ReadinessAdapterEvaluation(
                "MARKETING",
                "EVALUATED",
                "Marketing Google Ads connection readiness authority",
                len(marketing),
                evaluated_at,
                None,
            ),
        )

    @staticmethod
    async def _qbo(
        session: AsyncSession, company_id: UUID, observed_at: datetime
    ) -> tuple[QboReadinessGapFact, ...]:
        rows = (
            await session.execute(
                select(
                    QboNativeApplicationRecord.disposition,
                    func.count(),
                    func.max(QboNativeApplicationRecord.applied_at),
                )
                .where(
                    QboNativeApplicationRecord.company_id == company_id,
                    QboNativeApplicationRecord.superseded_at.is_(None),
                )
                .group_by(QboNativeApplicationRecord.disposition)
            )
        ).all()
        counts = Counter({str(row[0]): int(row[1]) for row in rows})
        total = sum(counts.values())
        open_reviews = int(
            await session.scalar(
                select(func.count(QboNativeReviewItem.id)).where(
                    QboNativeReviewItem.company_id == company_id,
                    QboNativeReviewItem.state == "OPEN",
                )
            )
            or 0
        )
        unresolved = counts["QUARANTINED"] + open_reviews
        if total == 0 or unresolved == 0:
            return ()
        evidence = {
            "total": total,
            "applied": counts["APPLIED"],
            "bound": counts["BOUND"],
            "quarantined": counts["QUARANTINED"],
            "open_review": open_reviews,
        }
        digest = hashlib.sha256(
            json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        latest = max(
            (row[2] for row in rows if row[2] is not None), default=observed_at
        )
        return (
            QboReadinessGapFact(
                company_id,
                total,
                counts["APPLIED"],
                counts["BOUND"],
                counts["QUARANTINED"],
                open_reviews,
                digest,
                latest,
            ),
        )

    @staticmethod
    async def _marketing(
        session: AsyncSession,
        context: AuthorizationContext,
        observed_at: datetime,
    ) -> tuple[MarketingReadinessGapFact, ...]:
        readiness = await marketing_provider_service.google_ads_connection_readiness(
            session, context=context
        )
        ready = (
            readiness.connection_status == "connected"
            and readiness.bound_account_count > 0
            and readiness.live_ingestion_enabled
            and not readiness.blockers
        )
        if ready:
            return ()
        evidence = {
            "connection_status": readiness.connection_status,
            "bound_account_count": readiness.bound_account_count,
            "live_ingestion_enabled": readiness.live_ingestion_enabled,
            "blockers": readiness.blockers,
        }
        digest = hashlib.sha256(
            json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return (
            MarketingReadinessGapFact(
                context.company.id,
                readiness.connection_status,
                readiness.bound_account_count,
                readiness.live_ingestion_enabled,
                readiness.blockers,
                digest,
                observed_at,
            ),
        )

    @staticmethod
    async def _payroll(
        session: AsyncSession, company_id: UUID
    ) -> tuple[PayrollReadinessGapFact, ...]:
        run = await session.scalar(
            select(PayrollRunRecord)
            .where(
                PayrollRunRecord.company_id == company_id,
                PayrollRunRecord.lifecycle.in_(
                    ("assembled", "under_review", "reviewed", "approved")
                ),
            )
            .order_by(PayrollRunRecord.assembled_at.desc(), PayrollRunRecord.id.desc())
            .limit(1)
        )
        if run is None:
            return ()
        members = tuple(
            (
                await session.scalars(
                    select(PayrollRunMemberRecord)
                    .where(
                        PayrollRunMemberRecord.company_id == company_id,
                        PayrollRunMemberRecord.run_id == run.id,
                    )
                    .order_by(PayrollRunMemberRecord.employee_id)
                )
            ).all()
        )
        blocked_members = tuple(
            item for item in members if item.disposition == "blocked"
        )
        if not blocked_members:
            return ()
        counts = Counter(
            code for item in blocked_members for code in tuple(item.blocker_codes)
        )
        return (
            PayrollReadinessGapFact(
                run.id,
                run.pay_period_id,
                len(blocked_members),
                len(members),
                tuple(sorted(counts.items())),
                run.run_digest,
                run.assembled_at,
            ),
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
                row.finding_identity,
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
