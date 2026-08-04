import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import app.platform.permissions.models  # noqa: F401
import pytest
import pytest_asyncio
from app.core.config import settings
from app.engineering_control.commands import (
    ApproveEngineeringCommand,
    CancelEngineeringCommand,
    CreateEngineeringCommand,
    EngineeringCommandQuery,
    ExpireEngineeringCommand,
)
from app.engineering_control.errors import (
    EngineeringCommandApprovalMismatchError,
    EngineeringCommandExpirationError,
    EngineeringCommandExpiredError,
    EngineeringCommandIdempotencyConflictError,
    EngineeringCommandLifecycleError,
    EngineeringCommandRepositoryPolicyError,
    EngineeringCommandStaleVersionError,
    EngineeringCommandUnsafeInstructionError,
    EngineeringCommandValidationError,
)
from app.engineering_control.models import EngineeringCommand, EngineeringCommandEvent
from app.engineering_control.records import (
    EngineeringApprovalState,
    EngineeringExecutionState,
)
from app.engineering_control.registry import (
    EngineeringRepositoryDefinition,
    EngineeringRepositoryRegistry,
    engineering_repository_registry,
)
from app.engineering_control.service import EngineeringControlService
from app.events.models import BusinessEvent
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.platform.audit.models import AuditRecord
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.permissions.authorization import (
    AuthorizationContext,
    AuthorizedCompany,
    AuthorizedMembership,
    AuthorizedPermission,
    AuthorizedUser,
)
from app.platform.permissions.codes import EngineeringCommandPermission
from app.platform.users.models import User
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ServiceFixture:
    factory: async_sessionmaker[AsyncSession]
    context: AuthorizationContext
    other_context: AuthorizationContext


def context_with_permissions(
    user: User | AuthorizedUser,
    company: Company | AuthorizedCompany,
    membership: Membership | AuthorizedMembership,
    permission_codes: tuple[str, ...],
) -> AuthorizationContext:
    now = utc_now()
    permissions = tuple(
        AuthorizedPermission(
            id=uuid4(),
            code=code,
            name=code,
            description=None,
            resource="engineering_command",
            action=code.rsplit("_", 1)[-1].lower(),
            status="active",
            created_at=now,
            updated_at=now,
            retired_at=None,
        )
        for code in permission_codes
    )
    return AuthorizationContext(
        user=user,
        company=company,
        membership=membership,
        authorized_branches=(),
        active_branch=None,
        effective_roles=(),
        effective_permissions=permissions,
        credential_version=1,
        authorization_version=1,
    )


async def seed_service_fixture(
    factory: async_sessionmaker[AsyncSession],
) -> ServiceFixture:
    now = utc_now()
    user = User(
        id=uuid4(),
        normalized_email=f"{uuid4().hex}@example.com",
        first_name="Engineering",
        last_name="Owner",
        display_name="Engineering Owner",
        status="active",
    )
    other_user = User(
        id=uuid4(),
        normalized_email=f"{uuid4().hex}@example.com",
        first_name="Other",
        last_name="Owner",
        display_name="Other Owner",
        status="active",
    )
    company = Company(
        id=uuid4(),
        name="Engineering Service Company",
        code=f"ES{uuid4().hex[:8].upper()}",
        status="active",
        timezone="America/New_York",
    )
    other_company = Company(
        id=uuid4(),
        name="Other Engineering Service Company",
        code=f"EO{uuid4().hex[:8].upper()}",
        status="active",
        timezone="America/New_York",
    )
    membership = Membership(
        id=uuid4(),
        user_id=user.id,
        company_id=company.id,
        status="active",
        accepted_at=now,
        has_all_branch_access=True,
    )
    other_membership = Membership(
        id=uuid4(),
        user_id=other_user.id,
        company_id=other_company.id,
        status="active",
        accepted_at=now,
        has_all_branch_access=True,
    )
    async with factory() as session, session.begin():
        session.add_all(
            [user, other_user, company, other_company, membership, other_membership]
        )
    all_permissions = tuple(EngineeringCommandPermission.ALL)
    return ServiceFixture(
        factory,
        context_with_permissions(user, company, membership, all_permissions),
        context_with_permissions(
            other_user, other_company, other_membership, all_permissions
        ),
    )


