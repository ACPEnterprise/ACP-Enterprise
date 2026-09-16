from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.lia_context import customer_lia_context_service
from app.jobs.lia_context import job_lia_context_service
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
from .owner_answers import compose_owner_answer
from .payroll_guidance import payroll_guidance_answer
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
        if matches_any(question, HIGH_IMPACT_PATTERNS):
            return self._response(
                context=context,
                request=request,
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.POLICY_REQUIRED,
                answer="LIA cannot execute that business action. Review it in the authoritative ACP workflow with the required permission and confirmation.",
                limitations=(
                    "No action proposal was created: an exact target, authoritative evidence, current version, and required permission are mandatory.",
                    "A future proposal must satisfy LIA_PROPOSED_ACTION.v1 and remains non-executing.",
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
        if plan.subject_query is not None and plan.subject_domain is not None:
            subject_matches: list[tuple[str, UUID]] = []
            if "customers" in selected and plan.subject_domain in {
                "customers",
                "identity",
            }:
                subject_matches.extend(
                    ("customers", match)
                    for match in await customer_lia_context_service.resolve_display_name(
                        session,
                        context=context,
                        display_name=plan.subject_query,
                    )
                )
            if "workforce" in selected and plan.subject_domain == "identity":
                subject_matches.extend(
                    ("workforce", match)
                    for match in await workforce_operations_service.resolve_display_name(
                        session,
                        context=context,
                        display_name=plan.subject_query,
                    )
                )
            if "jobs" in selected and plan.subject_domain == "jobs":
                subject_matches.extend(
                    ("jobs", match)
                    for match in await job_lia_context_service.resolve_job_number(
                        session,
                        context=context,
                        job_number=plan.subject_query,
                    )
                )
            if len(subject_matches) != 1:
                subject_label = {
                    "customers": "Customer",
                    "jobs": "Job",
                    "identity": "Customer or Employee",
                }[plan.subject_domain]
                return self._response(
                    context=context,
                    request=request,
                    request_id=request_id,
                    conversation_id=conversation_id,
                    classification=(
                        TruthClassification.INCOMPLETE
                        if subject_matches
                        else TruthClassification.UNAVAILABLE
                    ),
                    answer=(
                        f"More than one authorized {subject_label} matches exactly. Open the authoritative workspace and select the intended record."
                        if subject_matches
                        else f"No authorized {subject_label} with that exact identity is available in your current Company and Branch scope."
                    ),
                    limitations=(
                        "ACP does not reveal records outside the authorized scope.",
                    ),
                )
            resolved_domain, entity_id = subject_matches[0]
            selected = {resolved_domain}
            effective_request = request.model_copy(
                update={
                    "context": LiaContext(
                        domain=resolved_domain,
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

        interpreted = payroll_guidance_answer(question, evidence)
        owner_answer = compose_owner_answer(question, evidence)
        answer = interpreted or owner_answer.text
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
            safe_next_action=owner_answer.next_action,
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
        safe_next_action: str | None = None,
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
            safe_next_action=safe_next_action
            or (navigation[0].label if navigation else "Refresh authoritative ACP evidence"),
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
