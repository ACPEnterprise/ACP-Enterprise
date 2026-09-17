from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict
from datetime import datetime, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.lia_context import customer_lia_context_service
from app.jobs.lia_context import job_lia_context_service
from app.platform.permissions.authorization import AuthorizationContext
from app.timekeeping.models import PayPeriod
from app.workforce.service import workforce_operations_service

from .contracts import (
    AnswerAuthority,
    EvidenceReference,
    LiaContext,
    LiaRequest,
    LiaResponse,
    LiaTemporalContext,
    NavigationSuggestion,
    TruthClassification,
)
from .conversation import (
    ActionRisk,
    CorrectionKind,
    ResponseMode,
    interpret_conversation,
)
from .owner_answers import compose_owner_answer
from .payroll_guidance import payroll_guidance_answer
from .planner import OWNER_BRIEFING_DOMAINS, QuestionIntent, plan_question
from .price_book_context import price_book_lia_context_service
from .record_resolution import resolve_canonical_reference
from .retrieval import GovernedRetrievalService, permitted_domain_names
from .security import (
    EXFILTRATION_PATTERNS,
    FABRICATION_PATTERNS,
    HIGH_IMPACT_PATTERNS,
    INJECTION_PATTERNS,
    matches_any,
)
from .temporal import resolve_temporal_context

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
    "communications": "/administration/communications",
    "accounting": "/financial-reports",
    "data-quality": "/data-quality",
    "launch-readiness": "/administration",
    "price-book": "/price-book",
    "audit": "/audit",
    "timekeeping": "/employees",
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
        resolved_temporal = resolve_temporal_context(
            question, timezone_name=getattr(context.company, "timezone", "UTC")
        )
        temporal = (
            LiaTemporalContext(**asdict(resolved_temporal))
            if resolved_temporal is not None
            else request.context.temporal
            if request.context is not None
            else None
        )
        if (
            resolved_temporal is not None
            and request.context is not None
            and request.context.temporal is not None
        ):
            assert temporal is not None
            temporal = temporal.model_copy(
                update={
                    "prior_start": request.context.temporal.start_date,
                    "prior_end": request.context.temporal.end_date,
                    "prior_label": request.context.temporal.period_label,
                }
            )
        elif (
            resolved_temporal is None
            and temporal is not None
            and temporal.prior_start is not None
            and re.search(
                r"\bcompare (?:them|those|the two)\b", question, re.IGNORECASE
            )
        ):
            temporal = temporal.model_copy(
                update={
                    "comparison_start": temporal.prior_start,
                    "comparison_end": temporal.prior_end,
                    "comparison_label": temporal.prior_label or "prior period",
                }
            )
        period_changed = bool(
            resolved_temporal is not None
            and request.context is not None
            and request.context.temporal is not None
            and (
                request.context.temporal.start_date != resolved_temporal.start_date
                or request.context.temporal.end_date != resolved_temporal.end_date
            )
        )
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
        if (
            request.context is not None
            and request.context.domain == "invoicing"
            and request.context.entity_id is not None
            and "payments" in selected
            and "invoicing" not in selected
        ):
            return self._response(
                context=context,
                request=request,
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.INCOMPLETE,
                answer=(
                    "ACP can retain the selected Invoice, but the current LIA evidence contract does not bind "
                    "that Invoice to authoritative payment application, settlement, or collected-cash evidence. "
                    "Open the Invoice to inspect its current authorized payment state."
                ),
                limitations=(
                    "Company-wide Payment records were not substituted for this Invoice.",
                    "Payment existence was not treated as settlement or collected cash.",
                ),
                navigation=(
                    NavigationSuggestion(
                        label="Open Invoice",
                        internal_path=f"/invoices/{request.context.entity_id}",
                    ),
                ),
            )
        if (
            temporal is None
            and "payroll" in selected
            and "pay period" in question.casefold()
        ):
            temporal = await _pay_period_temporal(
                session,
                context=context,
                question=question,
            )
            if temporal is None:
                return self._response(
                    context=context,
                    request=request,
                    request_id=request_id,
                    conversation_id=conversation_id,
                    classification=TruthClassification.INCOMPLETE,
                    answer=(
                        "ACP does not have an authoritative matching pay-period identity. "
                        "Current Payroll readiness was not substituted for historical state."
                    ),
                    limitations=("No Payroll calculation was performed.",),
                )
        unsupported_period_reason = _unsupported_period_semantics(
            question, selected, temporal
        )
        if unsupported_period_reason is not None:
            return self._response(
                context=context,
                request=request,
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.INCOMPLETE,
                answer=unsupported_period_reason,
                limitations=(
                    "Current state was not substituted for historical state.",
                    "No unsupported calculation was performed.",
                ),
            )
        effective_request = request
        entity_id = request.context.entity_id if request.context else None
        preloaded_evidence: tuple[EvidenceReference, ...] = ()
        if (
            plan.subject_query is not None
            and plan.subject_domain == "price-book"
            and "price-book" in selected
        ):
            price_lookup = await price_book_lia_context_service.resolve_exact(
                session,
                context=context,
                query=plan.subject_query,
            )
            if price_lookup.branch_required:
                return self._response(
                    context=context,
                    request=request,
                    request_id=request_id,
                    conversation_id=conversation_id,
                    classification=TruthClassification.INCOMPLETE,
                    answer="Select an authorized Branch before asking for a current Price Book price.",
                    limitations=(
                        "A Company-wide price was not substituted for Branch price authority.",
                    ),
                )
            if len(price_lookup.matches) != 1 or price_lookup.evidence is None:
                return self._response(
                    context=context,
                    request=request,
                    request_id=request_id,
                    conversation_id=conversation_id,
                    classification=(
                        TruthClassification.INCOMPLETE
                        if price_lookup.matches
                        else TruthClassification.UNAVAILABLE
                    ),
                    answer=(
                        "More than one authorized Price Book service matches that exact name or code. Open Price Book and select the intended service."
                        if price_lookup.matches
                        else "No active authorized Price Book service with that exact name or code is available in the selected Branch."
                    ),
                    limitations=(
                        "No fuzzy service identity or price was inferred.",
                    ),
                    navigation=(
                        NavigationSuggestion(
                            label="Open Price Book", internal_path="/price-book"
                        ),
                    ),
                )
            preloaded_evidence = (price_lookup.evidence,)
        elif plan.subject_query is not None and plan.subject_domain is not None:
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
            if "workforce" in selected and plan.subject_domain in {
                "identity",
                "workforce",
            }:
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
            if plan.subject_domain in {"estimates", "invoicing", "scheduling"}:
                subject_matches.extend(
                    (plan.subject_domain, match)
                    for match in await resolve_canonical_reference(
                        session,
                        context=context,
                        domain=plan.subject_domain,
                        reference=plan.subject_query,
                    )
                )
            if len(subject_matches) != 1:
                subject_label = {
                    "customers": "Customer",
                    "jobs": "Job",
                    "identity": "Customer or Employee",
                    "workforce": "Employee",
                    "price-book": "Price Book service",
                    "estimates": "Estimate",
                    "invoicing": "Invoice",
                    "scheduling": "Appointment",
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
            selected = (
                {
                    domain
                    for domain in selected
                    if domain in {"workforce", "payroll", "timekeeping", "dispatch"}
                }
                if resolved_domain == "workforce"
                else {
                    domain
                    for domain in selected
                    if domain in {"scheduling", "dispatch"}
                }
                if resolved_domain == "scheduling"
                else {resolved_domain}
            )
            selected.add(resolved_domain)
            effective_request = request.model_copy(
                update={
                    "context": LiaContext(
                        domain=resolved_domain,
                        entity_id=entity_id,
                        authorization_version=context.authorization_version,
                        topic_domains=tuple(sorted(selected)),
                        temporal=temporal,
                    )
                }
            )
        elif temporal is not None:
            effective_request = request.model_copy(
                update={
                    "context": LiaContext(
                        domain=request.context.domain if request.context else None,
                        entity_id=entity_id,
                        authorization_version=context.authorization_version,
                        evidence_digest=(
                            None if period_changed else request.context.evidence_digest
                        )
                        if request.context
                        else None,
                        topic_domains=tuple(sorted(selected)),
                        temporal=temporal,
                    )
                }
            )
        if plan.subject_query is None and selected:
            prior_context = request.context
            selected_domain = (
                next(iter(selected))
                if len(selected) == 1
                else prior_context.domain
                if prior_context is not None and prior_context.domain in selected
                else None
            )
            if selected_domain is not None:
                same_subject = bool(
                    prior_context is not None
                    and prior_context.domain == selected_domain
                )
                prior_entity_id = (
                    prior_context.entity_id
                    if prior_context is not None and same_subject
                    else None
                )
                prior_evidence_digest = (
                    prior_context.evidence_digest
                    if prior_context is not None
                    and same_subject
                    and not period_changed
                    else None
                )
                entity_id = prior_entity_id
                effective_request = request.model_copy(
                    update={
                        "context": LiaContext(
                            domain=selected_domain,
                            entity_id=entity_id,
                            authorization_version=context.authorization_version,
                            evidence_digest=prior_evidence_digest,
                            topic_domains=tuple(sorted(selected)),
                            temporal=temporal,
                        )
                    }
                )
        requested_basis = _requested_accounting_basis(question)
        if preloaded_evidence:
            evidence = preloaded_evidence
        elif temporal is None:
            evidence = await self.retrieval.retrieve(
                session,
                context=context,
                domains=selected,
                entity_id=entity_id,
                entity_domain=(
                    effective_request.context.domain
                    if effective_request.context is not None
                    else None
                ),
            )
        else:
            evidence = await self.retrieval.retrieve(
                session,
                context=context,
                domains=selected,
                entity_id=entity_id,
                entity_domain=(
                    effective_request.context.domain
                    if effective_request.context is not None
                    else None
                ),
                temporal=temporal,
                requested_accounting_basis=requested_basis,
            )
        if temporal is not None and temporal.comparison_start is not None:
            comparison = LiaTemporalContext(
                start_date=temporal.comparison_start,
                end_date=temporal.comparison_end or temporal.comparison_start,
                as_of=temporal.as_of,
                timezone=temporal.timezone,
                period_label=temporal.comparison_label or "comparison period",
            )
            evidence = (
                *evidence,
                *(
                    await self.retrieval.retrieve(
                        session,
                        context=context,
                        domains=selected,
                        entity_id=entity_id,
                        entity_domain=(
                            effective_request.context.domain
                            if effective_request.context is not None
                            else None
                        ),
                        temporal=comparison,
                        requested_accounting_basis=requested_basis,
                    )
                ),
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

        if "timekeeping" in selected and re.search(
            r"\bhow\s+many\s+hours\b|\bjobsite\s+hours\b", question.casefold()
        ):
            return self._response(
                context=context,
                request=effective_request,
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.INCOMPLETE,
                answer=(
                    "ACP found the authorized accepted timekeeping records for the requested Employee and period, "
                    "but the current LIA evidence contract does not provide an authoritative total-hours aggregate. "
                    "Open Time & Attendance to review the accepted intervals and total."
                ),
                evidence=evidence,
                limitations=(
                    "Accepted-record counts were not presented as worked or paid hours.",
                    "Scheduled duration was not substituted for accepted time.",
                ),
                navigation=(
                    NavigationSuggestion(
                        label="Open Time & Attendance", internal_path="/employees"
                    ),
                ),
            )

        evidence_digest = _evidence_digest(evidence)
        if (
            request.context is not None
            and request.context.evidence_digest is not None
            and not period_changed
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

        if temporal is not None and all(
            item.authority == "PERIOD_AUTHORITY_UNAVAILABLE" for item in evidence
        ):
            return self._response(
                context=context,
                request=effective_request,
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.INCOMPLETE,
                answer=_unavailable_period_answer(evidence, temporal),
                evidence=evidence,
                limitations=(
                    "Current-state evidence was not substituted for historical evidence.",
                    "No unsupported calculation was performed.",
                ),
            )
        interpreted = payroll_guidance_answer(question, evidence)
        owner_answer = compose_owner_answer(question, evidence)
        base_answer = interpreted or owner_answer.text
        if temporal is not None:
            base_answer = _period_answer(base_answer, evidence, temporal)
        answer = _compose_answer(
            lines=[base_answer],
            mode=plan.response_mode,
            authority=_answer_authority(TruthClassification.KNOWN, evidence),
            period=None,
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
            or (
                navigation[0].label
                if navigation
                else "Refresh authoritative ACP evidence"
            ),
            as_of=evidence_as_of,
            generated_at=datetime.now(timezone.utc),
            temporal=request.context.temporal if request.context else None,
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
    if item.entity_id is not None:
        entity_base = {
            "customers": "/customers",
            "jobs": "/jobs",
            "scheduling": "/appointments",
            "invoicing": "/invoices",
            "payments": "/payments",
        }.get(item.domain)
        if entity_base is not None:
            return f"{entity_base}/{item.entity_id}"
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
        first = _brief_text(lines[0]) if lines else "No result was returned."
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


def _brief_text(answer: str, *, limit: int = 320) -> str:
    """Keep the spoken/default brief answer useful without hiding evidence metadata."""
    normalized = " ".join(answer.split())
    if len(normalized) <= limit:
        return normalized
    boundary = normalized.rfind(" ", 0, limit - 1)
    if boundary < limit // 2:
        boundary = limit - 1
    return f"{normalized[:boundary].rstrip('.,;:')}…"


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


def _requested_accounting_basis(question: str) -> str | None:
    normalized = question.casefold()
    if "cash basis" in normalized or re.search(r"\bcash\b", normalized):
        return "cash"
    if "accrual" in normalized:
        return "accrual"
    return None


def _unsupported_period_semantics(
    question: str,
    domains: set[str],
    temporal: LiaTemporalContext | None,
) -> str | None:
    if temporal is None:
        return None
    normalized = question.casefold()
    if "invoicing" in domains and any(
        phrase in normalized
        for phrase in ("still open", "at month end", "were paid", "was paid")
    ):
        return (
            "ACP knows current Invoice state and can filter Invoice issue dates, but it "
            "does not have authoritative historical Invoice-state snapshots for that question."
        )
    if "dispatch" in domains and any(
        phrase in normalized for phrase in ("was active", "were active")
    ):
        return (
            "ACP has current Dispatch assignments and assignment windows, but not an "
            "authoritative historical active-state snapshot for that time."
        )
    if "scheduling" in domains and "needs scheduling" in normalized:
        return (
            "Unscheduled work has no authoritative Appointment date to place inside that "
            "period. ACP did not infer a requested date from current queue membership."
        )
    if "estimates" in domains and "expired" in normalized:
        return (
            "ACP has current Estimate status and creation dates, but no accepted historical "
            "expiration-transition filter for that period."
        )
    return None


async def _pay_period_temporal(
    session: AsyncSession,
    *,
    context: AuthorizationContext,
    question: str,
) -> LiaTemporalContext | None:
    timezone_name = getattr(context.company, "timezone", "UTC")
    today = datetime.now(ZoneInfo(timezone_name)).date()
    normalized = question.casefold()
    query = select(PayPeriod).where(PayPeriod.company_id == context.company.id)
    label = "current pay period"
    if "last pay period" in normalized:
        query = query.where(PayPeriod.period_end < today).order_by(
            PayPeriod.period_end.desc(), PayPeriod.id.desc()
        )
        label = "last pay period"
    else:
        query = query.where(
            PayPeriod.period_start <= today,
            PayPeriod.period_end >= today,
        ).order_by(PayPeriod.period_end.desc(), PayPeriod.id.desc())
    period = await session.scalar(query.limit(1))
    if period is None:
        return None
    return LiaTemporalContext(
        start_date=period.period_start,
        end_date=period.period_end,
        as_of=datetime.now(timezone.utc),
        timezone=timezone_name,
        period_label=label,
    )


def _period_answer(
    answer: str,
    evidence: tuple[EvidenceReference, ...],
    temporal: LiaTemporalContext,
) -> str:
    supported = tuple(
        item for item in evidence if item.authority != "PERIOD_AUTHORITY_UNAVAILABLE"
    )
    unavailable = tuple(
        item for item in evidence if item.authority == "PERIOD_AUTHORITY_UNAVAILABLE"
    )
    period = (
        f"{temporal.period_label} ({temporal.start_date.isoformat()} through "
        f"{temporal.end_date.isoformat()}, {temporal.timezone})"
    )
    suffix = ""
    if unavailable:
        suffix = (
            " Historical filtering is unavailable for: "
            + ", ".join(sorted({item.domain for item in unavailable}))
            + "."
        )
    prefix = f"For {period}, "
    if temporal.comparison_start is not None:
        comparison_end = temporal.comparison_end or temporal.comparison_start
        primary_evidence = tuple(
            item
            for item in supported
            if item.period_start == temporal.start_date
            and item.period_end == temporal.end_date
        )
        comparison_evidence = tuple(
            item
            for item in supported
            if item.period_start == temporal.comparison_start
            and item.period_end == comparison_end
        )
        if primary_evidence and comparison_evidence:
            return (
                f"Comparing {period} with {temporal.comparison_label} "
                f"({temporal.comparison_start.isoformat()} through "
                f"{comparison_end.isoformat()}), the authorized evidence reports "
                f"{temporal.period_label}: {_period_evidence_summary(primary_evidence)} "
                f"{temporal.comparison_label}: "
                f"{_period_evidence_summary(comparison_evidence)} "
                "LIA did not manufacture a difference, percentage, or causal explanation."
                + suffix
            )
        prefix = (
            f"Comparing {period} with {temporal.comparison_label} "
            f"({temporal.comparison_start.isoformat()} through "
            f"{comparison_end.isoformat()}), "
        )
    if not supported:
        return (
            prefix
            + "ACP does not have authoritative period-filtered evidence."
            + suffix
        )
    return prefix + answer[0].lower() + answer[1:] + suffix


def _period_evidence_summary(evidence: tuple[EvidenceReference, ...]) -> str:
    return "; ".join(
        f"{item.label} — {item.state or f'{item.count or 0} accepted records'}."
        for item in evidence
    )


def _unavailable_period_answer(
    evidence: tuple[EvidenceReference, ...], temporal: LiaTemporalContext
) -> str:
    domains = ", ".join(sorted({item.domain for item in evidence}))
    basis = next(
        (
            limitation.removeprefix("available_native_basis:")
            for item in evidence
            for limitation in item.limitations
            if limitation.startswith("available_native_basis:")
        ),
        None,
    )
    if basis is not None:
        return (
            f"ACP can produce a {basis}-basis native report for "
            f"{temporal.period_label}, but not the requested basis."
        )
    return (
        f"ACP does not have an authoritative historical filter for {domains} over "
        f"{temporal.period_label}. Current state was not presented as historical fact."
    )