@pytest_asyncio.fixture
async def service_database() -> AsyncIterator[ServiceFixture]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    fixture = await seed_service_fixture(factory)
    try:
        yield fixture
    finally:
        await engine.dispose()


def create_input(
    *,
    now: datetime,
    idempotency_key: str | None = None,
    instruction: str = "Inspect and update only the approved service files.",
    branch: str = "customer-management-v1",
    head: str = "a" * 40,
    repository_key: str = "acp-enterprise",
    requested_code_changes: bool = True,
    command_type: str = "owner_instruction",
) -> CreateEngineeringCommand:
    return CreateEngineeringCommand(
        command_type=command_type,
        owner_instruction=instruction,
        repository_key=repository_key,
        expected_branch=branch,
        expected_head=head,
        requested_code_changes=requested_code_changes,
        expires_at=now + timedelta(hours=2),
        idempotency_key=idempotency_key or uuid4().hex,
        execution_boundary={
            "allowed_repository": repository_key,
            "allowed_branch": branch,
            "expected_head": head,
            "allowed_paths": ["backend/app/**"],
            "forbidden_paths": [".git/**", ".env*", "**/.env*"],
            "permitted_operations": [
                "inspect",
                "validate",
                *(["modify", "commit"] if requested_code_changes else []),
            ],
            "validation_requirements": ["git diff --check"],
        },
    )


@pytest.mark.asyncio
async def test_creation_stages_command_event_audit_and_business_event(
    service_database: ServiceFixture,
) -> None:
    fixture = service_database
    now = utc_now()
    async with fixture.factory() as session:
        record = await EngineeringControlService().create_command(
            session,
            context=fixture.context,
            command=create_input(now=now),
            now=now,
        )
    assert record.ecid.startswith(f"ECID-{now.year}-")
    assert record.approval_state is EngineeringApprovalState.AWAITING_APPROVAL
    assert record.execution_state is EngineeringExecutionState.EXECUTION_NOT_CONNECTED
    assert record.instruction_digest == record.instruction_digest.lower()
    async with fixture.factory() as session:
        events = (
            await session.scalars(
                select(EngineeringCommandEvent).where(
                    EngineeringCommandEvent.command_id == record.id
                )
            )
        ).all()
        audits = (
            await session.scalars(
                select(AuditRecord).where(AuditRecord.resource_id == record.id)
            )
        ).all()
        business = (
            await session.scalars(
                select(BusinessEvent).where(BusinessEvent.entity_id == record.id)
            )
        ).all()
    assert [event.event_type for event in events] == ["command_created"]
    assert [audit.action for audit in audits] == ["engineering.command_created"]
    assert [event.event_type for event in business] == ["engineering.command_created"]
    assert record.owner_instruction not in str(audits[0].details)
    assert record.owner_instruction not in str(business[0].payload)


