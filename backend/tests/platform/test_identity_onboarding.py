import asyncio
import base64
import json
import os
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings, settings
from app.payroll.contracts import PayrollAdmissionState, evaluate_payroll_admission
from app.platform.audit.models import AuditRecord
from app.platform.auth.models import EmailVerificationToken  # noqa: F401
from app.platform.auth.passwords import PasswordService
from app.platform.auth.services import CredentialService
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.notifications.models import NotificationOutbox
from app.platform.onboarding.delivery import ProtectedEnvelopeQualificationDelivery
from app.platform.onboarding.models import (
    IdentityOnboardingInvitation,
    IdentityOnboardingRequest,
    ProtectedInvitationDeliveryEnvelope,
)
from app.platform.onboarding.router import _safe_error
from app.platform.onboarding.service import (
    IdentityOnboardingService,
    OnboardingAuthorizationError,
    OnboardingCommand,
    OnboardingConflictError,
    ProtectedInvitationDelivery,
)
from app.platform.permissions.codes import AdministrationPermission
from app.platform.permissions.models import (
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.users.models import User, UserCredential
from app.timekeeping.repository import timekeeping_repository


class Context:
    def __init__(
        self,
        company: Company,
        branch: Branch,
        user: User,
        membership: Membership,
        allowed: bool = True,
    ) -> None:
        self.company, self.active_branch, self.user, self.membership = (
            company,
            branch,
            user,
            membership,
        )
        self.permission_codes = (
            frozenset({AdministrationPermission.IDENTITY_ONBOARDING_MANAGE})
            if allowed
            else frozenset()
        )

    def has_permission(self, code: str) -> bool:
        return code in self.permission_codes

    def can_access_branch(self, branch_id: UUID) -> bool:
        return branch_id == self.active_branch.id


@pytest.mark.parametrize(
    ("error", "status_code", "code", "recovery"),
    (
        (
            OnboardingAuthorizationError("protected authority detail"),
            403,
            "forbidden",
            "OWNER_ADMIN_ACTION_REQUIRED",
        ),
        (
            OnboardingConflictError("protected token/provider detail"),
            409,
            "resource_state_conflict",
            "RETRY_AFTER_REFRESH",
        ),
    ),
)
def test_onboarding_errors_use_safe_recovery_contract(
    error: Exception, status_code: int, code: str, recovery: str
) -> None:
    translated = _safe_error(error)
    assert translated.status_code == status_code
    assert translated.detail["code"] == code
    assert translated.detail["recovery"] == recovery
    assert translated.detail["correlation_id"] is None
    assert str(error) not in str(translated.detail)


@pytest_asyncio.fixture
async def onboarding_db() -> AsyncIterator[
    tuple[async_sessionmaker[AsyncSession], Context, IdentityOnboardingService]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    company = Company(
        id=uuid4(),
        name=f"Onboarding {uuid4()}",
        code=f"ONB{uuid4().hex[:8].upper()}",
        status="active",
        timezone="America/New_York",
    )
    branch = Branch(
        id=uuid4(),
        company_id=company.id,
        name="Main",
        code="MAIN",
        status="active",
        timezone="America/New_York",
        is_primary=True,
    )
    admin = User(
        id=uuid4(),
        normalized_email=f"admin-{uuid4()}@example.test",
        first_name="Admin",
        last_name="Owner",
        display_name="Admin Owner",
        status="active",
        email_verified_at=datetime.now(timezone.utc),
    )
    membership = Membership(
        id=uuid4(),
        user_id=admin.id,
        company_id=company.id,
        status="active",
        default_branch_id=branch.id,
        has_all_branch_access=True,
    )
    async with factory() as session, session.begin():
        session.add_all([company, branch, admin, membership])
    key = base64.urlsafe_b64encode(b"k" * 32).decode()
    config = Settings(
        environment="test",
        database_url=settings.database_url,
        identity_onboarding_delivery_keys={"test-v1": key},
        identity_onboarding_active_delivery_kid="test-v1",
    )
    yield (
        factory,
        Context(company, branch, admin, membership),
        IdentityOnboardingService(config),
    )
    await engine.dispose()


def command(
    context: Context,
    *,
    request_key: str = "request-1",
    email: str | None = None,
    existing_user_id: UUID | None = None,
    role_ids: tuple[UUID, ...] = (),
    additional_permission_ids: tuple[UUID, ...] = (),
) -> OnboardingCommand:
    return OnboardingCommand(
        request_key=request_key,
        branch_id=context.active_branch.id,
        first_name="Synthetic",
        last_name="Employee",
        display_name="Synthetic Employee",
        employee_type="employee",
        employee_number_prefix="EMP-",
        employee_number_width=4,
        role_ids=role_ids,
        additional_permission_ids=additional_permission_ids,
        login_email=email,
        existing_user_id=existing_user_id,
    )


@pytest.mark.asyncio
async def test_onboarding_plan_detects_new_and_duplicate_identity_without_mutation(
    onboarding_db: tuple[
        async_sessionmaker[AsyncSession], Context, IdentityOnboardingService
    ],
) -> None:
    factory, context, service = onboarding_db
    role = Role(
        company_id=context.company.id,
        code=f"PLAN_ROLE_{uuid4().hex[:10].upper()}",
        name="Synthetic planning role",
        status="active",
        is_system=True,
    )
    async with factory() as setup, setup.begin():
        setup.add(role)
    email = f"plan-{uuid4()}@example.test"
    async with factory() as session:
        plan = await service.plan(
            session,
            context=context,
            branch_id=context.active_branch.id,
            login_email=email,
            role_ids=(role.id,),
            additional_permission_ids=(),
        )
        assert plan.classification == "NEW_EMPLOYEE_CANDIDATE"
        assert plan.safe_to_apply
        assert plan.readiness_stages["INVITATION"] == "PROVIDER_REQUIRED"
        assert not await session.scalar(
            select(User.id).where(User.normalized_email == email)
        )
        await session.rollback()

        created = await service.initiate(
            session,
            context=context,
            command=command(
                context,
                request_key=f"plan-apply-{uuid4()}",
                email=email,
                role_ids=(role.id,),
            ),
        )
        duplicate = await service.plan(
            session,
            context=context,
            branch_id=context.active_branch.id,
            login_email=email,
            role_ids=(role.id,),
            additional_permission_ids=(),
        )
        assert duplicate.classification == "DUPLICATE_CONFLICT"
        assert not duplicate.safe_to_apply
        assert duplicate.blockers == ("employee_identity_already_exists",)
        assert created.employee_id is not None


@pytest.mark.asyncio
async def test_explicit_employee_permission_profile_is_additive_replay_safe(
    onboarding_db: tuple[
        async_sessionmaker[AsyncSession], Context, IdentityOnboardingService
    ],
) -> None:
    factory, context, service = onboarding_db
    permission = Permission(
        code=f"TEST_EMPLOYEE_ADD_{uuid4().hex[:12].upper()}",
        name="Synthetic additive Employee permission",
        resource="synthetic_employee",
        action="read",
        status="active",
    )
    async with factory() as setup, setup.begin():
        setup.add(permission)

    email = f"employee-profile-{uuid4()}@example.test"
    profile_command = command(
        context,
        request_key=f"profile-{uuid4()}",
        email=email,
        additional_permission_ids=(permission.id,),
    )
    async with factory() as session:
        created = await service.initiate(
            session, context=context, command=profile_command
        )
        replay = await service.initiate(
            session, context=context, command=profile_command
        )
        assert replay.id == created.id
        profile_roles = tuple(
            await session.scalars(
                select(Role)
                .join(MembershipRole, MembershipRole.role_id == Role.id)
                .where(
                    MembershipRole.membership_id == created.membership_id,
                    Role.code.like("EMPLOYEE_PROFILE_%"),
                )
            )
        )
        assert len(profile_roles) == 1
        assert await session.scalar(
            select(RolePermission.id).where(
                RolePermission.role_id == profile_roles[0].id,
                RolePermission.permission_id == permission.id,
            )
        )
        user = await session.get(User, created.user_id)
        assert user is not None and user.authorization_version == 2


@pytest.mark.asyncio
async def test_explicit_employee_permission_profile_rejects_unknown_permission(
    onboarding_db: tuple[
        async_sessionmaker[AsyncSession], Context, IdentityOnboardingService
    ],
) -> None:
    factory, context, service = onboarding_db
    async with factory() as session:
        with pytest.raises(OnboardingConflictError):
            await service.initiate(
                session,
                context=context,
                command=command(
                    context,
                    request_key=f"unknown-permission-{uuid4()}",
                    email=f"unknown-permission-{uuid4()}@example.test",
                    additional_permission_ids=(uuid4(),),
                ),
            )
        assert not await session.scalar(
            select(IdentityOnboardingRequest.id).where(
                IdentityOnboardingRequest.company_id == context.company.id,
                IdentityOnboardingRequest.request_key.like("unknown-permission-%"),
            )
        )


@pytest.mark.asyncio
async def test_invitation_activation_is_single_use_and_secret_safe(
    onboarding_db: tuple[
        async_sessionmaker[AsyncSession], Context, IdentityOnboardingService
    ],
) -> None:
    factory, context, service = onboarding_db
    email = f"employee-{uuid4()}@example.test"
    async with factory() as session:
        result = await service.initiate(
            session, context=context, command=command(context, email=email)
        )
        replay = await service.initiate(
            session, context=context, command=command(context, email=email)
        )
        assert replay.id == result.id
        invitation = await session.scalar(
            select(IdentityOnboardingInvitation).where(
                IdentityOnboardingInvitation.onboarding_request_id == result.id
            )
        )
        envelope = await session.scalar(
            select(ProtectedInvitationDeliveryEnvelope).where(
                ProtectedInvitationDeliveryEnvelope.invitation_id == invitation.id
            )
        )
        assert invitation is not None and envelope is not None
        assert email.encode() not in envelope.ciphertext
        assert invitation.token_hash.encode() not in envelope.ciphertext
        outbox = await session.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.notification_type == "identity.onboarding_invitation"
            )
        )
        assert outbox is not None
        durable_delivery = json.dumps(outbox.payload, sort_keys=True)
        assert invitation.token_hash not in durable_delivery
        invitation_id = invitation.id
        await session.rollback()
        delivery = await service.claim_protected_delivery(
            session, invitation_id=invitation_id
        )
        assert delivery.recipient == email
        await service.complete_protected_delivery(session, invitation_id=invitation.id)
        activated = await service.activate(
            session, token=delivery.secret, password="A-secure-test-passphrase-42!"
        )
        assert activated.status == "activated"
        activated_user_id = activated.user_id
        employee = await timekeeping_repository.employee_for_membership(
            session,
            company_id=context.company.id,
            membership_id=activated.membership_id,
        )
        assert employee is not None and employee.employee_number == "EMP-0001"
        await session.rollback()
        with pytest.raises(OnboardingConflictError):
            await service.activate(
                session,
                token=delivery.secret,
                password="Another-secure-test-passphrase-42!",
            )
        assert await session.scalar(
            select(UserCredential.id).where(UserCredential.user_id == activated_user_id)
        )
        admission = evaluate_payroll_admission(
            company_id=context.company.id,
            identity_resolved=True,
            policy=None,
            compensation=None,
            time_input=None,
        )
        assert admission.state is PayrollAdmissionState.BLOCKED_POLICY


