"""Transaction owner for Payroll policy and compensation authority."""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import AuthorizationContext
from app.timekeeping.contracts import PayrollTimeInputSnapshot

from .commands import DraftCompensationAuthority, DraftPayrollPolicy
from .contracts import (
    COMPENSATION_AUTHORITY_DEFINITION_VERSION,
    PAYROLL_POLICY_DEFINITION_VERSION,
    ApprovedCompensationAuthority,
    ApprovedPayrollPolicy,
    AuthorityLifecycle,
    CompanyPayrollPolicyDefinition,
    CompensationType,
    OvertimeExceptionScope,
    OvertimePolicy,
    OvertimePremiumTreatment,
    PayrollAdmissionResult,
    PayrollAuthorityError,
    PayrollAuthorizationError,
    PayrollConflictError,
    SalariedTimeRequirement,
    ScopedOvertimeException,
    canonical_digest,
    evaluate_payroll_admission,
)
from .models import CompanyPayrollPolicyVersion, EmployeeCompensationAuthorityVersion
from .permissions import PayrollPermission
from .repository import PayrollAuthorityRepository, payroll_authority_repository


class PayrollAuthorityService:
    def __init__(
        self,
        repository: PayrollAuthorityRepository = payroll_authority_repository,
        *,
        audit: AuditService = audit_service,
    ) -> None:
        self._repository = repository
        self._audit = audit

    async def draft_policy(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: DraftPayrollPolicy,
    ) -> CompanyPayrollPolicyVersion:
        self._require(context, PayrollPermission.POLICY_MANAGE)
        command.definition.validate()
        self._validate_interval(command.effective_start, command.effective_end)
        if command.policy_version < 1 or not command.audit_reason.strip():
            raise PayrollAuthorityError("policy version and audit reason are required")
        prior = None
        if command.supersedes_policy_id is not None:
            prior = await self._repository.policy_by_id(
                session,
                company_id=context.company.id,
                policy_id=command.supersedes_policy_id,
            )
            if prior is None or prior.lifecycle not in {
                AuthorityLifecycle.APPROVED.value,
                AuthorityLifecycle.SUPERSEDED.value,
            }:
                raise PayrollConflictError(
                    "superseded policy is not approved authority"
                )
        definition = command.definition.canonical_content()
        authority_digest = canonical_digest(
            {
                "company_id": str(context.company.id),
                "policy_version": command.policy_version,
                "effective_start": command.effective_start.isoformat(),
                "effective_end": (
                    command.effective_end.isoformat() if command.effective_end else None
                ),
                "definition": definition,
                "decision_evidence_digest": command.decision_evidence_digest,
                "supersedes_policy_id": (
                    str(command.supersedes_policy_id)
                    if command.supersedes_policy_id
                    else None
                ),
            }
        )
        value = CompanyPayrollPolicyVersion(
            id=uuid4(),
            company_id=context.company.id,
            policy_version=command.policy_version,
            effective_start=command.effective_start,
            effective_end=command.effective_end,
            lifecycle=AuthorityLifecycle.DRAFT.value,
            definition_version=PAYROLL_POLICY_DEFINITION_VERSION,
            definition=definition,
            decision_evidence_digest=command.decision_evidence_digest,
            authority_digest=authority_digest,
            supersedes_policy_id=command.supersedes_policy_id,
            drafted_by_user_id=context.user.id,
            approved_by_user_id=None,
            approved_at=None,
            retired_by_user_id=None,
            retired_at=None,
            audit_reason=command.audit_reason.strip(),
        )
        session.add(value)
        self._stage(
            session,
            context=context,
            event_type=EventType.PAYROLL_POLICY_DRAFTED,
            action="payroll.policy.drafted",
            resource_type="payroll_policy",
            resource_id=value.id,
            details={"policy_version": command.policy_version},
        )
        await session.commit()
        return value

    async def approve_policy(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        policy_id: UUID,
    ) -> CompanyPayrollPolicyVersion:
        self._require(context, PayrollPermission.POLICY_APPROVE)
        value = await self._repository.policy_by_id(
            session, company_id=context.company.id, policy_id=policy_id
        )
        if value is None or value.lifecycle != AuthorityLifecycle.DRAFT.value:
            raise PayrollConflictError("only a Company draft policy may be approved")
        if value.drafted_by_user_id == context.user.id:
            raise PayrollAuthorizationError(
                "policy drafter cannot approve the same policy"
            )
        overlaps = await self._repository.overlapping_policies(
            session,
            company_id=context.company.id,
            effective_start=value.effective_start,
            effective_end=value.effective_end,
            exclude_policy_id=value.id,
        )
        allowed_prior_ids = (
            {value.supersedes_policy_id} if value.supersedes_policy_id else set()
        )
        if any(item.id not in allowed_prior_ids for item in overlaps):
            raise PayrollConflictError("approved Payroll policy intervals overlap")
        now = datetime.now(timezone.utc)
        value.lifecycle = AuthorityLifecycle.APPROVED.value
        value.approved_by_user_id = context.user.id
        value.approved_at = now
        value.authority_digest = self._approved_policy_digest(value)
        if value.supersedes_policy_id is not None:
            prior = await self._repository.policy_by_id(
                session,
                company_id=context.company.id,
                policy_id=value.supersedes_policy_id,
            )
            if prior is None:
                raise PayrollConflictError("superseded policy disappeared")
            prior.lifecycle = AuthorityLifecycle.SUPERSEDED.value
            self._stage(
                session,
                context=context,
                event_type=EventType.PAYROLL_POLICY_SUPERSEDED,
                action="payroll.policy.superseded",
                resource_type="payroll_policy",
                resource_id=prior.id,
                details={"successor_policy_id": str(value.id)},
            )
        self._stage(
            session,
            context=context,
            event_type=EventType.PAYROLL_POLICY_APPROVED,
            action="payroll.policy.approved",
            resource_type="payroll_policy",
            resource_id=value.id,
            details={"policy_version": value.policy_version},
        )
        await session.commit()
        return value

    async def resolve_policy(
        self, session: AsyncSession, *, company_id: UUID, as_of_date: date
    ) -> ApprovedPayrollPolicy | None:
        candidates = await self._repository.policies_at(
            session, company_id=company_id, as_of_date=as_of_date
        )
        active = self._remove_superseded_ancestors(candidates)
        if not active:
            return None
        if len(active) != 1:
            raise PayrollConflictError("Payroll policy resolution is ambiguous")
        value = active[0]
        if (
            value.definition_version != PAYROLL_POLICY_DEFINITION_VERSION
            or value.approved_by_user_id is None
            or value.approved_at is None
        ):
            raise PayrollConflictError("Payroll policy authority is malformed")
        result = ApprovedPayrollPolicy(
            policy_id=value.id,
            company_id=value.company_id,
            policy_version=value.policy_version,
            effective_start=value.effective_start,
            effective_end=value.effective_end,
            definition=self._definition(value.definition),
            approved_by_user_id=value.approved_by_user_id,
            approved_at=value.approved_at,
            decision_evidence_digest=value.decision_evidence_digest,
            authority_digest=value.authority_digest,
        )
        result.verify()
        return result

    async def retire_policy(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        policy_id: UUID,
    ) -> CompanyPayrollPolicyVersion:
        self._require(context, PayrollPermission.POLICY_APPROVE)
        value = await self._repository.policy_by_id(
            session, company_id=context.company.id, policy_id=policy_id
        )
        if value is None or value.lifecycle not in {
            AuthorityLifecycle.APPROVED.value,
            AuthorityLifecycle.SUPERSEDED.value,
        }:
            raise PayrollConflictError("only approved policy authority may be retired")
        value.lifecycle = AuthorityLifecycle.RETIRED.value
        value.retired_by_user_id = context.user.id
        value.retired_at = datetime.now(timezone.utc)
        self._stage(
            session,
            context=context,
            event_type=EventType.PAYROLL_POLICY_RETIRED,
            action="payroll.policy.retired",
            resource_type="payroll_policy",
            resource_id=value.id,
            details={"policy_version": value.policy_version},
        )
        await session.commit()
        return value

    async def draft_compensation(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: DraftCompensationAuthority,
    ) -> EmployeeCompensationAuthorityVersion:
        self._require(context, PayrollPermission.COMPENSATION_MANAGE)
        self._validate_interval(command.effective_start, command.effective_end)
        self._validate_compensation_shape(command)
        if command.authority_version < 1 or not command.audit_reason.strip():
            raise PayrollAuthorityError(
                "authority version and audit reason are required"
            )
        if command.supersedes_authority_id is not None:
            prior = await self._repository.compensation_by_id(
                session,
                company_id=context.company.id,
                authority_id=command.supersedes_authority_id,
            )
            if (
                prior is None
                or prior.employee_id != command.employee_id
                or prior.lifecycle
                not in {
                    AuthorityLifecycle.APPROVED.value,
                    AuthorityLifecycle.SUPERSEDED.value,
                }
            ):
                raise PayrollConflictError("superseded compensation is out of scope")
        content = {
            "company_id": str(context.company.id),
            "employee_id": str(command.employee_id),
            "authority_version": command.authority_version,
            "effective_start": command.effective_start.isoformat(),
            "effective_end": (
                command.effective_end.isoformat() if command.effective_end else None
            ),
            "compensation_type": command.compensation_type.value,
            "hourly_rate": str(command.hourly_rate) if command.hourly_rate else None,
            "salary_amount": str(command.salary_amount)
            if command.salary_amount
            else None,
            "salary_frequency": command.salary_frequency,
            "worker_class_reference": command.worker_class_reference,
            "additional_earning_types": command.additional_earning_types,
            "recurring_components": command.recurring_components,
            "decision_evidence_digest": command.decision_evidence_digest,
            "supersedes_authority_id": (
                str(command.supersedes_authority_id)
                if command.supersedes_authority_id
                else None
            ),
        }
        value = EmployeeCompensationAuthorityVersion(
            id=uuid4(),
            company_id=context.company.id,
            employee_id=command.employee_id,
            authority_version=command.authority_version,
            effective_start=command.effective_start,
            effective_end=command.effective_end,
            lifecycle=AuthorityLifecycle.DRAFT.value,
            definition_version=COMPENSATION_AUTHORITY_DEFINITION_VERSION,
            compensation_type=command.compensation_type.value,
            hourly_rate=command.hourly_rate,
            salary_amount=command.salary_amount,
            salary_frequency=command.salary_frequency,
            worker_class_reference=command.worker_class_reference,
            additional_earning_types=list(command.additional_earning_types),
            recurring_components=list(command.recurring_components),
            decision_evidence_digest=command.decision_evidence_digest,
            authority_digest=canonical_digest(content),
            supersedes_authority_id=command.supersedes_authority_id,
            drafted_by_user_id=context.user.id,
            approved_by_user_id=None,
            approved_at=None,
            retired_by_user_id=None,
            retired_at=None,
            audit_reason=command.audit_reason.strip(),
        )
        session.add(value)
        self._stage(
            session,
            context=context,
            event_type=EventType.PAYROLL_COMPENSATION_DRAFTED,
            action="payroll.compensation.drafted",
            resource_type="payroll_compensation_authority",
            resource_id=value.id,
            details={
                "employee_id": str(command.employee_id),
                "authority_version": command.authority_version,
                "compensation_type": command.compensation_type.value,
            },
        )
        await session.commit()
        return value

    async def approve_compensation(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        authority_id: UUID,
    ) -> EmployeeCompensationAuthorityVersion:
        self._require(context, PayrollPermission.COMPENSATION_APPROVE)
        value = await self._repository.compensation_by_id(
            session, company_id=context.company.id, authority_id=authority_id
        )
        if value is None or value.lifecycle != AuthorityLifecycle.DRAFT.value:
            raise PayrollConflictError("only draft compensation may be approved")
        if value.drafted_by_user_id == context.user.id:
            raise PayrollAuthorizationError(
                "compensation drafter cannot approve the same authority"
            )
        overlaps = await self._repository.overlapping_compensations(
            session,
            company_id=context.company.id,
            employee_id=value.employee_id,
            effective_start=value.effective_start,
            effective_end=value.effective_end,
            exclude_authority_id=value.id,
        )
        allowed_prior_ids = (
            {value.supersedes_authority_id} if value.supersedes_authority_id else set()
        )
        if any(item.id not in allowed_prior_ids for item in overlaps):
            raise PayrollConflictError("approved compensation intervals overlap")
        value.lifecycle = AuthorityLifecycle.APPROVED.value
        value.approved_by_user_id = context.user.id
        value.approved_at = datetime.now(timezone.utc)
        value.authority_digest = self._approved_compensation_digest(value)
        if value.supersedes_authority_id is not None:
            prior = await self._repository.compensation_by_id(
                session,
                company_id=context.company.id,
                authority_id=value.supersedes_authority_id,
            )
            if prior is None:
                raise PayrollConflictError("superseded compensation disappeared")
            prior.lifecycle = AuthorityLifecycle.SUPERSEDED.value
            self._stage(
                session,
                context=context,
                event_type=EventType.PAYROLL_COMPENSATION_SUPERSEDED,
                action="payroll.compensation.superseded",
                resource_type="payroll_compensation_authority",
                resource_id=prior.id,
                details={"successor_authority_id": str(value.id)},
            )
        self._stage(
            session,
            context=context,
            event_type=EventType.PAYROLL_COMPENSATION_APPROVED,
            action="payroll.compensation.approved",
            resource_type="payroll_compensation_authority",
            resource_id=value.id,
            details={
                "employee_id": str(value.employee_id),
                "authority_version": value.authority_version,
                "compensation_type": value.compensation_type,
            },
        )
        await session.commit()
        return value

    async def resolve_compensation(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        employee_id: UUID,
        as_of_date: date,
    ) -> ApprovedCompensationAuthority | None:
        candidates = await self._repository.compensations_at(
            session,
            company_id=company_id,
            employee_id=employee_id,
            as_of_date=as_of_date,
        )
        active = self._remove_superseded_ancestors(candidates)
        if not active:
            return None
        if len(active) != 1:
            raise PayrollConflictError("compensation resolution is ambiguous")
        value = active[0]
        if (
            value.definition_version != COMPENSATION_AUTHORITY_DEFINITION_VERSION
            or value.approved_by_user_id is None
            or value.approved_at is None
        ):
            raise PayrollConflictError("compensation authority is malformed")
        result = ApprovedCompensationAuthority(
            authority_id=value.id,
            company_id=value.company_id,
            employee_id=value.employee_id,
            authority_version=value.authority_version,
            effective_start=value.effective_start,
            effective_end=value.effective_end,
            compensation_type=CompensationType(value.compensation_type),
            hourly_rate=value.hourly_rate,
            salary_amount=value.salary_amount,
            salary_frequency=value.salary_frequency,
            worker_class_reference=value.worker_class_reference,
            additional_earning_types=tuple(value.additional_earning_types),
            recurring_components=tuple(value.recurring_components),
            approved_by_user_id=value.approved_by_user_id,
            approved_at=value.approved_at,
            decision_evidence_digest=value.decision_evidence_digest,
            authority_digest=value.authority_digest,
        )
        result.verify()
        return result

    async def retire_compensation(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        authority_id: UUID,
    ) -> EmployeeCompensationAuthorityVersion:
        self._require(context, PayrollPermission.COMPENSATION_APPROVE)
        value = await self._repository.compensation_by_id(
            session, company_id=context.company.id, authority_id=authority_id
        )
        if value is None or value.lifecycle not in {
            AuthorityLifecycle.APPROVED.value,
            AuthorityLifecycle.SUPERSEDED.value,
        }:
            raise PayrollConflictError(
                "only approved compensation authority may be retired"
            )
        value.lifecycle = AuthorityLifecycle.RETIRED.value
        value.retired_by_user_id = context.user.id
        value.retired_at = datetime.now(timezone.utc)
        self._stage(
            session,
            context=context,
            event_type=EventType.PAYROLL_COMPENSATION_RETIRED,
            action="payroll.compensation.retired",
            resource_type="payroll_compensation_authority",
            resource_id=value.id,
            details={
                "employee_id": str(value.employee_id),
                "authority_version": value.authority_version,
            },
        )
        await session.commit()
        return value

    async def evaluate_admission(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        identity_resolved: bool,
        policy: ApprovedPayrollPolicy | None,
        compensation: ApprovedCompensationAuthority | None,
        time_input: PayrollTimeInputSnapshot | None,
        pay_period_schedule_definition_id: str | None = None,
        pay_period_schedule_version: int | None = None,
        resolution_conflict: bool = False,
    ) -> PayrollAdmissionResult:
        self._require(context, PayrollPermission.ADMISSION_REVIEW)
        result = evaluate_payroll_admission(
            company_id=context.company.id,
            identity_resolved=identity_resolved,
            policy=policy,
            compensation=compensation,
            time_input=time_input,
            pay_period_schedule_definition_id=pay_period_schedule_definition_id,
            pay_period_schedule_version=pay_period_schedule_version,
            resolution_conflict=resolution_conflict,
        )
        event_id = uuid4()
        self._stage(
            session,
            context=context,
            event_type=EventType.PAYROLL_ADMISSION_EVALUATED,
            action="payroll.admission.evaluated",
            resource_type="payroll_admission",
            resource_id=event_id,
            details={
                "admission_id": result.admission_id,
                "state": result.state.value,
                "blockers": result.blockers,
                "employee_id": str(result.employee_id) if result.employee_id else None,
                "pay_period_id": (
                    str(result.pay_period_id) if result.pay_period_id else None
                ),
            },
        )
        await session.commit()
        return result

    @staticmethod
    def _remove_superseded_ancestors(values):
        superseded_ids = {
            value.supersedes_policy_id
            if isinstance(value, CompanyPayrollPolicyVersion)
            else value.supersedes_authority_id
            for value in values
            if (
                value.supersedes_policy_id
                if isinstance(value, CompanyPayrollPolicyVersion)
                else value.supersedes_authority_id
            )
            is not None
        }
        return tuple(value for value in values if value.id not in superseded_ids)

    @classmethod
    def _approved_policy_digest(cls, value: CompanyPayrollPolicyVersion) -> str:
        assert value.approved_by_user_id is not None and value.approved_at is not None
        policy = ApprovedPayrollPolicy(
            policy_id=value.id,
            company_id=value.company_id,
            policy_version=value.policy_version,
            effective_start=value.effective_start,
            effective_end=value.effective_end,
            definition=cls._definition(value.definition),
            approved_by_user_id=value.approved_by_user_id,
            approved_at=value.approved_at,
            decision_evidence_digest=value.decision_evidence_digest,
            authority_digest="",
        )
        return canonical_digest(policy.canonical_content())

    @staticmethod
    def _approved_compensation_digest(
        value: EmployeeCompensationAuthorityVersion,
    ) -> str:
        assert value.approved_by_user_id is not None and value.approved_at is not None
        authority = ApprovedCompensationAuthority(
            authority_id=value.id,
            company_id=value.company_id,
            employee_id=value.employee_id,
            authority_version=value.authority_version,
            effective_start=value.effective_start,
            effective_end=value.effective_end,
            compensation_type=CompensationType(value.compensation_type),
            hourly_rate=value.hourly_rate,
            salary_amount=value.salary_amount,
            salary_frequency=value.salary_frequency,
            worker_class_reference=value.worker_class_reference,
            additional_earning_types=tuple(value.additional_earning_types),
            recurring_components=tuple(value.recurring_components),
            approved_by_user_id=value.approved_by_user_id,
            approved_at=value.approved_at,
            decision_evidence_digest=value.decision_evidence_digest,
            authority_digest="",
        )
        return canonical_digest(authority.canonical_content())

    @staticmethod
    def _definition(value: dict[str, object]) -> CompanyPayrollPolicyDefinition:
        overtime_value = value.get("overtime")
        overtime = None
        if isinstance(overtime_value, dict):
            overtime = OvertimePolicy(
                weekly_threshold_minutes=overtime_value.get("weekly_threshold_minutes"),  # type: ignore[arg-type]
                daily_threshold_minutes=overtime_value.get("daily_threshold_minutes"),  # type: ignore[arg-type]
                multiplier=PayrollAuthorityService._decimal(
                    overtime_value.get("multiplier")
                ),
                double_time_threshold_minutes=overtime_value.get(
                    "double_time_threshold_minutes"
                ),  # type: ignore[arg-type]
                double_time_multiplier=PayrollAuthorityService._decimal(
                    overtime_value.get("double_time_multiplier")
                ),
                workweek_start_day=int(overtime_value["workweek_start_day"]),
                workweek_start_time=str(overtime_value["workweek_start_time"]),
                included_earning_categories=tuple(
                    str(item) for item in overtime_value["included_earning_categories"]
                ),
                excluded_earning_categories=tuple(
                    str(item) for item in overtime_value["excluded_earning_categories"]
                ),
                scoped_exceptions=tuple(
                    ScopedOvertimeException(
                        exception_id=str(item["exception_id"]),
                        scope=OvertimeExceptionScope(str(item["scope"])),
                        employee_id=(
                            UUID(str(item["employee_id"]))
                            if item.get("employee_id") is not None
                            else None
                        ),
                        worker_class_reference=(
                            str(item["worker_class_reference"])
                            if item.get("worker_class_reference") is not None
                            else None
                        ),
                        treatment=OvertimePremiumTreatment(str(item["treatment"])),
                        effective_start=date.fromisoformat(
                            str(item["effective_start"])
                        ),
                        effective_end=(
                            date.fromisoformat(str(item["effective_end"]))
                            if item.get("effective_end") is not None
                            else None
                        ),
                        decision_evidence_digest=str(item["decision_evidence_digest"]),
                        legal_compliance_review_required=bool(
                            item["legal_compliance_review_required"]
                        ),
                        definition_version=str(item["definition_version"]),
                    )
                    for item in overtime_value.get("scoped_exceptions", ())
                    if isinstance(item, dict)
                ),
            )
        result = CompanyPayrollPolicyDefinition(
            pay_frequency=str(value["pay_frequency"]),
            schedule_definition_id=str(value["schedule_definition_id"]),
            schedule_version=PayrollAuthorityService._int(value["schedule_version"]),
            regular_earning_categories=PayrollAuthorityService._strings(
                value["regular_earning_categories"]
            ),
            overtime=overtime,
            break_treatment=str(value["break_treatment"]),
            leave_category_refs=PayrollAuthorityService._strings(
                value["leave_category_refs"]
            ),
            holiday_policy_ref=(
                str(value["holiday_policy_ref"])
                if value.get("holiday_policy_ref") is not None
                else None
            ),
            pto_policy_ref=(
                str(value["pto_policy_ref"])
                if value.get("pto_policy_ref") is not None
                else None
            ),
            salaried_time_requirement=SalariedTimeRequirement(
                str(value["salaried_time_requirement"])
            ),
            minimum_increment_minutes=(
                PayrollAuthorityService._int(value["minimum_increment_minutes"])
                if value.get("minimum_increment_minutes") is not None
                else None
            ),
            rounding_rule=(
                str(value["rounding_rule"])
                if value.get("rounding_rule") is not None
                else None
            ),
            pre_finalization_correction_treatment=str(
                value["pre_finalization_correction_treatment"]
            ),
            post_finalization_adjustment_treatment=str(
                value["post_finalization_adjustment_treatment"]
            ),
            post_payment_adjustment_treatment=str(
                value["post_payment_adjustment_treatment"]
            ),
            cutoff_rule=str(value["cutoff_rule"]),
            required_time_approvals=PayrollAuthorityService._int(
                value["required_time_approvals"]
            ),
            compensation_authority_required=bool(
                value["compensation_authority_required"]
            ),
        )
        result.validate()
        return result

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        return Decimal(str(value)) if value is not None else None

    @staticmethod
    def _int(value: object) -> int:
        if not isinstance(value, (int, str)):
            raise PayrollConflictError("Payroll policy integer is malformed")
        return int(value)

    @staticmethod
    def _strings(value: object) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)):
            raise PayrollConflictError("Payroll policy list is malformed")
        return tuple(str(item) for item in value)

    @staticmethod
    def _validate_compensation_shape(command: DraftCompensationAuthority) -> None:
        if command.compensation_type is CompensationType.HOURLY:
            valid = (
                command.hourly_rate is not None
                and command.hourly_rate > 0
                and command.salary_amount is None
                and command.salary_frequency is None
            )
        else:
            valid = (
                command.salary_amount is not None
                and command.salary_amount > 0
                and bool(command.salary_frequency)
                and command.hourly_rate is None
            )
        if not valid:
            raise PayrollAuthorityError("compensation authority shape is invalid")

    @staticmethod
    def _validate_interval(start: date, end: date | None) -> None:
        if end is not None and end <= start:
            raise PayrollAuthorityError("authority effective interval is invalid")

    @staticmethod
    def _require(context: AuthorizationContext, permission: str) -> None:
        if not context.has_permission(permission):
            raise PayrollAuthorizationError("Payroll authority permission denied")

    def _stage(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        event_type: EventType,
        action: str,
        resource_type: str,
        resource_id: UUID,
        details: dict[str, object],
    ) -> None:
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type=resource_type,
                entity_id=resource_id,
                company_id=context.company.id,
                user_id=context.user.id,
                payload=details,
            ),
        )
        self._audit.stage(
            session,
            AuditEntry(
                action=action,
                resource_type=resource_type,
                actor_user_id=context.user.id,
                company_id=context.company.id,
                resource_id=resource_id,
                details=details,
            ),
        )


payroll_authority_service = PayrollAuthorityService()