@pytest.mark.asyncio
async def test_creation_idempotency_replay_conflict_and_concurrency(
    service_database: ServiceFixture,
) -> None:
    fixture = service_database
    now = utc_now()
    key = uuid4().hex
    command = create_input(now=now, idempotency_key=key)
    service = EngineeringControlService()
    async with fixture.factory() as session:
        first = await service.create_command(
            session, context=fixture.context, command=command, now=now
        )
    async with fixture.factory() as session:
        replay = await service.create_command(
            session, context=fixture.context, command=command, now=now
        )
    assert replay == first
    async with fixture.factory() as session:
        with pytest.raises(EngineeringCommandIdempotencyConflictError):
            await service.create_command(
                session,
                context=fixture.context,
                command=create_input(
                    now=now,
                    idempotency_key=key,
                    instruction="Inspect a different approved boundary.",
                ),
                now=now,
            )

    concurrent_key = uuid4().hex
    concurrent_command = create_input(now=now, idempotency_key=concurrent_key)

    async def create() -> UUID:
        async with fixture.factory() as session:
            result = await service.create_command(
                session,
                context=fixture.context,
                command=concurrent_command,
                now=now,
            )
            return result.id

    assert len(set(await asyncio.gather(create(), create()))) == 1
    async with fixture.factory() as session:
        count = await session.scalar(
            select(func.count(EngineeringCommandEvent.id))
            .join(
                EngineeringCommand,
                EngineeringCommand.id == EngineeringCommandEvent.command_id,
            )
            .where(EngineeringCommand.idempotency_key == concurrent_key)
        )
    assert count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"repository_key": "unknown"}, EngineeringCommandRepositoryPolicyError),
        ({"branch": "other"}, EngineeringCommandRepositoryPolicyError),
        ({"head": "A" * 40}, EngineeringCommandValidationError),
        ({"instruction": "   "}, EngineeringCommandValidationError),
    ],
)
async def test_creation_validates_repository_and_input(
    service_database: ServiceFixture,
    changes: dict[str, object],
    error: type[Exception],
) -> None:
    now = utc_now()
    with pytest.raises(error):
        async with service_database.factory() as session:
            await EngineeringControlService().create_command(
                session,
                context=service_database.context,
                command=create_input(now=now, **changes),  # type: ignore[arg-type]
                now=now,
            )


@pytest.mark.asyncio
async def test_read_only_inspection_requires_explicit_branch_allowlist(
    service_database: ServiceFixture,
) -> None:
    definition = engineering_repository_registry.resolve("acp-enterprise")
    registry = EngineeringRepositoryRegistry(
        (
            EngineeringRepositoryDefinition(
                **{
                    **definition.__dict__,
                    "approved_inspection_branches": (
                        "df9-authenticated-live-worker-runtime",
                    ),
                }
            ),
        )
    )
    service = EngineeringControlService(registry=registry)
    now = utc_now()
    async with service_database.factory() as session:
        record = await service.create_command(
            session,
            context=service_database.context,
            command=create_input(
                now=now,
                branch="df9-authenticated-live-worker-runtime",
                command_type="inspect_workspace",
                requested_code_changes=False,
            ),
            now=now,
        )
    assert record.expected_branch == "df9-authenticated-live-worker-runtime"
    assert record.requested_code_changes is False
    async with service_database.factory() as session:
        approved = await service.approve_command(
            session,
            context=service_database.context,
            command=ApproveEngineeringCommand(
                command_id=record.id,
                expected_version=record.version,
                instruction_digest=record.instruction_digest,
                request_digest=record.request_digest,
                repository_key=record.repository_key,
                expected_branch=record.expected_branch,
                expected_head=record.expected_head,
                requested_code_changes=record.requested_code_changes,
            ),
            now=now + timedelta(seconds=1),
        )
    assert approved.approval_state is EngineeringApprovalState.APPROVED

    for command in (
        create_input(
            now=now,
            branch="df9-authenticated-live-worker-runtime",
            requested_code_changes=True,
            command_type="inspect_workspace",
        ),
        create_input(
            now=now,
            branch="df9-authenticated-live-worker-runtime",
            requested_code_changes=False,
            command_type="owner_instruction",
        ),
    ):
        with pytest.raises(EngineeringCommandRepositoryPolicyError):
            async with service_database.factory() as session:
                await service.create_command(
                    session,
                    context=service_database.context,
                    command=command,
                    now=now,
                )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "instruction",
    [
        "password=supersecret",
        "Authorization: Bearer abcdefghijklmnop",
        "-----BEGIN PRIVATE KEY-----",
        "Commit these changes and push them.",
        "git merge another-branch",
        "Deploy this to production.",
        "Remove the infrastructure.",
        "Read files from ../../private.",
    ],
)
async def test_creation_rejects_secret_and_privileged_instructions(
    service_database: ServiceFixture, instruction: str
) -> None:
    now = utc_now()
    async with service_database.factory() as session:
        with pytest.raises(EngineeringCommandUnsafeInstructionError):
            await EngineeringControlService().create_command(
                session,
                context=service_database.context,
                command=create_input(now=now, instruction=instruction),
                now=now,
            )