@pytest.mark.asyncio
async def test_owner_claim_reuses_protected_boundary_and_is_single_use(
    onboarding_db: tuple[
        async_sessionmaker[AsyncSession], Context, IdentityOnboardingService
    ],
) -> None:
    factory, context, service = onboarding_db
    async with factory() as session:
        record = await service.initiate(
            session,
            context=context,
            command=command(context, email=f"owner-claim-{uuid4()}@example.test"),
        )
        request_id = record.id
        delivery = await service.claim_protected_delivery_for_owner(
            session,
            context=context,
            request_id=request_id,
        )
        envelope = await session.scalar(
            select(ProtectedInvitationDeliveryEnvelope)
            .join(IdentityOnboardingInvitation)
            .where(IdentityOnboardingInvitation.onboarding_request_id == request_id)
        )
        assert envelope is not None and envelope.status == "delivered"
        assert envelope.ciphertext == b""
        assert envelope.nonce == b""
        assert envelope.destroyed_at is not None
        audit = await session.scalar(
            select(AuditRecord).where(
                AuditRecord.action == "identity.onboarding_owner_claimed",
                AuditRecord.resource_id == request_id,
            )
        )
        assert audit is not None
        assert audit.actor_user_id == context.user.id
        assert audit.company_id == context.company.id
        assert audit.branch_id == context.active_branch.id
        assert audit.details == {"invitation_id": str(delivery.invitation_id)}
        assert delivery.secret not in str(audit.details)
        await session.rollback()
        with pytest.raises(OnboardingConflictError):
            await service.claim_protected_delivery_for_owner(
                session,
                context=context,
                request_id=request_id,
            )
        audits = (
            await session.scalars(
                select(AuditRecord).where(
                    AuditRecord.action == "identity.onboarding_owner_claimed",
                    AuditRecord.resource_id == request_id,
                )
            )
        ).all()
        assert len(audits) == 1
        await session.rollback()
        activated = await service.activate(
            session,
            token=delivery.secret,
            password="A-secure-owner-claim-passphrase-42!",
        )
        assert activated.status == "activated"
        await session.refresh(envelope)
        assert envelope.status == "destroyed"
        assert envelope.ciphertext == b""


