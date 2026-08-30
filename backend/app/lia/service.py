from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.authorization import AuthorizationContext

from .contracts import (
    LiaRequest,
    LiaResponse,
    NavigationSuggestion,
    TruthClassification,
)
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

DOMAIN_KEYWORDS = {
    "customers": ("customer",),
    "jobs": ("job", "work"),
    "scheduling": ("schedule", "appointment", "dispatch"),
    "estimates": ("estimate", "proposal"),
    "invoicing": ("invoice", "outstanding", "revenue"),
    "payments": ("payment", "settlement", "cash"),
    "purchasing": ("purchasing", "purchase order", "vendor"),
    "inventory": ("inventory", "stock", "material"),
    "business-economics": (
        "profit",
        "margin",
        "economics",
        "labor cost",
        "material cost",
    ),
    "beacon": ("beacon", "signal"),
    "migration": ("migration", "cutover"),
    "payroll": ("payroll", "pay statement", "pay statement", "remittance"),
    "luminary": (
        "luminary",
        "finding",
        "briefing",
        "how are we doing",
        "what changed",
        "why did",
    ),
}

ENTERPRISE_SUMMARY_PHRASES = (
    "how are we doing",
    "what needs my attention",
    "what changed",
    "what don't you know",
    "what information is incomplete",
    "owner briefing",
)

ROUTES = {
    "luminary": "/luminary",
    "customers": "/customers",
    "jobs": "/jobs",
    "scheduling": "/scheduling",
    "estimates": "/estimates",
    "invoicing": "/invoices",
    "payments": "/payments",
    "purchasing": "/purchasing",
    "inventory": "/inventory",
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
        if matches_any(question, INJECTION_PATTERNS + EXFILTRATION_PATTERNS):
            return self._response(
                context=context,
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
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.POLICY_REQUIRED,
                answer="I won’t turn an assumption into an ACP fact. I can explain a clearly labeled hypothetical, but authoritative status requires accepted evidence.",
                limitations=("No business fact was changed or inferred.",),
            )
        if matches_any(question, HIGH_IMPACT_PATTERNS):
            return self._response(
                context=context,
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.POLICY_REQUIRED,
                answer="LIA cannot execute that business action. Review it in the authoritative ACP workflow with the required permission and confirmation.",
                limitations=(
                    "No action proposal was created: an exact target, authoritative evidence, current version, and required permission are mandatory.",
                    "A future proposal must satisfy LIA_PROPOSED_ACTION.v1 and remains non-executing.",
                ),
            )

        requested_domains = self._classify_domains(question, request)
        allowed = permitted_domain_names(context)
        selected = requested_domains & allowed if requested_domains else allowed
        if requested_domains and not selected:
            return self._response(
                context=context,
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.UNAUTHORIZED,
                answer="I can’t retrieve that domain with your current authorization.",
                limitations=("ACP does not reveal whether protected records exist.",),
            )
        evidence = await self.retrieval.retrieve(
            session,
            context=context,
            domains=selected,
            entity_id=request.context.entity_id if request.context else None,
        )
        if not evidence:
            return self._response(
                context=context,
                request_id=request_id,
                conversation_id=conversation_id,
                classification=TruthClassification.UNAVAILABLE,
                answer="No authorized authoritative evidence is available for this question.",
                limitations=(
                    "AI_PROVIDER_NOT_CONFIGURED",
                    "No eligible source adapter returned evidence.",
                ),
            )

        lines = [f"{item.label}: {item.count} ({item.state})." for item in evidence]
        answer = "Here is the current authorized ACP evidence: " + " ".join(lines)
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
                label=f"Open {item.label}", internal_path=ROUTES[item.domain]
            )
            for item in evidence
            if item.domain in ROUTES
        )
        response = self._response(
            context=context,
            request_id=request_id,
            conversation_id=conversation_id,
            classification=TruthClassification.KNOWN,
            answer=answer,
            evidence=evidence,
            limitations=limitations,
            navigation=navigation,
        )
        return response

    def _classify_domains(self, question: str, request: LiaRequest) -> set[str]:
        if request.context and request.context.domain:
            return {request.context.domain}
        normalized = question.casefold()
        if any(phrase in normalized for phrase in ENTERPRISE_SUMMARY_PHRASES):
            return set()
        return {
            domain
            for domain, keywords in DOMAIN_KEYWORDS.items()
            if any(keyword in normalized for keyword in keywords)
        }

    def _response(
        self,
        *,
        context: AuthorizationContext,
        request_id: UUID,
        conversation_id: UUID,
        classification: TruthClassification,
        answer: str,
        evidence=(),
        limitations=(),
        navigation=(),
        proposals=(),
    ) -> LiaResponse:
        canonical = [item.evidence_digest for item in evidence]
        digest = hashlib.sha256(
            json.dumps(canonical, sort_keys=True).encode()
        ).hexdigest()
        response = LiaResponse(
            request_id=request_id,
            conversation_id=conversation_id,
            classification=classification,
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


lia_service = LiaService()