@pytest.mark.asyncio
async def test_expiration_bounds_are_enforced(
    service_database: ServiceFixture,
) -> None:
    now = utc_now()
    base = create_input(now=now)
    for expiration in (now, now + timedelta(days=8)):
        invalid = CreateEngineeringCommand(
            **{**base.__dict__, "expires_at": expiration}
        )
        async with service_database.factory() as session:
            with pytest.raises(EngineeringCommandExpirationError):
                await EngineeringControlService().create_command(
                    session,
                    context=service_database.context,
                    command=invalid,
                    now=now,
                )


@pytest.mark.asyncio
async def test_service_listing_paginates_filters_and_is_company_scoped(
    service_database: ServiceFixture,
) -> None:
    fixture = service_database
    service = EngineeringControlService()
    now = utc_now()
    created = []
    for index in range(5):
        async with fixture.factory() as session:
            created.append(
                await service.create_command(
                    session,
                    context=fixture.context,
                    command=create_input(now=now + timedelta(seconds=index)),
                    now=now + timedelta(seconds=index),
                )
            )
    async with fixture.factory() as session:
        approved = await service.approve_command(
            session,
            context=fixture.context,
            command=ApproveEngineeringCommand(
                command_id=created[2].id,
                expected_version=created[2].version,
                instruction_digest=created[2].instruction_digest,
                request_digest=created[2].request_digest,
                repository_key=created[2].repository_key,
                expected_branch=created[2].expected_branch,
                expected_head=created[2].expected_head,
                requested_code_changes=created[2].requested_code_changes,
            ),
            now=now + timedelta(minutes=1),
        )
    async with fixture.factory() as session:
        default_page = await service.list_commands(session, context=fixture.context)
    async with fixture.factory() as session:
        second_page = await service.list_commands(
            session,
            context=fixture.context,
            query=EngineeringCommandQuery(page=2, page_size=2),
        )
    async with fixture.factory() as session:
        final_page = await service.list_commands(
            session,
            context=fixture.context,
            query=EngineeringCommandQuery(page=3, page_size=2),
        )
    async with fixture.factory() as session:
        beyond = await service.list_commands(
            session,
            context=fixture.context,
            query=EngineeringCommandQuery(page=8, page_size=2),
        )
    async with fixture.factory() as session:
        filtered = await service.list_commands(
            session,
            context=fixture.context,
            query=EngineeringCommandQuery(
                approval_state=EngineeringApprovalState.APPROVED,
                page=1,
                page_size=10,
            ),
        )
    async with fixture.factory() as session:
        other = await service.list_commands(session, context=fixture.other_context)

    assert default_page.page == 1
    assert default_page.page_size == 50
    assert default_page.total_count == 5
    assert default_page.total_pages == 1
    assert [item.id for item in default_page.items] == [
        item.id for item in reversed(created)
    ]
    assert second_page.total_count == 5
    assert second_page.total_pages == 3
    assert len(second_page.items) == 2
    assert len(final_page.items) == 1
    assert beyond.items == ()
    assert beyond.total_count == 5
    assert filtered.items == (approved,)
    assert filtered.total_count == filtered.total_pages == 1
    assert other.items == ()
    assert other.total_count == other.total_pages == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        EngineeringCommandQuery(page=0),
        EngineeringCommandQuery(page_size=0),
        EngineeringCommandQuery(page_size=201),
    ],
)
async def test_service_listing_rejects_invalid_pagination(
    service_database: ServiceFixture, query: EngineeringCommandQuery
) -> None:
    async with service_database.factory() as session:
        with pytest.raises(EngineeringCommandValidationError):
            await EngineeringControlService().list_commands(
                session, context=service_database.context, query=query
            )