@pytest.mark.asyncio
async def test_concurrent_owner_claim_has_one_winner_and_one_audit(
    onboarding_db: tuple[
        async_sessionmaker[AsyncSession], Context, IdentityOnboardingService
    ],
) -> None:
    factory, context, service = onboarding_db
    async with factory() as setup:
        record = await service.initiate(
            setup,
            context=context,
            command=command(
                context,
                email=f"owner-claim-race-{uuid4()}@example.test",
            ),
        )
        request_id = record.id

    async def claim() -> ProtectedInvitationDelivery:
        async with factory() as session:
            return await service.claim_protected_delivery_for_owner(
                session,
                context=context,
                request_id=request_id,
            )

    outcomes = await asyncio.gather(claim(), claim(), return_exceptions=True)
    deliveries = [
        outcome
        for outcome in outcomes
        if isinstance(outcome, ProtectedInvitationDelivery)
    ]
    conflicts = [
        outcome for outcome in outcomes if isinstance(outcome, OnboardingConflictError)
    ]
    assert len(deliveries) == len(conflicts) == 1

    async with factory() as verification:
        envelopes = (
            await verification.scalars(
                select(ProtectedInvitationDeliveryEnvelope)
                .join(IdentityOnboardingInvitation)
                .where(IdentityOnboardingInvitation.onboarding_request_id == request_id)
            )
        ).all()
        audits = (
            await verification.scalars(
                select(AuditRecord).where(
                    AuditRecord.action == "identity.onboarding_owner_claimed",
                    AuditRecord.resource_id == request_id,
                )
            )
        ).all()
        assert len(envelopes) == 1
        assert envelopes[0].status == "delivered"
        assert envelopes[0].ciphertext == b""
        assert envelopes[0].nonce == b""
        assert envelopes[0].destroyed_at is not None
        assert len(audits) == 1
        assert deliveries[0].secret not in str(audits[0].details)


