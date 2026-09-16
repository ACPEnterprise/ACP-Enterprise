from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.authorization import AuthorizationContext
from app.workforce.service import workforce_operations_service

from .contracts import (
    AnswerAuthority,
    EvidenceReference,
    LiaContext,
    LiaRequest,
    LiaResponse,
    NavigationSuggestion,
    TruthClassification,
)
from .conversation import (
    ActionRisk,
    CorrectionKind,
    ResponseMode,
    interpret_conversation,
)
from .planner import OWNER_BRIEFING_DOMAINS, QuestionIntent, plan_question
from .retrieval import GovernedRetrievalService, permitted_domain_names
from .security import (
    EXFILTRATION_PATTERNS,
    FABRICATION_PATTERNS,
    HIGH_IMPACT_PATTERNS,
    INJECTION_PATTERNS,
    matches_any,
)

logger = logging.getLogger("app.lia.audit")
POLICY_VERSION = "lia-governed-assistant/v1"

ASSOCIATION_QUESTION_PHRASES = (
    "also showing",
    "line up with",
    "driving",
    "causing",
    "because of",
    "contributing to",
)

ROUTES = {
    "luminary": "/luminary",
    "business-economics": "/business-economics",
    "beacon": "/mission-control",
    "migration": "/administration",
    "payroll": "/payroll",
    "customers": "/customers",
    "jobs": "/jobs",
    "scheduling": "/scheduling",
    "dispatch": "/dispatch",
    "locations": "/customers",
    "estimates": "/estimates",
    "invoicing": "/invoices",
    "payments": "/payments",
    "purchasing": "/purchasing",
    "inventory": "/inventory",
    "assets": "/assets",
    "workforce": "/employees",
    "communications": "/communications",
    "accounting": "/reports",
    "data-quality": "/data-quality",
    "launch-readiness": "/administration",
    "price-book": "/price-book",
    "audit": "/audit",
    "timekeeping": "/employees/time-attendance",
}