@pytest.mark.asyncio
async def test_approval_cancellation_and_expiration_stage_evidence(
    service_database: ServiceFixture,
) -> None:
    fixture = service_database
    now = utc_now()
    service = EngineeringControlService()
    async with fixture.factory() as session:
        created = await service.create_command(
            session,
            context=fixture.context,
            command=create_input(now=now),
            now=now,
        )
    approval = ApproveEngineeringCommand(
        command_id=created.id,
        expected_version=1,
        instruction_digest=created.instruction_digest,
        request_digest=created.request_digest,
        repository_key=created.repository_key,
        expected_branch=created.expected_branch,
        expected_head=created.expected_head,
        requested_code_changes=created.requested_code_changes,
    )
    async with fixture.factory() as session:
        approved = await service.approve_command(
            session,
            context=fixture.context,
            command=approval,
            now=now + timedelta(minutes=1),
        )
    assert approved.approval_state is EngineeringApprovalState.APPROVED
    assert approved.version == 2
    assert approved.execution_state is EngineeringExecutionState.EXECUTION_NOT_CONNECTED
    async with fixture.factory() as session:
        replay = await service.approve_command(
            session,
            context=fixture.context,
            command=approval,
            now=now + timedelta(minutes=2),
        )
    assert replay == approved

    async with fixture.factory() as session:
        canceled = await service.cancel_command(
            session,
            context=fixture.context,
            command=CancelEngineeringCommand(
                command_id=approved.id,
                expected_version=2,
                reason_code="owner_requested",
            ),
            now=now + timedelta(minutes=3),
        )
    assert canceled.approval_state is EngineeringApprovalState.CANCELED
    assert canceled.version == 3
    async with fixture.factory() as session:
        repeated = await service.cancel_command(
            session,
            context=fixture.context,
            command=CancelEngineeringCommand(
                command_id=approved.id,
                expected_version=2,
                reason_code="owner_requested",
            ),
            now=now + timedelta(minutes=4),
        )
    assert repeated == canceled
    async with fixture.factory() as session:
        with pytest.raises(EngineeringCommandLifecycleError):
            await service.expire_command(
                session,
                context=fixture.context,
                command=ExpireEngineeringCommand(
                    command_id=canceled.id, expected_version=3
                ),
                now=created.expires_at,
            )

    async with fixture.factory() as session:
        expiring = await service.create_command(
            session,
            context=fixture.context,
            command=create_input(now=now),
            now=now,
        )
    async with fixture.factory() as session:
        expired = await service.expire_command(
            session,
            context=fixture.context,
            command=ExpireEngineeringCommand(
                command_id=expiring.id, expected_version=1
            ),
            now=expiring.expires_at,
        )
    assert expired.approval_state is EngineeringApprovalState.EXPIRED
    assert expired.execution_state is EngineeringExecutionState.EXECUTION_NOT_CONNECTED
    async with fixture.factory() as session:
        event_types = (
            await session.scalars(
                select(EngineeringCommandEvent.event_type)
                .where(
                    EngineeringCommandEvent.command_id.in_((created.id, expiring.id))
                )
                .order_by(EngineeringCommandEvent.occurred_at)
            )
        ).all()
    assert "command_approved" in event_types
    assert "command_canceled" in event_types
    assert "command_expired" in event_types