@pytest.mark.asyncio
async def test_owner_claim_requires_permission_scope_and_non_production(
    onboarding_db: tuple[
        async_sessionmaker[AsyncSession], Context, IdentityOnboardingService
    ],
) -> None:
    factory, context, service = onboarding_db
    async with factory() as session:
        record = await service.initiate(
            session,
            context=context,
            command=command(
                context, email=f"owner-claim-guards-{uuid4()}@example.test"
            ),
        )
        request_id = record.id
        denied = Context(
            context.company,
            context.active_branch,
            context.user,
            context.membership,
            False,
        )
        with pytest.raises(OnboardingAuthorizationError):
            await service.claim_protected_delivery_for_owner(
                session, context=denied, request_id=request_id
            )

        inaccessible = Context(
            context.company,
            Branch(id=uuid4(), company_id=context.company.id),
            context.user,
            context.membership,
        )
        with pytest.raises(OnboardingConflictError):
            await service.claim_protected_delivery_for_owner(
                session, context=inaccessible, request_id=request_id
            )
        for operation in (service.get, service.revoke, service.reissue):
            with pytest.raises(OnboardingConflictError):
                await operation(
                    session,
                    context=inaccessible,
                    request_id=request_id,
                )
            await session.rollback()
        preserved = await service.get(
            session,
            context=context,
            request_id=request_id,
        )
        assert preserved.status == "invited"
        await session.rollback()

        production = IdentityOnboardingService(
            service.configuration.model_copy(update={"environment": "production"})
        )
        with pytest.raises(OnboardingConflictError):
            await production.claim_protected_delivery_for_owner(
                session, context=context, request_id=request_id
            )