class LiaService:
    def __init__(self, retrieval: GovernedRetrievalService | None = None) -> None:
        self.retrieval = retrieval or GovernedRetrievalService()

    async def ask(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        request: LiaRequest,
    ) -> LiaResponse:
        request_id = uuid4()
        conversation_id = request.conversation_id or uuid4()
        question = request.question.strip()
        conversation = interpret_conversation(question)
        if (
            request.context is not None
            and request.context.authorization_version is not None
            and request.context.authorization_version != context.authorization_version
        ):
            return self._response(
                context=context,
                request=request,
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.STALE,
                answer="Your authorization changed since this context was captured. Refresh before asking about the record again.",
                limitations=("No stale context was retrieved.",),
            )
        if matches_any(question, INJECTION_PATTERNS + EXFILTRATION_PATTERNS):
            return self._response(
                context=context,
                request=request,
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.UNAUTHORIZED,
                answer="I can’t provide protected credentials, private instructions, or information outside your authorized scope.",
                limitations=(
                    "The request crossed ACP’s protected-information boundary.",
                ),
            )
        if matches_any(question, FABRICATION_PATTERNS):
            return self._response(
                context=context,
                request=request,
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.POLICY_REQUIRED,
                answer="I won’t turn an assumption into an ACP fact. I can explain a clearly labeled hypothetical, but authoritative status requires accepted evidence.",
                limitations=("No business fact was changed or inferred.",),
            )
        if conversation.capability_question:
            return self._response(
                context=context,
                request=request,
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.KNOWN,
                answer=_capability_answer(question),
                limitations=(
                    "LIA is read-only and cannot execute operational or financial changes.",
                    "Answers remain limited to the principal's current ACP permissions.",
                ),
                navigation=_capability_navigation(question),
            )
        if conversation.action is not None or matches_any(
            question, HIGH_IMPACT_PATTERNS
        ):
            action = conversation.action
            action_label = (
                action.action_type.replace("_", " ").lower()
                if action is not None
                else "requested business action"
            )
            risk = (
                action.risk.value.replace("_", " ").lower()
                if action is not None
                else "high impact operation"
            )
            return self._response(
                context=context,
                request=request,
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.POLICY_REQUIRED,
                answer=(
                    f"I understood this as {action_label} ({risk}). LIA is read-only "
                    "and did not execute it. Open the authoritative ACP workspace to "
                    "review the exact record, permission, and confirmation."
                ),
                limitations=(
                    "No action proposal was created: an exact target, authoritative evidence, current version, and required permission are mandatory.",
                    "A future proposal must satisfy LIA_PROPOSED_ACTION.v1 and remains non-executing.",
                ),
                navigation=_action_navigation(action.risk if action else None),
            )

        if conversation.correction is CorrectionKind.BACK:
            return self._response(
                context=context,
                request=request,
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.INCOMPLETE,
                answer=(
                    "I don't have an authorized earlier topic in this bounded request. "
                    "Name the Customer, Job, Employee, or period you want to return to."
                ),
                limitations=(
                    "LIA did not guess or restore stale conversation context.",
                ),
            )
        if conversation.pronouns and request.context is None:
            return self._response(
                context=context,
                request=request,
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.INCOMPLETE,
                answer=(
                    "I need the authorized record you mean before I can answer. Name or "
                    "select the Customer, Job, Employee, Invoice, Appointment, or alert."
                ),
                limitations=(
                    "No referent was guessed and no protected lookup occurred.",
                ),
            )

        plan = plan_question(
            question,
            request.context.domain if request.context else None,
            request.context.topic_domains if request.context else (),
        )
        requested_domains = set(plan.domains)
        if plan.intent is QuestionIntent.UNSUPPORTED:
            return self._response(
                context=context,
                request=request,
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.UNAVAILABLE,
                answer="I can’t identify a bounded authoritative ACP source for that question yet.",
                limitations=(
                    "Ask about a Customer, Job, schedule, Employee, Payroll, Accounting, Beacon, Economics, Migration, or launch readiness.",
                    "No broad database search or external AI provider was used.",
                ),
            )
        allowed = permitted_domain_names(context)
        selected = requested_domains & allowed
        if requested_domains == OWNER_BRIEFING_DOMAINS and not selected:
            # Briefings remain bounded to the principal's permitted source registry.
            selected = allowed
        if requested_domains and not selected:
            return self._response(
                context=context,
                request=request,
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.UNAUTHORIZED,
                answer="I can’t retrieve that domain with your current authorization.",
                limitations=("ACP does not reveal whether protected records exist.",),
            )
        effective_request = request
        entity_id = request.context.entity_id if request.context else None
        if plan.subject_query is not None:
            matches = await workforce_operations_service.resolve_display_name(
                session,
                context=context,
                display_name=plan.subject_query,
            )
            if len(matches) != 1:
                return self._response(
                    context=context,
                    request=request,
                    request_id=request_id,
                    conversation_id=conversation_id,
                    classification=(
                        TruthClassification.INCOMPLETE
                        if matches
                        else TruthClassification.UNAVAILABLE
                    ),
                    answer=(
                        "More than one authorized Employee has that exact name. Open Team and select the intended Employee."
                        if matches
                        else "No authorized Employee with that exact name is available in your current Company and Branch scope."
                    ),
                    limitations=(
                        "ACP does not reveal Employees outside the authorized scope.",
                    ),
                )
            entity_id = matches[0]
            effective_request = request.model_copy(
                update={
                    "context": LiaContext(
                        domain="workforce",
                        entity_id=entity_id,
                        authorization_version=context.authorization_version,
                    )
                }
            )
        evidence = await self.retrieval.retrieve(
            session,
            context=context,
            domains=selected,
            entity_id=entity_id,
        )
        if not evidence:
            return self._response(
                context=context,
                request=effective_request,
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.UNAVAILABLE,
                answer="No authorized authoritative evidence is available for this question.",
                limitations=(
                    "AI_PROVIDER_NOT_CONFIGURED",
                    "No eligible source adapter returned evidence.",
                ),
            )

        evidence_digest = _evidence_digest(evidence)
        if (
            request.context is not None
            and request.context.evidence_digest is not None
            and (
                not request.context.topic_domains
                or selected == set(request.context.topic_domains)
            )
            and request.context.evidence_digest != evidence_digest
        ):
            return self._response(
                context=context,
                request=effective_request,
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.STALE,
                answer="The authoritative evidence changed since the prior answer. Review the refreshed evidence before relying on the earlier context.",
                evidence=evidence,
                limitations=("Prior evidence was not silently reused.",),
            )
        if len(selected) > 1 and any(
            phrase in question.casefold() for phrase in ASSOCIATION_QUESTION_PHRASES
        ):
            response = self._response(
                context=context,
                request=effective_request,
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.INCOMPLETE,
                answer=(
                    "The authorized domains have evidence, but their safe summary adapters "
                    "do not prove the requested cross-domain relationship. Review the "
                    "digest-bound source results before treating co-occurrence as an association."
                ),
                evidence=evidence,
                limitations=(
                    "No causal claim was generated.",
                    "A shared subject, period, and admitted attribution contract are required for a supported association.",
                    "No external AI provider was invoked.",
                ),
                navigation=tuple(
                    NavigationSuggestion(
                        label=f"Open {item.label}",
                        internal_path=_evidence_route(item),
                    )
                    for item in evidence
                    if item.domain in ROUTES
                ),
            )
            return response

        lines = [f"{item.label}: {item.count} ({item.state})." for item in evidence]
        answer = _compose_answer(
            lines=lines,
            mode=plan.response_mode,
            authority=_answer_authority(TruthClassification.KNOWN, evidence),
            period=plan.resolved_period,
            evidence=evidence,
        )
        if any(
            word in question.casefold()
            for word in ("why", "profit", "margin", "economics")
        ):
            answer += " A causal explanation requires an admitted Business Economics result; these operational counts alone do not establish cause or profitability."
        limitations = (
            "This deterministic response summarizes current ACP records; no external AI provider was invoked.",
            "Counts are not a substitute for domain approval, settlement, posting, or payroll authority.",
        )
        navigation = tuple(
            NavigationSuggestion(
                label=f"Open {item.label}", internal_path=_evidence_route(item)
            )
            for item in evidence
            if item.domain in ROUTES
        )
        response = self._response(
            context=context,
            request=effective_request,
            request_id=request_id,
            conversation_id=conversation_id,
            classification=TruthClassification.KNOWN,
            answer=answer,
            evidence=evidence,
            limitations=limitations,
            navigation=navigation,
        )
        return response

    def _response(
        self,
        *,
        context: AuthorizationContext,
        request: LiaRequest,
        request_id: UUID,
        conversation_id: UUID,
        classification: TruthClassification,
        answer: str,
        evidence=(),
        limitations=(),
        navigation=(),
        proposals=(),
    ) -> LiaResponse:
        digest = _evidence_digest(evidence)
        evidence_as_of = max(
            (item.observed_at for item in evidence), default=datetime.now(timezone.utc)
        )
        branch_ids = tuple(
            sorted(
                {branch for item in evidence for branch in item.branch_ids}
                or set(context.authorized_branch_ids),
                key=str,
            )
        )
        missing = tuple(
            dict.fromkeys(
                limitation for item in evidence for limitation in item.limitations
            )
        )
        response = LiaResponse(
            request_id=request_id,
            conversation_id=conversation_id,
            classification=classification,
            authority=_answer_authority(classification, evidence),
            answer=answer,
            evidence=evidence,
            limitations=limitations,
            navigation=navigation,
            proposals=proposals,
            completeness="COMPLETE_FOR_AUTHORIZED_ADAPTERS"
            if evidence
            else "NO_EVIDENCE_USED",
            freshness="CURRENT_QUERY" if evidence else "NOT_APPLICABLE",
            provider="deterministic-acp",
            provider_version="v1",
            policy_version=POLICY_VERSION,
            evidence_digest=digest,
            authorization_version=context.authorization_version,
            company_id=context.company.id,
            branch_ids=branch_ids,
            subject_domain=request.context.domain if request.context else None,
            subject_id=request.context.entity_id if request.context else None,
            source_systems=tuple(sorted({item.domain for item in evidence})),
            missing_evidence=missing,
            safe_next_action=(
                navigation[0].label
                if navigation
                else "Refresh authoritative ACP evidence"
            ),
            as_of=evidence_as_of,
            generated_at=datetime.now(timezone.utc),
        )
        logger.info(
            "lia_request request_id=%s actor_id=%s company_id=%s branch_id=%s classification=%s domains=%s evidence_digest=%s",
            request_id,
            context.user.id,
            context.company.id,
            context.active_branch.id if context.active_branch else None,
            response.classification,
            ",".join(item.domain for item in response.evidence),
            response.evidence_digest,
        )
        return response