@pytest.mark.asyncio
async def test_approval_mismatch_stale_and_expired_fail_closed(
    service_database: ServiceFixture,
) -> None:
    fixture = service_database
    now = utc_now()
    service = EngineeringControlService()
    async with fixture.factory() as session:
        created = await service.create_command(
            session,
            context=fixture.context,
            command=create_input(now=now),
            now=now,
        )
    base = ApproveEngineeringCommand(
        command_id=created.id,
        expected_version=1,
        instruction_digest=created.instruction_digest,
        request_digest=created.request_digest,
        repository_key=created.repository_key,
        expected_branch=created.expected_branch,
        expected_head=created.expected_head,
        requested_code_changes=created.requested_code_changes,
    )
    mismatches = (
        {"instruction_digest": "b" * 64},
        {"request_digest": "d" * 64},
        {"repository_key": "unapproved-repository"},
        {"expected_branch": "other"},
        {"expected_head": "c" * 40},
        {"requested_code_changes": not created.requested_code_changes},
    )
    async with fixture.factory() as session:
        evidence_before = (
            await session.scalar(
                select(func.count(EngineeringCommandEvent.id)).where(
                    EngineeringCommandEvent.command_id == created.id
                )
            ),
            await session.scalar(
                select(func.count(AuditRecord.id)).where(
                    AuditRecord.company_id == created.company_id
                )
            ),
            await session.scalar(
                select(func.count(BusinessEvent.id)).where(
                    BusinessEvent.company_id == created.company_id
                )
            ),
        )
    for changes in mismatches:
        async with fixture.factory() as session:
            with pytest.raises(EngineeringCommandApprovalMismatchError):
                await service.approve_command(
                    session,
                    context=fixture.context,
                    command=ApproveEngineeringCommand(**{**base.__dict__, **changes}),
                    now=now + timedelta(minutes=1),
                )
    async with fixture.factory() as session:
        unchanged = await service.get_command(
            session, context=fixture.context, command_id=created.id
        )
        evidence_after = (
            await session.scalar(
                select(func.count(EngineeringCommandEvent.id)).where(
                    EngineeringCommandEvent.command_id == created.id
                )
            ),
            await session.scalar(
                select(func.count(AuditRecord.id)).where(
                    AuditRecord.company_id == created.company_id
                )
            ),
            await session.scalar(
                select(func.count(BusinessEvent.id)).where(
                    BusinessEvent.company_id == created.company_id
                )
            ),
        )
    assert unchanged.approval_state is EngineeringApprovalState.AWAITING_APPROVAL
    assert unchanged.version == 1
    assert (
        unchanged.execution_state is EngineeringExecutionState.EXECUTION_NOT_CONNECTED
    )
    assert evidence_after == evidence_before
    async with fixture.factory() as session:
        with pytest.raises(EngineeringCommandExpiredError):
            await service.approve_command(
                session,
                context=fixture.context,
                command=base,
                now=created.expires_at,
            )
    stale = ApproveEngineeringCommand(**{**base.__dict__, "expected_version": 2})
    async with fixture.factory() as session:
        with pytest.raises(EngineeringCommandStaleVersionError):
            await service.approve_command(
                session,
                context=fixture.context,
                command=stale,
                now=now + timedelta(minutes=1),
            )


class FailingBusinessEvents(BusinessEventService):
    @staticmethod
    def stage(session: AsyncSession, event_data: BusinessEventCreate) -> BusinessEvent:
        raise RuntimeError("controlled Business Event staging failure")


@pytest.mark.asyncio
async def test_transaction_rolls_back_when_evidence_staging_fails(
    service_database: ServiceFixture,
) -> None:
    fixture = service_database
    service = EngineeringControlService(business_events=FailingBusinessEvents)
    async with fixture.factory() as session:
        with pytest.raises(RuntimeError, match="controlled"):
            await service.create_command(
                session,
                context=fixture.context,
                command=create_input(now=utc_now()),
            )
    async with fixture.factory() as session:
        assert (
            await session.scalar(
                select(func.count(EngineeringCommand.id)).where(
                    EngineeringCommand.company_id == fixture.context.company.id
                )
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count(EngineeringCommandEvent.id)).where(
                    EngineeringCommandEvent.company_id == fixture.context.company.id
                )
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count(AuditRecord.id)).where(
                    AuditRecord.company_id == fixture.context.company.id
                )
            )
            == 0
        )
