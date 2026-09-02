"""Permission-bounded Workforce and Employee-readiness context for LIA."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AdministrationPermission, WorkforcePermission

from .employee_administration import employee_administration_service
from .service import workforce_operations_service

CONTRACT_VERSION = "WORKFORCE.LIA_CONTEXT.v1"


class WorkforceLiaContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: str = CONTRACT_VERSION
    entity_id: UUID
    company_id: UUID
    branch_ids: tuple[UUID, ...]
    authorization_version: int
    display_name: str
    employee_number: str
    employee_status: str
    readiness_state: str
    readiness_blockers: tuple[str, ...]
    capability_codes: tuple[str, ...]
    language_codes: tuple[str, ...]
    certification_states: dict[str, int]
    availability_states: dict[str, int]
    permission_explanations: tuple[str, ...] | None
    onboarding_state: str | None
    mobile_readiness: str | None
    mobile_readiness_blockers: tuple[str, ...]
    limitations: tuple[str, ...]
    observed_at: datetime
    evidence_digest: str

    def safe_summary(self) -> str:
        return (
            f"Employee {self.display_name} is {self.employee_status}; operational readiness is "
            f"{self.readiness_state}. Mobile readiness: {self.mobile_readiness or 'not authorized'}."
        )


class WorkforceLiaContextService:
    async def project(
        self, session: AsyncSession, *, context: AuthorizationContext, employee_id: UUID
    ) -> WorkforceLiaContext | None:
        if not context.has_permission(WorkforcePermission.READ):
            return None
        detail = await workforce_operations_service.detail(
            session, context=context, employee_id=employee_id
        )
        if detail is None:
            return None
        branch_ids = tuple(
            sorted(
                (item.branch_id for item in detail.branches if item.status == "active"),
                key=str,
            )
        )
        certification_states: dict[str, int] = {}
        for certification in detail.certifications:
            certification_states[certification.status] = (
                certification_states.get(certification.status, 0) + 1
            )
        availability_states: dict[str, int] = {}
        for availability in detail.availability:
            availability_states[availability.status] = (
                availability_states.get(availability.status, 0) + 1
            )
        permission_explanations = None
        onboarding_state = None
        mobile_readiness = None
        mobile_blockers: tuple[str, ...] = ()
        if {
            WorkforcePermission.MANAGE,
            AdministrationPermission.MEMBERSHIP_READ,
            AdministrationPermission.ROLE_READ,
        }.issubset(context.permission_codes):
            administration = await employee_administration_service.detail(
                session, context=context, employee_id=employee_id
            )
            if administration is not None:
                permission_explanations = tuple(
                    f"{item.code}:{item.authority}:{'branch' if item.branch_scoped else 'company'}"
                    for item in administration.permissions
                )
                onboarding_state = administration.onboarding_status
                mobile_readiness = administration.mobile_readiness
                mobile_blockers = administration.mobile_readiness_blockers
        limitations = (
            "compensation_payroll_tax_and_banking_excluded",
            "credential_references_excluded",
            "readiness_is_not_subjective_employee_ranking",
            "no_permission_or_employee_mutation_authority",
        )
        observed_at = datetime.now(timezone.utc)
        canonical = {
            "contract_version": CONTRACT_VERSION,
            "entity_id": str(detail.employee_id),
            "company_id": str(context.company.id),
            "branch_ids": [str(item) for item in branch_ids],
            "authorization_version": context.authorization_version,
            "display_name": detail.display_name,
            "employee_number": detail.employee_number,
            "employee_status": detail.employee_status,
            "readiness_state": detail.readiness_state,
            "readiness_blockers": detail.readiness_blockers,
            "capability_codes": detail.capability_codes,
            "language_codes": detail.language_codes,
            "certification_states": certification_states,
            "availability_states": availability_states,
            "permission_explanations": permission_explanations,
            "onboarding_state": onboarding_state,
            "mobile_readiness": mobile_readiness,
            "mobile_readiness_blockers": mobile_blockers,
            "limitations": limitations,
        }
        digest = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return WorkforceLiaContext(
            entity_id=detail.employee_id,
            company_id=context.company.id,
            branch_ids=branch_ids,
            authorization_version=context.authorization_version,
            display_name=detail.display_name,
            employee_number=detail.employee_number,
            employee_status=detail.employee_status,
            readiness_state=detail.readiness_state,
            readiness_blockers=detail.readiness_blockers,
            capability_codes=detail.capability_codes,
            language_codes=detail.language_codes,
            certification_states=certification_states,
            availability_states=availability_states,
            permission_explanations=permission_explanations,
            onboarding_state=onboarding_state,
            mobile_readiness=mobile_readiness,
            mobile_readiness_blockers=mobile_blockers,
            limitations=limitations,
            observed_at=observed_at,
            evidence_digest=digest,
        )


workforce_lia_context_service = WorkforceLiaContextService()