def _evidence_route(item: EvidenceReference) -> str:
    base = ROUTES[item.domain]
    if item.entity_id is not None and item.domain in {"customers", "jobs"}:
        return f"{base}/{item.entity_id}"
    return base


lia_service = LiaService()


def _evidence_digest(evidence: tuple[EvidenceReference, ...]) -> str:
    canonical = [item.evidence_digest for item in evidence]
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


def _answer_authority(
    classification: TruthClassification,
    evidence: tuple[EvidenceReference, ...],
) -> AnswerAuthority:
    if not evidence:
        return AnswerAuthority.INSUFFICIENT_EVIDENCE
    if classification in {
        TruthClassification.INCOMPLETE,
        TruthClassification.STALE,
        TruthClassification.CONFLICTING,
        TruthClassification.UNAVAILABLE,
    } or any(item.freshness == "NO_ACCEPTED_EVIDENCE" for item in evidence):
        return AnswerAuthority.PARTIAL
    if any(
        "MIGRATION" in item.authority or "SOURCE" in item.authority for item in evidence
    ):
        return AnswerAuthority.SOURCE_BACKED
    return AnswerAuthority.ACP_AUTHORITATIVE


def _compose_answer(
    *,
    lines: list[str],
    mode: ResponseMode,
    authority: AnswerAuthority,
    period,
    evidence: tuple[EvidenceReference, ...],
) -> str:
    authority_text = {
        AnswerAuthority.ACP_AUTHORITATIVE: "ACP's native authorized records show",
        AnswerAuthority.SOURCE_BACKED: "Authorized source evidence shows",
        AnswerAuthority.PARTIAL: "ACP has only part of the authorized evidence",
        AnswerAuthority.INSUFFICIENT_EVIDENCE: "ACP does not have enough authorized evidence",
    }[authority]
    period_text = ""
    if period is not None:
        period_text = (
            f" The requested period resolves to {period.starts_on.isoformat()} through "
            f"{period.ends_on.isoformat()}; the current source summaries are not "
            "date-filtered, so they must not be treated as period totals."
        )
    if mode is ResponseMode.BRIEF:
        first = lines[0] if lines else "No result was returned."
        return f"{authority_text}: {first}{period_text}"
    detail = " ".join(lines)
    answer = f"{authority_text}: {detail}{period_text}"
    if mode is ResponseMode.DETAILED:
        answer += " Open the authoritative workspace for record-level detail and the next permitted step."
    elif mode is ResponseMode.EVIDENCE:
        sources = ", ".join(sorted({item.authority for item in evidence}))
        as_of = max(item.observed_at for item in evidence).isoformat()
        answer += f" Evidence authority: {sources}. As of {as_of}."
    return answer


