"""Employee-safe Mobile boundary for the shared governed LIA contract."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.employee_operations.errors import EmployeeIdentityNotReady
from app.employee_operations.service import EmployeeDayService, employee_day_service
from app.field_service.errors import FieldServiceError
from app.field_service.service import FieldService, field_service
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import JobPermission

from .contracts import (
    AnswerAuthority,
    EvidenceReference,
    LiaRequest,
    LiaResponse,
    NavigationSuggestion,
    TruthClassification,
)
from .security import EXFILTRATION_PATTERNS, INJECTION_PATTERNS, matches_any
from .temporal import resolve_temporal_context

logger = logging.getLogger("app.lia.audit")

MOBILE_ROLE = "ACP_EMPLOYEE_MOBILE"
EMPLOYEE_SAFE_CONTRACT = "LIA.EMPLOYEE_SAFE.v1"
EMPLOYEE_DAY_AUTHORITY = "EMPLOYEE.DAY.v1"

# Classification is intentionally independent from prompt wording. The allowlist is
# evaluated before any domain retrieval, so redaction is not the security boundary.
EMPLOYEE_SAFE_TERMS = (
    "my day",
    "my schedule",
    "next job",
    "next appointment",
    "assigned to me",
    "my assigned",
    "where am i going",
    "where is my next",
    "what am i doing",
)
ROLE_GATED_TERMS = (
    "this job",
    "this appointment",
    "job status",
    "appointment status",
    "job instructions",
)
OWNER_ADMIN_ONLY_TERMS = (
    "profit",
    "margin",
    "economics",
    "luminary",
    "beacon",
    "payroll",
    "compensation",
    "salary",
    "wage",
    "financial",
    "p&l",
    "balance sheet",
    "bank",
    "payment",
    "customer pay",
    "invoice balance",
    "all customers",
    "customer history",
    "other employee",
    "all employees",
)


class EmployeeSafeLiaService:
    """Compose shared LIA responses from self-scoped Employee Operations evidence."""

    def __init__(
        self,
        day_service: EmployeeDayService = employee_day_service,
        field: FieldService = field_service,
    ) -> None:
        self.day_service = day_service
        self.field = field

    async def ask(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        request: LiaRequest,
    ) -> LiaResponse:
        question = request.question.strip()
        if MOBILE_ROLE not in context.role_codes:
            return self._response(
                context=context,
                request=request,
                classification=TruthClassification.UNAUTHORIZED,
                answer="This Employee-safe LIA surface is not available with your current Mobile authority.",
                limitations=(
                    "ACP does not reveal protected intelligence or record existence.",
                ),
            )
        if matches_any(question, INJECTION_PATTERNS + EXFILTRATION_PATTERNS):
            return self._response(
                context=context,
                request=request,
                classification=TruthClassification.UNAUTHORIZED,
                answer="I can’t provide protected instructions or information outside your authorized Employee scope.",
                limitations=("No protected source was queried.",),
            )
        normalized = question.casefold()
        if any(term in normalized for term in OWNER_ADMIN_ONLY_TERMS):
            return self._response(
                context=context,
                request=request,
                classification=TruthClassification.UNAUTHORIZED,
                answer="That information is not available through Employee-safe LIA.",
                limitations=(
                    "Employee Mobile does not retrieve owner, financial, Payroll, compensation, or unrestricted Company intelligence.",
                    "No protected source was queried.",
                ),
            )
        safe_query = any(term in normalized for term in EMPLOYEE_SAFE_TERMS)
        role_gated_query = any(term in normalized for term in ROLE_GATED_TERMS)
        if not safe_query and not role_gated_query:
            return self._response(
                context=context,
                request=request,
                classification=TruthClassification.UNAVAILABLE,
                answer="I can currently answer Employee-safe questions about your own day and assigned work.",
                limitations=(
                    "The question was not mapped to an employee-safe source.",
                    "No broad LIA or Company source was queried.",
                ),
            )
        if request.context is not None and request.context.entity_id is not None:
            return await self._assigned_job_response(
                session, context=context, request=request
            )

        temporal = resolve_temporal_context(
            question,
            timezone_name=context.active_branch.timezone
            if context.active_branch is not None
            else context.company.timezone,
        )
        business_date = temporal.start_date if temporal is not None else None
        try:
            projection = await self.day_service.day(
                session,
                context=context,
                business_date=business_date,
                authorized_branch_ids=frozenset(_response_branch_ids(context)),
            )
        except EmployeeIdentityNotReady:
            return self._response(
                context=context,
                request=request,
                classification=TruthClassification.UNAVAILABLE,
                answer="Your active Employee identity is not ready for Employee-safe LIA.",
                limitations=(
                    "An owner or administrator must repair the Membership-to-Employee binding.",
                ),
            )

        canonical = {
            "contract": EMPLOYEE_DAY_AUTHORITY,
            "company_id": str(context.company.id),
            "membership_id": str(context.membership.id),
            "authorization_version": context.authorization_version,
            "business_date": projection.business_date.isoformat(),
            "timezone": projection.timezone,
            "assignments": [
                {
                    "appointment_id": str(item.appointment_id),
                    "job_id": str(item.job_id) if item.job_id is not None else None,
                    "window_start_at": item.window_start_at.isoformat(),
                    "window_end_at": item.window_end_at.isoformat(),
                    "appointment_status": item.appointment_status,
                    "assignment_status": item.assignment_status,
                }
                for item in projection.assignments
            ],
        }
        evidence_digest = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        evidence = (
            EvidenceReference(
                domain="employee-operations",
                label="My authorized assigned work",
                authority=EMPLOYEE_DAY_AUTHORITY,
                observed_at=datetime.now(timezone.utc),
                freshness="CURRENT_QUERY",
                evidence_digest=evidence_digest,
                count=len(projection.assignments),
                state=_assignment_state(projection.assignments),
                source_contract_version=EMPLOYEE_DAY_AUTHORITY,
                company_id=context.company.id,
                branch_ids=_response_branch_ids(context),
                authorization_version=context.authorization_version,
                limitations=(
                    "Only the authenticated Employee's active assignments are included.",
                    "No availability, profitability, Payroll, payment, or unrestricted Customer history is inferred.",
                ),
                period_start=projection.business_date,
                period_end=projection.business_date,
                period_label="Employee local business day",
                timezone=projection.timezone,
            ),
        )
        if (
            request.context is not None
            and request.context.evidence_digest is not None
            and request.context.evidence_digest != evidence_digest
        ):
            return self._response(
                context=context,
                request=request,
                classification=TruthClassification.STALE,
                answer="Your assigned-work evidence changed. Refresh My Day before relying on the earlier answer.",
                evidence=evidence,
                limitations=("Prior assignment context was not silently reused.",),
            )
        answer = _answer_for(projection.assignments, projection.business_date)
        return self._response(
            context=context,
            request=request,
            classification=TruthClassification.KNOWN,
            answer=answer,
            evidence=evidence,
            limitations=(
                "This answer is limited to your currently authorized assigned-work projection.",
            ),
            navigation=(
                NavigationSuggestion(label="Open My Day", internal_path="/my-day"),
            ),
        )

    async def _assigned_job_response(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        request: LiaRequest,
    ) -> LiaResponse:
        assert request.context is not None
        assert request.context.entity_id is not None
        if request.context.domain != "jobs" or not context.has_permission(
            JobPermission.READ
        ):
            return self._response(
                context=context,
                request=request,
                classification=TruthClassification.UNAUTHORIZED,
                answer="That record is not available through Employee-safe LIA.",
                limitations=("No record existence was disclosed.",),
            )
        job_id = request.context.entity_id
        try:
            state = await self.field.state(session, context=context, job_id=job_id)
        except FieldServiceError:
            return self._response(
                context=context,
                request=request,
                classification=TruthClassification.UNAUTHORIZED,
                answer="That assigned Job is not available in your current Employee scope.",
                limitations=(
                    "Assignment, Company, and Branch authority were revalidated server-side.",
                    "No record existence was disclosed.",
                ),
            )
        canonical = {
            "contract": "FIELD.JOB.STATE.v1",
            "company_id": str(context.company.id),
            "job_id": str(state.job_id),
            "assignment_id": str(state.assignment_id),
            "completion_ready": state.completion_ready,
            "missing_requirements": list(state.missing_requirements),
            "commercial_authorization": state.commercial_authorization,
            "authorization_version": context.authorization_version,
        }
        digest = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        evidence = (
            EvidenceReference(
                domain="employee-operations",
                label="My assigned Job readiness",
                authority="FIELD.JOB.STATE.v1",
                observed_at=datetime.now(timezone.utc),
                freshness="CURRENT_QUERY",
                entity_id=state.job_id,
                evidence_digest=digest,
                count=len(state.missing_requirements),
                state=(
                    "Completion ready"
                    if state.completion_ready
                    else "Completion evidence incomplete"
                ),
                source_contract_version="FIELD.JOB.STATE.v1",
                company_id=context.company.id,
                branch_ids=_response_branch_ids(context),
                authorization_version=context.authorization_version,
                limitations=(
                    "Only current assignment-safe field readiness is included.",
                    "No Customer history, payment, margin, compensation, or office notes are included.",
                ),
            ),
        )
        if (
            request.context.evidence_digest is not None
            and request.context.evidence_digest != digest
        ):
            return self._response(
                context=context,
                request=request,
                classification=TruthClassification.STALE,
                answer="This assigned Job changed. Refresh before relying on the earlier answer.",
                evidence=evidence,
                limitations=("Prior Job evidence was not silently reused.",),
            )
        answer = (
            "This assigned Job is completion-ready."
            if state.completion_ready
            else "This assigned Job is not completion-ready. Missing evidence: "
            + ", ".join(item.replace("_", " ") for item in state.missing_requirements)
            + "."
        )
        return self._response(
            context=context,
            request=request,
            classification=TruthClassification.KNOWN,
            answer=answer,
            evidence=evidence,
            limitations=("The current assignment was revalidated for this request.",),
            navigation=(
                NavigationSuggestion(
                    label="Open assigned Job", internal_path=f"/jobs/{job_id}"
                ),
            ),
        )

    @staticmethod
    def _response(
        *,
        context: AuthorizationContext,
        request: LiaRequest,
        classification: TruthClassification,
        answer: str,
        evidence: tuple[EvidenceReference, ...] = (),
        limitations: tuple[str, ...] = (),
        navigation: tuple[NavigationSuggestion, ...] = (),
    ) -> LiaResponse:
        now = datetime.now(timezone.utc)
        evidence_digest = (
            evidence[0].evidence_digest
            if len(evidence) == 1
            else hashlib.sha256(b"[]").hexdigest()
        )
        response = LiaResponse(
            request_id=uuid4(),
            conversation_id=request.conversation_id or uuid4(),
            classification=classification,
            authority=AnswerAuthority.ACP_AUTHORITATIVE
            if evidence and classification is TruthClassification.KNOWN
            else AnswerAuthority.PARTIAL
            if evidence
            else AnswerAuthority.INSUFFICIENT_EVIDENCE,
            answer=answer,
            evidence=evidence,
            limitations=limitations,
            navigation=navigation,
            proposals=(),
            completeness="COMPLETE_FOR_EMPLOYEE_SAFE_ADAPTERS"
            if evidence
            else "NO_EVIDENCE_USED",
            freshness="CURRENT_QUERY" if evidence else "NOT_APPLICABLE",
            provider="deterministic-acp",
            provider_version="v1",
            policy_version=EMPLOYEE_SAFE_CONTRACT,
            evidence_digest=evidence_digest,
            authorization_version=context.authorization_version,
            company_id=context.company.id,
            branch_ids=_response_branch_ids(context),
            subject_domain=(
                request.context.domain
                if request.context is not None and request.context.domain is not None
                else "employee-operations"
            ),
            subject_id=request.context.entity_id
            if request.context is not None
            else None,
            source_systems=("employee-operations",) if evidence else (),
            missing_evidence=tuple(
                item for evidence_item in evidence for item in evidence_item.limitations
            ),
            safe_next_action=navigation[0].label
            if navigation
            else "Ask about your own assigned work",
            as_of=max((item.observed_at for item in evidence), default=now),
            generated_at=now,
            temporal=request.context.temporal if request.context is not None else None,
        )
        logger.info(
            "lia_employee_safe request_id=%s actor_id=%s company_id=%s classification=%s evidence_digest=%s",
            response.request_id,
            context.user.id,
            context.company.id,
            response.classification,
            response.evidence_digest,
        )
        return response


def _response_branch_ids(context: AuthorizationContext) -> tuple:
    if context.active_branch is not None:
        return (context.active_branch.id,)
    return tuple(sorted(context.authorized_branch_ids, key=str))


def _assignment_state(assignments) -> str:
    if not assignments:
        return "No assigned appointments for the selected business day."
    return "; ".join(
        f"{item.appointment_number} / {item.job_number or 'Job unavailable'} / "
        f"{item.appointment_status} / {item.assignment_status}"
        for item in assignments[:10]
    )


def _answer_for(assignments, business_date) -> str:
    if not assignments:
        return f"You have no authorized assigned appointments on {business_date.isoformat()}."
    first = assignments[0]
    return (
        f"You have {len(assignments)} assigned appointment{'s' if len(assignments) != 1 else ''} "
        f"on {business_date.isoformat()}. Next is {first.appointment_number}"
        f"{f' for {first.job_number}' if first.job_number else ''} at "
        f"{first.window_start_at.isoformat()} for {first.customer_display_name}, "
        f"{first.location_nickname or first.address_line_1}."
    )


employee_safe_lia_service = EmployeeSafeLiaService()
