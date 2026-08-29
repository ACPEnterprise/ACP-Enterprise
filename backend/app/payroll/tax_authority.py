"""Protected tax/deduction input authority; no tax or deduction arithmetic."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import AuthorizationContext

from .contracts import (
    AuthorityLifecycle,
    PayrollAuthorityError,
    PayrollAuthorizationError,
    PayrollConflictError,
    canonical_digest,
)
from .models import (
    PayrollGrossCalculationResultRecord,
    PayrollInputAuthorityVersion,
    PayrollProtectedInputEnvelope,
)
from .permissions import PayrollPermission

PAYROLL_INPUT_AUTHORITY_VERSION = "payroll.tax-deduction-authority.v1"
PAYROLL_TAX_DEDUCTION_ADMISSION_VERSION = "payroll.tax-deduction-admission.v1"


class PayrollInputDomain(StrEnum):
    TAX = "tax"
    DEDUCTION = "deduction"
    EMPLOYER_CONTRIBUTION = "employer_contribution"


class AuthorityApplicability(StrEnum):
    REQUIRED = "required"
    NOT_APPLICABLE = "not_applicable"


class TaxDeductionAdmissionState(StrEnum):
    READY = "ready"
    MISSING = "missing"
    EXPIRED = "expired"
    CONFLICTING = "conflicting"
    UNAPPROVED = "unapproved"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class DraftPayrollInputAuthority:
    employee_id: UUID | None
    domain: PayrollInputDomain
    authority_key: str
    authority_version: int
    applicability: AuthorityApplicability
    effective_start: date
    effective_end: date | None
    jurisdiction_reference: str | None
    calculation_basis: str | None
    priority: int | None
    public_parameters: dict[str, object]
    evidence_digest: str
    audit_reason: str
    protected_payload: dict[str, object] | None = None
    supersedes_authority_id: UUID | None = None


@dataclass(frozen=True)
class AuthorityRequirement:
    domain: PayrollInputDomain
    authority_key: str
    employee_id: UUID | None
    required: bool = True

    def canonical_content(self) -> dict[str, object]:
        return {
            "domain": self.domain.value,
            "authority_key": self.authority_key,
            "employee_id": str(self.employee_id) if self.employee_id else None,
            "required": self.required,
        }


@dataclass(frozen=True)
class AuthorityResolution:
    requirement: AuthorityRequirement
    state: TaxDeductionAdmissionState
    authority_id: UUID | None
    authority_digest: str | None
    protected_input_digest: str | None
    limitations: tuple[str, ...]

    def canonical_content(self) -> dict[str, object]:
        return {
            "requirement": self.requirement.canonical_content(),
            "state": self.state.value,
            "authority_id": str(self.authority_id) if self.authority_id else None,
            "authority_digest": self.authority_digest,
            "protected_input_digest": self.protected_input_digest,
            "limitations": self.limitations,
        }


@dataclass(frozen=True)
class TaxDeductionAdmissionResult:
    company_id: UUID
    employee_id: UUID
    gross_result_id: UUID
    gross_calculation_digest: str
    as_of_date: date
    definition_version: str
    state: TaxDeductionAdmissionState
    resolutions: tuple[AuthorityResolution, ...]
    blockers: tuple[str, ...]
    admission_digest: str

    def canonical_content(self) -> dict[str, object]:
        return {
            "company_id": str(self.company_id),
            "employee_id": str(self.employee_id),
            "gross_result_id": str(self.gross_result_id),
            "gross_calculation_digest": self.gross_calculation_digest,
            "as_of_date": self.as_of_date.isoformat(),
            "definition_version": self.definition_version,
            "state": self.state.value,
            "resolutions": tuple(item.canonical_content() for item in self.resolutions),
            "blockers": self.blockers,
        }

    def verify(self) -> None:
        if canonical_digest(self.canonical_content()) != self.admission_digest:
            raise PayrollConflictError("tax/deduction admission digest is invalid")


class ProtectedPayrollInputCipher:
    """Injected keyring boundary; persistence receives ciphertext only."""

    def __init__(self, *, active_key_id: str, keys: dict[str, bytes]) -> None:
        if active_key_id not in keys or len(keys[active_key_id]) != 32:
            raise PayrollAuthorityError("protected Payroll input key is unavailable")
        self.active_key_id = active_key_id
        self._keys = dict(keys)

    def encrypt(
        self, *, company_id: UUID, payload: dict[str, object]
    ) -> tuple[str, bytes, bytes, str]:
        plaintext = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), default=str
        ).encode()
        digest = canonical_digest(payload)
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._keys[self.active_key_id]).encrypt(
            nonce, plaintext, str(company_id).encode()
        )
        return self.active_key_id, nonce, ciphertext, digest


class PayrollInputAuthorityService:
    def __init__(
        self,
        *,
        cipher: ProtectedPayrollInputCipher | None = None,
        audit: AuditService = audit_service,
    ) -> None:
        self._cipher = cipher
        self._audit = audit

    async def draft(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: DraftPayrollInputAuthority,
    ) -> PayrollInputAuthorityVersion:
        self._require(context, self._manage_permission(command.domain))
        self._validate(command)
        protected_envelope: PayrollProtectedInputEnvelope | None = None
        protected_digest = (
            canonical_digest(command.protected_payload)
            if command.protected_payload is not None
            else None
        )
        existing = await session.scalar(
            select(PayrollInputAuthorityVersion).where(
                PayrollInputAuthorityVersion.company_id == context.company.id,
                PayrollInputAuthorityVersion.employee_id == command.employee_id,
                PayrollInputAuthorityVersion.authority_domain == command.domain.value,
                PayrollInputAuthorityVersion.authority_key
                == command.authority_key.strip(),
                PayrollInputAuthorityVersion.authority_version
                == command.authority_version,
            )
        )
        if existing is not None:
            expected = canonical_digest(
                self._content(
                    company_id=context.company.id,
                    command=command,
                    protected_digest=protected_digest,
                    approved_by_user_id=None,
                    approved_at=None,
                )
            )
            existing_protected_digest = await self._protected_digest(session, existing)
            existing_draft_digest = canonical_digest(
                self._content(
                    company_id=existing.company_id,
                    command=self._command_from_record(existing),
                    protected_digest=existing_protected_digest,
                    approved_by_user_id=None,
                    approved_at=None,
                )
            )
            if existing_draft_digest == expected:
                return existing
            raise PayrollConflictError(
                "input authority replay contradicts existing authority"
            )
        if command.protected_payload is not None:
            if self._cipher is None:
                raise PayrollAuthorityError(
                    "protected Payroll input encryption is not configured"
                )
            kid, nonce, ciphertext, encrypted_digest = self._cipher.encrypt(
                company_id=context.company.id, payload=command.protected_payload
            )
            if encrypted_digest != protected_digest:
                raise PayrollConflictError(
                    "protected input digest changed during sealing"
                )
            protected_envelope = PayrollProtectedInputEnvelope(
                id=uuid4(),
                company_id=context.company.id,
                key_id=kid,
                nonce=nonce,
                ciphertext=ciphertext,
                content_digest=protected_digest,
                created_by_user_id=context.user.id,
            )
            session.add(protected_envelope)
            await session.flush()
        prior = None
        if command.supersedes_authority_id is not None:
            prior = await self._by_id(
                session, context.company.id, command.supersedes_authority_id
            )
            if (
                prior is None
                or prior.authority_domain != command.domain.value
                or prior.authority_key != command.authority_key
                or prior.employee_id != command.employee_id
                or prior.lifecycle
                not in {
                    AuthorityLifecycle.APPROVED.value,
                    AuthorityLifecycle.SUPERSEDED.value,
                }
            ):
                raise PayrollConflictError("superseded input authority is out of scope")
        content = self._content(
            company_id=context.company.id,
            command=command,
            protected_digest=protected_digest,
            approved_by_user_id=None,
            approved_at=None,
        )
        value = PayrollInputAuthorityVersion(
            id=uuid4(),
            company_id=context.company.id,
            employee_id=command.employee_id,
            authority_domain=command.domain.value,
            authority_key=command.authority_key.strip(),
            authority_version=command.authority_version,
            definition_version=PAYROLL_INPUT_AUTHORITY_VERSION,
            applicability=command.applicability.value,
            effective_start=command.effective_start,
            effective_end=command.effective_end,
            lifecycle=AuthorityLifecycle.DRAFT.value,
            jurisdiction_reference=command.jurisdiction_reference,
            calculation_basis=command.calculation_basis,
            priority=command.priority,
            public_parameters=dict(command.public_parameters),
            evidence_digest=command.evidence_digest,
            authority_digest=canonical_digest(content),
            protected_envelope_id=(protected_envelope.id if protected_envelope else None),
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
            event_type=EventType.PAYROLL_INPUT_AUTHORITY_DRAFTED,
            action="payroll.input_authority.drafted",
            value=value,
        )
        await session.commit()
        return value

    async def read(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        authority_id: UUID,
    ) -> PayrollInputAuthorityVersion:
        value = await self._by_id(session, context.company.id, authority_id)
        if value is None:
            raise PayrollConflictError("input authority is outside Company scope")
        permission = (
            PayrollPermission.TAX_AUTHORITY_READ
            if value.authority_domain == PayrollInputDomain.TAX.value
            else PayrollPermission.DEDUCTION_AUTHORITY_READ
        )
        self._require(context, permission)
        return value

    async def approve(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        authority_id: UUID,
    ) -> PayrollInputAuthorityVersion:
        value = await self._by_id(session, context.company.id, authority_id)
        if value is None:
            raise PayrollConflictError("input authority is outside Company scope")
        self._require(
            context,
            self._approve_permission(PayrollInputDomain(value.authority_domain)),
        )
        if value.lifecycle != AuthorityLifecycle.DRAFT.value:
            raise PayrollConflictError("only draft input authority may be approved")
        if value.drafted_by_user_id == context.user.id:
            raise PayrollAuthorizationError("input authority drafter cannot self-approve")
        overlaps = await self._overlaps(session, value)
        allowed = {value.supersedes_authority_id} if value.supersedes_authority_id else set()
        if any(item.id not in allowed for item in overlaps):
            raise PayrollConflictError("approved input authority intervals overlap")
        now = datetime.now(timezone.utc)
        value.lifecycle = AuthorityLifecycle.APPROVED.value
        value.approved_by_user_id = context.user.id
        value.approved_at = now
        protected_digest = await self._protected_digest(session, value)
        value.authority_digest = canonical_digest(
            self._record_content(value, protected_digest=protected_digest)
        )
        if value.supersedes_authority_id:
            prior = await self._by_id(
                session, context.company.id, value.supersedes_authority_id
            )
            if prior is None:
                raise PayrollConflictError("superseded authority disappeared")
            prior.lifecycle = AuthorityLifecycle.SUPERSEDED.value
            self._stage(
                session,
                context=context,
                event_type=EventType.PAYROLL_INPUT_AUTHORITY_SUPERSEDED,
                action="payroll.input_authority.superseded",
                value=prior,
            )
        self._stage(
            session,
            context=context,
            event_type=EventType.PAYROLL_INPUT_AUTHORITY_APPROVED,
            action="payroll.input_authority.approved",
            value=value,
        )
        await session.commit()
        return value

    async def retire(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        authority_id: UUID,
    ) -> PayrollInputAuthorityVersion:
        value = await self._by_id(session, context.company.id, authority_id)
        if value is None:
            raise PayrollConflictError("input authority is outside Company scope")
        self._require(
            context,
            self._approve_permission(PayrollInputDomain(value.authority_domain)),
        )
        if value.lifecycle not in {
            AuthorityLifecycle.APPROVED.value,
            AuthorityLifecycle.SUPERSEDED.value,
        }:
            raise PayrollConflictError("only approved authority may be retired")
        value.lifecycle = AuthorityLifecycle.RETIRED.value
        value.retired_by_user_id = context.user.id
        value.retired_at = datetime.now(timezone.utc)
        self._stage(
            session,
            context=context,
            event_type=EventType.PAYROLL_INPUT_AUTHORITY_RETIRED,
            action="payroll.input_authority.retired",
            value=value,
        )
        await session.commit()
        return value

    async def evaluate_admission(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        gross_result_id: UUID,
        as_of_date: date,
        requirements: tuple[AuthorityRequirement, ...],
    ) -> TaxDeductionAdmissionResult:
        self._require(context, PayrollPermission.CALCULATION_READ)
        gross = await session.scalar(
            select(PayrollGrossCalculationResultRecord).where(
                PayrollGrossCalculationResultRecord.company_id == context.company.id,
                PayrollGrossCalculationResultRecord.id == gross_result_id,
            )
        )
        if gross is None or gross.lifecycle not in {
            "calculated",
            "under_review",
            "approved",
        }:
            raise PayrollConflictError("valid gross-pay result is required")
        resolutions = tuple(
            [
                await self._resolve(
                    session,
                    company_id=context.company.id,
                    as_of_date=as_of_date,
                    requirement=requirement,
                )
                for requirement in requirements
            ]
        )
        blocking = tuple(
            item
            for item in resolutions
            if item.requirement.required
            and item.state
            not in {
                TaxDeductionAdmissionState.READY,
                TaxDeductionAdmissionState.NOT_APPLICABLE,
            }
        )
        if not requirements or all(
            item.state is TaxDeductionAdmissionState.NOT_APPLICABLE
            for item in resolutions
        ):
            state = TaxDeductionAdmissionState.NOT_APPLICABLE
        elif not blocking:
            state = TaxDeductionAdmissionState.READY
        else:
            order = (
                TaxDeductionAdmissionState.CONFLICTING,
                TaxDeductionAdmissionState.UNAPPROVED,
                TaxDeductionAdmissionState.EXPIRED,
                TaxDeductionAdmissionState.MISSING,
            )
            state = next(
                candidate
                for candidate in order
                if any(item.state is candidate for item in blocking)
            )
        blockers = tuple(
            f"{item.requirement.domain.value}:{item.requirement.authority_key}:{item.state.value}"
            for item in blocking
        )
        provisional = TaxDeductionAdmissionResult(
            company_id=context.company.id,
            employee_id=gross.employee_id,
            gross_result_id=gross.id,
            gross_calculation_digest=gross.calculation_digest,
            as_of_date=as_of_date,
            definition_version=PAYROLL_TAX_DEDUCTION_ADMISSION_VERSION,
            state=state,
            resolutions=resolutions,
            blockers=blockers,
            admission_digest="",
        )
        result = TaxDeductionAdmissionResult(
            **{
                **provisional.__dict__,
                "admission_digest": canonical_digest(provisional.canonical_content()),
            }
        )
        self._stage_admission(session, context=context, result=result)
        await session.commit()
        return result

    async def _resolve(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        as_of_date: date,
        requirement: AuthorityRequirement,
    ) -> AuthorityResolution:
        values = tuple(
            (
                await session.scalars(
                    select(PayrollInputAuthorityVersion).where(
                        PayrollInputAuthorityVersion.company_id == company_id,
                        PayrollInputAuthorityVersion.employee_id
                        == requirement.employee_id,
                        PayrollInputAuthorityVersion.authority_domain
                        == requirement.domain.value,
                        PayrollInputAuthorityVersion.authority_key
                        == requirement.authority_key,
                    )
                )
            ).all()
        )
        applicable = tuple(
            item
            for item in values
            if item.effective_start <= as_of_date
            and (item.effective_end is None or as_of_date < item.effective_end)
        )
        approved = tuple(
            item
            for item in applicable
            if item.lifecycle in {
                AuthorityLifecycle.APPROVED.value,
                AuthorityLifecycle.SUPERSEDED.value,
            }
        )
        superseded_ids = {
            item.supersedes_authority_id
            for item in approved
            if item.supersedes_authority_id is not None
        }
        active = tuple(item for item in approved if item.id not in superseded_ids)
        if len(active) > 1:
            return AuthorityResolution(
                requirement, TaxDeductionAdmissionState.CONFLICTING, None, None, None,
                ("multiple approved authorities overlap",),
            )
        if len(active) == 1:
            value = active[0]
            protected_digest = await self._protected_digest(session, value)
            if (
                value.definition_version != PAYROLL_INPUT_AUTHORITY_VERSION
                or value.approved_by_user_id is None
                or value.approved_at is None
                or value.authority_digest
                != canonical_digest(
                    self._record_content(
                        value, protected_digest=protected_digest
                    )
                )
            ):
                return AuthorityResolution(
                    requirement,
                    TaxDeductionAdmissionState.CONFLICTING,
                    value.id,
                    value.authority_digest,
                    protected_digest,
                    ("approved authority integrity is invalid",),
                )
            state = (
                TaxDeductionAdmissionState.NOT_APPLICABLE
                if value.applicability == AuthorityApplicability.NOT_APPLICABLE.value
                else TaxDeductionAdmissionState.READY
            )
            return AuthorityResolution(
                requirement,
                state,
                value.id,
                value.authority_digest,
                protected_digest,
                (),
            )
        if applicable:
            return AuthorityResolution(
                requirement, TaxDeductionAdmissionState.UNAPPROVED, None, None, None,
                ("only draft or retired authority is applicable",),
            )
        if values:
            return AuthorityResolution(
                requirement, TaxDeductionAdmissionState.EXPIRED, None, None, None,
                ("no authority applies at the effective date",),
            )
        return AuthorityResolution(
            requirement, TaxDeductionAdmissionState.MISSING, None, None, None,
            ("required authority is absent",),
        )

    async def _overlaps(
        self, session: AsyncSession, value: PayrollInputAuthorityVersion
    ) -> tuple[PayrollInputAuthorityVersion, ...]:
        query = select(PayrollInputAuthorityVersion).where(
            PayrollInputAuthorityVersion.company_id == value.company_id,
            PayrollInputAuthorityVersion.employee_id == value.employee_id,
            PayrollInputAuthorityVersion.authority_domain == value.authority_domain,
            PayrollInputAuthorityVersion.authority_key == value.authority_key,
            PayrollInputAuthorityVersion.lifecycle.in_(("approved", "superseded")),
            PayrollInputAuthorityVersion.id != value.id,
            (
                PayrollInputAuthorityVersion.effective_end.is_(None)
                | (PayrollInputAuthorityVersion.effective_end > value.effective_start)
            ),
        )
        if value.effective_end is not None:
            query = query.where(
                PayrollInputAuthorityVersion.effective_start < value.effective_end
            )
        return tuple((await session.scalars(query)).all())

    @staticmethod
    async def _by_id(
        session: AsyncSession, company_id: UUID, authority_id: UUID
    ) -> PayrollInputAuthorityVersion | None:
        return await session.scalar(
            select(PayrollInputAuthorityVersion).where(
                PayrollInputAuthorityVersion.company_id == company_id,
                PayrollInputAuthorityVersion.id == authority_id,
            )
        )

    @staticmethod
    async def _protected_digest(
        session: AsyncSession, value: PayrollInputAuthorityVersion
    ) -> str | None:
        if value.protected_envelope_id is None:
            return None
        return await session.scalar(
            select(PayrollProtectedInputEnvelope.content_digest).where(
                PayrollProtectedInputEnvelope.company_id == value.company_id,
                PayrollProtectedInputEnvelope.id == value.protected_envelope_id,
            )
        )

    @staticmethod
    def _validate(command: DraftPayrollInputAuthority) -> None:
        if (
            not command.authority_key.strip()
            or command.authority_version < 1
            or not command.evidence_digest
            or not command.audit_reason.strip()
        ):
            raise PayrollAuthorityError("input authority identity is incomplete")
        if command.effective_end is not None and command.effective_end <= command.effective_start:
            raise PayrollAuthorityError("input authority interval is invalid")
        forbidden = {
            "ssn",
            "tin",
            "tax_id",
            "bank_account",
            "routing_number",
            "filing_status",
            "withholding_election",
            "additional_withholding",
            "exemption_election",
        }
        if forbidden.intersection(key.lower() for key in command.public_parameters):
            raise PayrollAuthorityError("protected input cannot enter public parameters")

    @staticmethod
    def _content(
        *,
        company_id: UUID,
        command: DraftPayrollInputAuthority,
        protected_digest: str | None,
        approved_by_user_id: UUID | None,
        approved_at: datetime | None,
    ) -> dict[str, object]:
        return {
            "definition_version": PAYROLL_INPUT_AUTHORITY_VERSION,
            "company_id": str(company_id),
            "employee_id": str(command.employee_id) if command.employee_id else None,
            "domain": command.domain.value,
            "authority_key": command.authority_key.strip(),
            "authority_version": command.authority_version,
            "applicability": command.applicability.value,
            "effective_start": command.effective_start.isoformat(),
            "effective_end": command.effective_end.isoformat() if command.effective_end else None,
            "jurisdiction_reference": command.jurisdiction_reference,
            "calculation_basis": command.calculation_basis,
            "priority": command.priority,
            "public_parameters": command.public_parameters,
            "evidence_digest": command.evidence_digest,
            "protected_input_digest": protected_digest,
            "supersedes_authority_id": str(command.supersedes_authority_id) if command.supersedes_authority_id else None,
            "approved_by_user_id": str(approved_by_user_id) if approved_by_user_id else None,
            "approved_at": approved_at.isoformat() if approved_at else None,
        }

    @classmethod
    def _record_content(
        cls, value: PayrollInputAuthorityVersion, *, protected_digest: str | None
    ) -> dict[str, object]:
        return cls._content(
            company_id=value.company_id,
            command=cls._command_from_record(value),
            protected_digest=protected_digest,
            approved_by_user_id=value.approved_by_user_id,
            approved_at=value.approved_at,
        )

    @staticmethod
    def _command_from_record(
        value: PayrollInputAuthorityVersion,
    ) -> DraftPayrollInputAuthority:
        return DraftPayrollInputAuthority(
            employee_id=value.employee_id,
            domain=PayrollInputDomain(value.authority_domain),
            authority_key=value.authority_key,
            authority_version=value.authority_version,
            applicability=AuthorityApplicability(value.applicability),
            effective_start=value.effective_start,
            effective_end=value.effective_end,
            jurisdiction_reference=value.jurisdiction_reference,
            calculation_basis=value.calculation_basis,
            priority=value.priority,
            public_parameters=value.public_parameters,
            evidence_digest=value.evidence_digest,
            audit_reason=value.audit_reason,
            supersedes_authority_id=value.supersedes_authority_id,
        )

    @staticmethod
    def _manage_permission(domain: PayrollInputDomain) -> str:
        return (
            PayrollPermission.TAX_AUTHORITY_MANAGE
            if domain is PayrollInputDomain.TAX
            else PayrollPermission.DEDUCTION_AUTHORITY_MANAGE
        )

    @staticmethod
    def _approve_permission(domain: PayrollInputDomain) -> str:
        return (
            PayrollPermission.TAX_AUTHORITY_APPROVE
            if domain is PayrollInputDomain.TAX
            else PayrollPermission.DEDUCTION_AUTHORITY_APPROVE
        )

    @staticmethod
    def _require(context: AuthorizationContext, permission: str) -> None:
        if not context.has_permission(permission):
            raise PayrollAuthorizationError("Payroll input authority permission denied")

    def _stage(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        event_type: EventType,
        action: str,
        value: PayrollInputAuthorityVersion,
    ) -> None:
        details: dict[str, object] = {
            "authority_id": str(value.id),
            "domain": value.authority_domain,
            "authority_key": value.authority_key,
            "lifecycle": value.lifecycle,
            "authority_digest": value.authority_digest,
        }
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="payroll_input_authority",
                entity_id=value.id,
                company_id=context.company.id,
                user_id=context.user.id,
                payload=details,
            ),
        )
        self._audit.stage(
            session,
            AuditEntry(
                action=action,
                resource_type="payroll_input_authority",
                actor_user_id=context.user.id,
                company_id=context.company.id,
                resource_id=value.id,
                details=details,
            ),
        )

    def _stage_admission(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        result: TaxDeductionAdmissionResult,
    ) -> None:
        details: dict[str, object] = {
            "admission_digest": result.admission_digest,
            "gross_result_id": str(result.gross_result_id),
            "state": result.state.value,
            "blockers": result.blockers,
        }
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=EventType.PAYROLL_TAX_DEDUCTION_ADMISSION_EVALUATED,
                entity_type="payroll_tax_deduction_admission",
                entity_id=result.gross_result_id,
                company_id=context.company.id,
                user_id=context.user.id,
                payload=details,
            ),
        )
        self._audit.stage(
            session,
            AuditEntry(
                action="payroll.tax_deduction_admission.evaluated",
                resource_type="payroll_tax_deduction_admission",
                actor_user_id=context.user.id,
                company_id=context.company.id,
                resource_id=result.gross_result_id,
                details=details,
            ),
        )