def _capability_answer(question: str) -> str:
    normalized = question.casefold()
    if any(
        term in normalized
        for term in ("schedule", "dispatch", "change prices", "run payroll")
    ):
        return (
            "I can explain authorized evidence and open the relevant ACP workspace, "
            "but I cannot schedule, dispatch, change prices, or run Payroll."
        )
    return (
        "I can read and explain authorized ACP evidence, preserve a bounded record "
        "context, show limitations, and suggest safe navigation. I cannot change "
        "business records, move money, send messages, or grant permissions."
    )


def _capability_navigation(question: str) -> tuple[NavigationSuggestion, ...]:
    normalized = question.casefold()
    for term, domain in (
        ("schedule", "scheduling"),
        ("dispatch", "dispatch"),
        ("price", "price-book"),
        ("payroll", "payroll"),
    ):
        if term in normalized:
            return (
                NavigationSuggestion(
                    label=f"Open {domain.replace('-', ' ').title()}",
                    internal_path=ROUTES[domain],
                ),
            )
    return ()


def _action_navigation(risk: ActionRisk | None) -> tuple[NavigationSuggestion, ...]:
    if risk is None:
        return ()
    domain = {
        ActionRisk.SCHEDULING_CHANGE: "scheduling",
        ActionRisk.CUSTOMER_COMMUNICATION: "communications",
        ActionRisk.PRICE_CHANGE: "price-book",
        ActionRisk.PAYROLL: "payroll",
        ActionRisk.ACCOUNTING: "accounting",
        ActionRisk.MONEY_MOVEMENT: "payments",
        ActionRisk.EMPLOYMENT: "workforce",
        ActionRisk.PERMISSION_CHANGE: "workforce",
        ActionRisk.LOW_IMPACT_OPERATION: "purchasing",
    }.get(risk)
    if domain is None:
        return ()
    return (
        NavigationSuggestion(
            label=f"Open {domain.replace('-', ' ').title()}",
            internal_path=ROUTES[domain],
        ),
    )