@pytest.mark.asyncio
async def test_initiate_rejects_valid_but_unauthorized_company_branch(
    onboarding_db: tuple[
        async_sessionmaker[AsyncSession], Context, IdentityOnboardingService
    ],
) -> None:
    factory, context, service = onboarding_db
    foreign_branch = Branch(
        id=uuid4(),
        company_id=context.company.id,
        name="Restricted",
        code=f"R{uuid4().hex[:7].upper()}",
        status="active",
        timezone="America/New_York",
        is_primary=False,
    )
    async with factory() as session:
        session.add(foreign_branch)
        await session.commit()
        request_key = f"foreign-branch-{uuid4()}"
        attempted = replace(
            command(
                context,
                request_key=request_key,
                email=f"foreign-branch-{uuid4()}@example.test",
            ),
            branch_id=foreign_branch.id,
        )
        with pytest.raises(OnboardingConflictError, match="Branch"):
            await service.initiate(session, context=context, command=attempted)
        assert (
            await session.scalar(
                select(IdentityOnboardingRequest.id).where(
                    IdentityOnboardingRequest.company_id == context.company.id,
                    IdentityOnboardingRequest.request_key == request_key,
                )
            )
            is None
        )


@pytest.mark.asyncio
async def test_database_rejects_cross_company_onboarding_branch(
    onboarding_db: tuple[
        async_sessionmaker[AsyncSession], Context, IdentityOnboardingService
    ],
) -> None:
    factory, context, service = onboarding_db
    async with factory() as session:
        record = await service.initiate(
            session,
            context=context,
            command=command(
                context,
                request_key=f"constraint-{uuid4()}",
                email=f"constraint-{uuid4()}@example.test",
            ),
        )
        other_company = Company(
            id=uuid4(),
            name=f"Other {uuid4()}",
            code=f"O{uuid4().hex[:8].upper()}",
            status="active",
            timezone="America/New_York",
        )
        other_branch = Branch(
            id=uuid4(),
            company_id=other_company.id,
            name="Other",
            code="OTHER",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        session.add_all([other_company, other_branch])
        await session.commit()
        with pytest.raises(IntegrityError):
            async with session.begin():
                await session.execute(
                    update(IdentityOnboardingRequest)
                    .where(IdentityOnboardingRequest.id == record.id)
                    .values(branch_id=other_branch.id)
                )
        constraint_names = set(
            (
                await session.scalars(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conrelid = "
                        "'identity_onboarding_requests'::regclass"
                    )
                )
            ).all()
        )
        assert {
            "fk_identity_onboarding_request_company_branch",
            "fk_identity_onboarding_request_company_employee",
        } <= constraint_names


@pytest.mark.asyncio
async def test_contradictory_replay_and_unauthorized_are_rejected(
    onboarding_db: tuple[
        async_sessionmaker[AsyncSession], Context, IdentityOnboardingService
    ],
) -> None:
    factory, context, service = onboarding_db
    async with factory() as session:
        await service.initiate(
            session,
            context=context,
            command=command(context, email=f"one-{uuid4()}@example.test"),
        )
        with pytest.raises(OnboardingConflictError):
            await service.initiate(
                session,
                context=context,
                command=command(context, email=f"two-{uuid4()}@example.test"),
            )
        denied = Context(
            context.company,
            context.active_branch,
            context.user,
            context.membership,
            False,
        )
        with pytest.raises(OnboardingAuthorizationError):
            await service.initiate(
                session,
                context=denied,
                command=command(
                    denied, request_key="denied", email=f"denied-{uuid4()}@example.test"
                ),
            )


@pytest.mark.asyncio
async def test_employee_number_allocation_is_concurrent_and_never_reuses(
    onboarding_db: tuple[
        async_sessionmaker[AsyncSession], Context, IdentityOnboardingService
    ],
) -> None:
    factory, context, service = onboarding_db

    async def initiate(request_key: str) -> UUID:
        async with factory() as session:
            record = await service.initiate(
                session,
                context=context,
                command=command(
                    context,
                    request_key=request_key,
                    email=f"{request_key}-{uuid4()}@example.test",
                ),
            )
            return record.employee_id

    employee_ids = await asyncio.gather(
        initiate("concurrent-a"), initiate("concurrent-b")
    )
    async with factory() as session:
        employees = list(
            (
                await session.scalars(
                    select(Employee).where(Employee.id.in_(employee_ids))
                )
            ).all()
        )
        allocated = {employee.employee_number for employee in employees}
        assert len(allocated) == 2
        archived_number = employees[0].employee_number
        employees[0].archived_at = datetime.now(timezone.utc)
        await session.commit()
        next_record = await service.initiate(
            session,
            context=context,
            command=command(
                context,
                request_key="after-archive",
                email=f"after-archive-{uuid4()}@example.test",
            ),
        )
        next_employee = await session.get(Employee, next_record.employee_id)
        assert next_employee is not None
        assert next_employee.employee_number not in allocated
        assert next_employee.employee_number != archived_number


@pytest.mark.asyncio
async def test_concurrent_exact_initiation_replays_one_authority(
    onboarding_db: tuple[
        async_sessionmaker[AsyncSession], Context, IdentityOnboardingService
    ],
) -> None:
    factory, context, service = onboarding_db
    request_key = f"concurrent-exact-{uuid4()}"
    exact_command = command(
        context,
        request_key=request_key,
        email=f"{request_key}@example.test",
    )

    async def initiate() -> IdentityOnboardingRequest:
        async with factory() as session:
            return await service.initiate(
                session,
                context=context,
                command=exact_command,
            )

    first, second = await asyncio.gather(initiate(), initiate())
    assert first.id == second.id
    assert first.employee_id == second.employee_id
    assert first.membership_id == second.membership_id

    async with factory() as session:
        records = list(
            (
                await session.scalars(
                    select(IdentityOnboardingRequest).where(
                        IdentityOnboardingRequest.company_id == context.company.id,
                        IdentityOnboardingRequest.request_key == request_key,
                    )
                )
            ).all()
        )
        assert [record.id for record in records] == [first.id]


@pytest.mark.asyncio
async def test_reissue_supersedes_and_revoke_destroys_envelopes(
    onboarding_db: tuple[
        async_sessionmaker[AsyncSession], Context, IdentityOnboardingService
    ],
) -> None:
    factory, context, service = onboarding_db
    async with factory() as session:
        record = await service.initiate(
            session,
            context=context,
            command=command(context, email=f"reissue-{uuid4()}@example.test"),
        )
        first = await session.scalar(
            select(IdentityOnboardingInvitation).where(
                IdentityOnboardingInvitation.onboarding_request_id == record.id
            )
        )
        assert first is not None
        record_id = record.id
        await session.rollback()
        await service.reissue(session, context=context, request_id=record_id)
        await session.refresh(first)
        assert first.status == "superseded" and first.superseded_by_id is not None
        await session.rollback()
        await service.revoke(session, context=context, request_id=record_id)
        invitations = list(
            (
                await session.scalars(
                    select(IdentityOnboardingInvitation).where(
                        IdentityOnboardingInvitation.onboarding_request_id == record.id
                    )
                )
            ).all()
        )
        assert {value.status for value in invitations} == {"superseded", "revoked"}
        envelopes = list(
            (
                await session.scalars(
                    select(ProtectedInvitationDeliveryEnvelope)
                    .join(IdentityOnboardingInvitation)
                    .where(
                        IdentityOnboardingInvitation.onboarding_request_id == record.id
                    )
                )
            ).all()
        )
        assert all(value.ciphertext == b"" for value in envelopes)


@pytest.mark.asyncio
async def test_existing_verified_user_is_reused_without_credential_change(
    onboarding_db: tuple[
        async_sessionmaker[AsyncSession], Context, IdentityOnboardingService
    ],
) -> None:
    factory, context, service = onboarding_db
    password_service = PasswordService()
    async with factory() as session:
        credential = CredentialService(password_service).build_initial_credential(
            user_id=context.user.id,
            password="Existing-secure-passphrase-42!",
            now=datetime.now(timezone.utc),
        )
        session.add(credential)
        await session.commit()
        original_hash = credential.password_hash
        record = await service.initiate(
            session,
            context=context,
            command=command(context, existing_user_id=context.user.id),
        )
        record_id = record.id
        assert (
            record.status == "activated"
            and record.user_id == context.user.id
            and record.membership_id == context.membership.id
        )
        stored = await session.scalar(
            select(UserCredential).where(UserCredential.user_id == context.user.id)
        )
        assert stored is not None and stored.password_hash == original_hash
        assert (
            await session.scalar(
                select(IdentityOnboardingInvitation.id).where(
                    IdentityOnboardingInvitation.onboarding_request_id == record_id
                )
            )
            is None
        )


@pytest.mark.asyncio
async def test_expired_and_cross_company_scope_fail_closed(
    onboarding_db: tuple[
        async_sessionmaker[AsyncSession], Context, IdentityOnboardingService
    ],
) -> None:
    factory, context, service = onboarding_db
    async with factory() as session:
        record = await service.initiate(
            session,
            context=context,
            command=command(context, email=f"expired-{uuid4()}@example.test"),
        )
        record_id = record.id
        invitation = await session.scalar(
            select(IdentityOnboardingInvitation).where(
                IdentityOnboardingInvitation.onboarding_request_id == record_id
            )
        )
        assert invitation is not None
        invitation_id = invitation.id
        await session.rollback()
        delivery = await service.claim_protected_delivery(
            session, invitation_id=invitation_id
        )
        invitation = await session.get(IdentityOnboardingInvitation, invitation_id)
        assert invitation is not None
        invitation.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()
        with pytest.raises(OnboardingConflictError):
            await service.activate(
                session, token=delivery.secret, password="A-secure-test-passphrase-42!"
            )
        expired = await session.get(IdentityOnboardingInvitation, invitation_id)
        assert expired is not None and expired.status == "expired"
        other_company = SimpleNamespace(id=uuid4())
        wrong = Context(
            other_company, context.active_branch, context.user, context.membership
        )  # type: ignore[arg-type]
        with pytest.raises(OnboardingConflictError):
            await service.initiate(
                session,
                context=wrong,
                command=command(
                    context, request_key="cross", email=f"cross-{uuid4()}@example.test"
                ),
            )


def test_protected_key_file_permissions_and_delivery_readiness(tmp_path) -> None:
    key = base64.urlsafe_b64encode(b"q" * 32).decode()
    keyring = tmp_path / "identity-delivery-keyring.json"
    keyring.write_text(json.dumps({"file-v1": key}), encoding="utf-8")
    os.chmod(keyring, 0o600)
    configured = Settings(
        environment="test",
        database_url=settings.database_url,
        identity_onboarding_delivery_key_file=str(keyring),
        identity_onboarding_active_delivery_kid="file-v1",
    )
    readiness = IdentityOnboardingService(configured).delivery_runtime_readiness()
    assert readiness.envelope_runtime == "delivery_runtime_ready"
    assert (
        readiness.external_provider
        == "external_delivery_provider_configuration_required"
    )
    os.chmod(keyring, 0o644)
    with pytest.raises(OnboardingConflictError, match="not configured"):
        IdentityOnboardingService(configured).delivery_runtime_readiness()


def test_delivery_readiness_fails_closed_without_key_material() -> None:
    configured = Settings(
        environment="test",
        database_url=settings.database_url,
        identity_onboarding_delivery_keys={},
        identity_onboarding_delivery_key_file=None,
        identity_onboarding_active_delivery_kid="missing-v1",
    )
    with pytest.raises(OnboardingConflictError, match="not configured"):
        IdentityOnboardingService(configured).delivery_runtime_readiness()


@pytest.mark.asyncio
async def test_nonproduction_delivery_qualification_sends_nothing_and_is_safe(
    onboarding_db: tuple[
        async_sessionmaker[AsyncSession], Context, IdentityOnboardingService
    ],
) -> None:
    factory, context, service = onboarding_db
    async with factory() as session:
        record = await service.initiate(
            session,
            context=context,
            command=command(
                context,
                request_key="delivery-qualification",
                email=f"qualification-{uuid4()}@example.test",
            ),
        )
        invitation = await session.scalar(
            select(IdentityOnboardingInvitation).where(
                IdentityOnboardingInvitation.onboarding_request_id == record.id
            )
        )
        assert invitation is not None
        invitation_id = invitation.id
        await session.rollback()
        result = await ProtectedEnvelopeQualificationDelivery(service).qualify(
            session, invitation_id=invitation_id
        )
        assert result.status == "qualified_without_external_delivery"
        assert not hasattr(result, "secret")
        envelope = await session.scalar(
            select(ProtectedInvitationDeliveryEnvelope).where(
                ProtectedInvitationDeliveryEnvelope.invitation_id == invitation_id
            )
        )
        assert envelope is not None
        assert envelope.status == "delivered"
        assert envelope.ciphertext == b"" and envelope.nonce == b""
