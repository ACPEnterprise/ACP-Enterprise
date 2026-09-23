import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from app.core.config import settings
from app.customer_migration.models import (
    CustomerMigrationCandidate,
    CustomerMigrationSourceArtifact,
    CustomerMigrationSourceRow,
    CustomerPopulationReconciliationCommand,
    CustomerPopulationReconciliationDisposition,
    CustomerPopulationRefreshRun,
    CustomerSourceIdentity,
)
from app.customer_migration.population_reconciliation import (
    CustomerPopulationReconciliationError,
    CustomerPopulationReconciliationService,
    ExactCustomerAdmissionCommand,
)
from app.customer_migration.population_router import (
    get_population_session_factory,
)
from app.customer_migration.population_router import (
    router as population_router,
)
from app.customers.models import Customer, CustomerContact, ServiceLocation
from app.customers.repository import CustomerRepository
from app.customers.schemas import (
    ContactCreate,
    CustomerCreate,
    CustomerRecordState,
    CustomerSearchQuery,
    CustomerStatus,
    CustomerType,
    ServiceLocationCreate,
)
from app.database.session import get_database_session
from app.events.models import BusinessEvent
from app.operational_migration.models import HcpMigrationMasterRun  # noqa: F401
from app.platform.audit.models import AuditRecord
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.idempotency.models import MutationReceipt
from app.platform.permissions.authorization import (
    AuthorizationContext,
    PermissionDeniedError,
)
from app.platform.permissions.codes import CustomerPermission
from app.platform.permissions.dependencies import get_authorization_context
from app.platform.permissions.models import Permission
from app.platform.users.models import User
from fastapi import FastAPI
from scripts.customer_population_reconciliation import (
    execute_action as execute_reconciliation_action,
)
from scripts.customer_population_reconciliation import parser as reconciliation_parser
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

HAMMER_PROVIDER_ID = "147405829"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@pytest_asyncio.fixture
async def database() -> AsyncIterator[
    tuple[AsyncEngine, async_sessionmaker[AsyncSession]]
]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        await engine.dispose()


async def seed_context(
    factory: async_sessionmaker[AsyncSession], *, name: str
) -> AuthorizationContext:
    suffix = uuid4().hex[:8]
    async with factory() as session, session.begin():
        permission = await session.scalar(
            select(Permission).where(Permission.code == CustomerPermission.MANAGE)
        )
        if permission is None:
            permission = Permission(
                code=CustomerPermission.MANAGE,
                name="Manage Customers",
                description="Synthetic reconciliation qualification authority",
                resource="customer",
                action="manage",
                status="active",
            )
            session.add(permission)
            await session.flush()
        user = User(
            normalized_email=f"reconciliation-{suffix}@example.test",
            first_name="Synthetic",
            last_name="Owner",
            display_name="Synthetic Owner",
            status="active",
        )
        company = Company(
            name=name,
            code=f"RC{suffix}".upper(),
            status="active",
            timezone="America/New_York",
        )
        session.add_all([user, company])
        await session.flush()
        branch = Branch(
            company_id=company.id,
            name="MAIN",
            code="MAIN",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        session.add(branch)
        await session.flush()
        membership = Membership(
            user_id=user.id,
            company_id=company.id,
            status="active",
            default_branch_id=branch.id,
            has_all_branch_access=True,
        )
        session.add(membership)
        await session.flush()
    return AuthorizationContext(
        user=user,
        company=company,
        membership=membership,
        authorized_branches=(branch,),
        active_branch=branch,
        effective_roles=(),
        effective_permissions=(permission,),
        credential_version=1,
        authorization_version=1,
    )


def population_app(
    factory: async_sessionmaker[AsyncSession],
    context: AuthorizationContext | None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(population_router)

    async def database_override() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_database_session] = database_override
    app.dependency_overrides[get_population_session_factory] = lambda: factory
    if context is not None:

        async def context_override() -> AuthorizationContext:
            return context

        app.dependency_overrides[get_authorization_context] = context_override
    return app


def hammer_aggregate() -> tuple[
    CustomerCreate,
    ContactCreate,
    tuple[ServiceLocationCreate, ServiceLocationCreate],
]:
    return (
        CustomerCreate(
            customer_type=CustomerType.RESIDENTIAL,
            display_name="Hammer Haag",
            status=CustomerStatus.ACTIVE,
        ),
        ContactCreate(
            first_name="Hammer",
            last_name="Haag",
            email="hammer.haag@example.test",
            is_preferred=True,
        ),
        (
            ServiceLocationCreate(
                address="101 Exact Provider Way",
                city="Tampa",
                state="FL",
                postal_code="33601",
                country="US",
            ),
            ServiceLocationCreate(
                address="202 Exact Provider Way",
                city="Tampa",
                state="FL",
                postal_code="33602",
                country="US",
            ),
        ),
    )


async def stage_hammer(
    factory: async_sessionmaker[AsyncSession],
    context: AuthorizationContext,
    *,
    provider_id: str = HAMMER_PROVIDER_ID,
) -> CustomerMigrationSourceArtifact:
    assert context.active_branch is not None
    customer, contact, locations = hammer_aggregate()
    source_sha256 = digest(
        f"authoritative-hcp-artifact:{context.company.id}:{provider_id}"
    )
    source_row_sha256 = digest(f"authoritative-hcp-row:{provider_id}")
    async with factory() as session, session.begin():
        artifact = CustomerMigrationSourceArtifact(
            company_id=context.company.id,
            branch_id=context.active_branch.id,
            source_system="housecall_pro",
            source_sha256=source_sha256,
            schema_version="housecall_pro_customer_451_v1",
            transformation_sha256=digest("registered-hcp-transformation"),
            byte_size=1024,
            row_count=1,
        )
        session.add(artifact)
        await session.flush()
        source_row = CustomerMigrationSourceRow(
            artifact_id=artifact.id,
            row_number=2,
            source_identity=provider_id,
            source_id_sha256=digest(provider_id),
            source_row_sha256=source_row_sha256,
            disposition="accepted",
        )
        session.add(source_row)
        await session.flush()
        values = [
            ("customer", 0, customer),
            ("contact", 0, contact),
            *(
                ("service_location", index, item)
                for index, item in enumerate(locations)
            ),
        ]
        for entity_type, ordinal, model in values:
            payload = model.model_dump(mode="json")
            session.add(
                CustomerMigrationCandidate(
                    source_row_id=source_row.id,
                    entity_type=entity_type,
                    ordinal=ordinal,
                    payload_sha256=hashlib.sha256(
                        json.dumps(payload, sort_keys=True).encode()
                    ).hexdigest(),
                    payload=payload,
                )
            )
    return artifact


@pytest.mark.asyncio
async def test_http_population_refresh_is_authorized_replay_safe_and_non_admitting(
    database,
) -> None:
    _, factory = database
    context = await seed_context(factory, name="Population Refresh API")
    await stage_hammer(factory, context)
    app = population_app(factory, context)

    async def refresh() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.post(
                "/api/v1/customer-migration/population/refresh",
                json={"source_system": "housecall_pro"},
                headers={"Idempotency-Key": "population-refresh-network-retry"},
            )

    first, concurrent_replay = await asyncio.gather(refresh(), refresh())
    assert first.status_code == concurrent_replay.status_code == 200
    assert first.json()["run_id"] == concurrent_replay.json()["run_id"]
    assert first.json()["receipt_id"] == concurrent_replay.json()["receipt_id"]
    assert {first.json()["replay"], concurrent_replay.json()["replay"]} == {
        "executed",
        "replayed",
    }
    assert first.json()["counts"] == {
        "total": 1,
        "bound": 0,
        "held": 0,
        "ambiguous": 0,
        "unexplained": 1,
    }
    assert first.json()["customer_admission_performed"] is False
    assert first.headers["Cache-Control"] == "private, no-store"

    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Customer)
                .where(Customer.company_id == context.company.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerContact)
                .join(Customer, Customer.id == CustomerContact.customer_id)
                .where(Customer.company_id == context.company.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ServiceLocation)
                .join(Customer, Customer.id == ServiceLocation.customer_id)
                .where(Customer.company_id == context.company.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerSourceIdentity)
                .where(CustomerSourceIdentity.company_id == context.company.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerPopulationReconciliationDisposition)
                .where(
                    CustomerPopulationReconciliationDisposition.company_id
                    == context.company.id
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerPopulationRefreshRun)
                .where(CustomerPopulationRefreshRun.company_id == context.company.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MutationReceipt)
                .where(
                    MutationReceipt.company_id == context.company.id,
                    MutationReceipt.operation
                    == "customer_population_reconciliation.refresh",
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuditRecord)
                .where(
                    AuditRecord.company_id == context.company.id,
                    AuditRecord.action
                    == "customer_population_reconciliation.refreshed",
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BusinessEvent)
                .where(BusinessEvent.company_id == context.company.id)
            )
            == 0
        )

    restricted = replace(context, effective_permissions=())
    restricted_app = population_app(factory, restricted)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restricted_app), base_url="http://test"
    ) as client:
        denied = await client.post(
            "/api/v1/customer-migration/population/refresh",
            json={"source_system": "housecall_pro"},
            headers={"Idempotency-Key": "population-refresh-network-retry"},
        )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Permission denied."


@pytest.mark.asyncio
async def test_http_clean_majority_admits_exact_rows_and_is_replay_safe(database) -> None:
    _, factory = database
    context = await seed_context(factory, name="Clean Majority API")
    await stage_hammer(factory, context)
    app = population_app(factory, context)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post(
            "/api/v1/customer-migration/population/admit-clean-majority",
            json={"source_system": "housecall_pro", "limit": 5000},
        )
        replay = await client.post(
            "/api/v1/customer-migration/population/admit-clean-majority",
            json={"source_system": "housecall_pro", "limit": 5000},
        )

    assert first.status_code == replay.status_code == 200
    assert first.json()["selected"] == first.json()["admitted"] == 1
    assert first.json()["quarantined"] == 0
    assert first.json()["remaining_unexplained"] == 0
    assert first.json()["customer_admission_performed"] is True
    assert first.headers["Cache-Control"] == "private, no-store"
    assert replay.json()["selected"] == replay.json()["admitted"] == 0
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Customer)
                .where(Customer.company_id == context.company.id)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_concurrent_distinct_refresh_commands_converge_without_admission(
    database,
) -> None:
    _, factory = database
    context = await seed_context(factory, name="Distinct Population Refresh")
    await stage_hammer(factory, context)
    app = population_app(factory, context)

    async def refresh(key: str) -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.post(
                "/api/v1/customer-migration/population/refresh",
                json={"source_system": "housecall_pro"},
                headers={"Idempotency-Key": key},
            )

    first, second = await asyncio.gather(
        refresh("population-refresh-distinct-one"),
        refresh("population-refresh-distinct-two"),
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["replay"] == second.json()["replay"] == "executed"
    assert first.json()["run_id"] != second.json()["run_id"]

    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerPopulationReconciliationDisposition)
                .where(
                    CustomerPopulationReconciliationDisposition.company_id
                    == context.company.id
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerPopulationRefreshRun)
                .where(CustomerPopulationRefreshRun.company_id == context.company.id)
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Customer)
                .where(Customer.company_id == context.company.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerSourceIdentity)
                .where(CustomerSourceIdentity.company_id == context.company.id)
            )
            == 0
        )


@pytest.mark.asyncio
async def test_http_population_refresh_conflicting_branch_and_tenant_scope(
    database,
) -> None:
    _, factory = database
    context = await seed_context(factory, name="Population Refresh Scope")
    assert context.active_branch is not None
    await stage_hammer(factory, context)
    app = population_app(factory, context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post(
            "/api/v1/customer-migration/population/refresh",
            json={"source_system": "housecall_pro"},
            headers={"Idempotency-Key": "population-refresh-scoped-key"},
        )
    assert first.status_code == 200

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        unsupported_source = await client.post(
            "/api/v1/customer-migration/population/refresh",
            json={"source_system": "quickbooks"},
            headers={"Idempotency-Key": "population-refresh-scoped-key"},
        )
    assert unsupported_source.status_code == 422

    async with factory() as session, session.begin():
        branch = Branch(
            company_id=context.company.id,
            name="OTHER",
            code=f"OTHER-{uuid4().hex[:8].upper()}",
            status="active",
            timezone="America/New_York",
            is_primary=False,
        )
        session.add(branch)
        await session.flush()
    other_branch_context = replace(
        context,
        authorized_branches=(context.active_branch, branch),
        active_branch=branch,
    )
    branch_app = population_app(factory, other_branch_context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=branch_app), base_url="http://test"
    ) as client:
        conflict = await client.post(
            "/api/v1/customer-migration/population/refresh",
            json={"source_system": "housecall_pro"},
            headers={"Idempotency-Key": "population-refresh-scoped-key"},
        )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"

    other_context = await seed_context(factory, name="Other Population Tenant")
    other_app = population_app(factory, other_context)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=other_app), base_url="http://test"
    ) as client:
        isolated = await client.post(
            "/api/v1/customer-migration/population/refresh",
            json={"source_system": "housecall_pro"},
            headers={"Idempotency-Key": "population-refresh-scoped-key"},
        )
    assert isolated.status_code == 200
    assert isolated.json()["run_id"] != first.json()["run_id"]
    assert isolated.json()["counts"]["total"] == 0


def command(
    artifact: CustomerMigrationSourceArtifact, *, key: str
) -> ExactCustomerAdmissionCommand:
    return ExactCustomerAdmissionCommand(
        source_system="housecall_pro",
        source_customer_id=HAMMER_PROVIDER_ID,
        source_artifact_id=artifact.id,
        expected_source_sha256=artifact.source_sha256,
        expected_source_row_sha256=digest(
            f"authoritative-hcp-row:{HAMMER_PROVIDER_ID}"
        ),
        expected_customers=1,
        expected_contacts=1,
        expected_service_locations=2,
        expected_billing_addresses=0,
        idempotency_key=key,
        reason_code="owner_accepted_exact_provider_admission",
    )


@pytest.mark.asyncio
async def test_hammer_exact_admission_is_searchable_and_replay_safe(database) -> None:
    _, factory = database
    context = await seed_context(factory, name="Hammer Qualification Company")
    artifact = await stage_hammer(factory, context)
    service = CustomerPopulationReconciliationService()

    before = await service.refresh_population(factory, context=context)
    assert before.counts.total == 1
    assert before.counts.unexplained == 1

    request = command(artifact, key="hammer-haag-exact-admission")
    first = await service.admit_exact(factory, context=context, command=request)
    async with factory() as session:
        initial = {
            "customers": int(
                await session.scalar(
                    select(func.count())
                    .select_from(Customer)
                    .where(Customer.company_id == context.company.id)
                )
                or 0
            ),
            "contacts": int(
                await session.scalar(
                    select(func.count())
                    .select_from(CustomerContact)
                    .where(CustomerContact.customer_id == first.customer_id)
                )
                or 0
            ),
            "locations": int(
                await session.scalar(
                    select(func.count())
                    .select_from(ServiceLocation)
                    .where(ServiceLocation.customer_id == first.customer_id)
                )
                or 0
            ),
            "events": int(
                await session.scalar(
                    select(func.count())
                    .select_from(BusinessEvent)
                    .where(BusinessEvent.company_id == context.company.id)
                )
                or 0
            ),
            "audits": int(
                await session.scalar(
                    select(func.count())
                    .select_from(AuditRecord)
                    .where(AuditRecord.company_id == context.company.id)
                )
                or 0
            ),
            "dispositions": int(
                await session.scalar(
                    select(func.count())
                    .select_from(CustomerPopulationReconciliationDisposition)
                    .where(
                        CustomerPopulationReconciliationDisposition.company_id
                        == context.company.id
                    )
                )
                or 0
            ),
        }
    replay = await service.admit_exact(factory, context=context, command=request)
    assert replay.replayed is True
    assert replay.customer_id == first.customer_id
    async with factory() as session:
        binding = await session.scalar(
            select(CustomerSourceIdentity).where(
                CustomerSourceIdentity.company_id == context.company.id,
                CustomerSourceIdentity.source_system == "housecall_pro",
                CustomerSourceIdentity.source_customer_id == HAMMER_PROVIDER_ID,
            )
        )
        assert binding is not None and binding.customer_id == first.customer_id
        disposition = await session.get(
            CustomerPopulationReconciliationDisposition, first.disposition_id
        )
        assert disposition is not None
        assert disposition.source_artifact_id == artifact.id
        assert disposition.source_customer_id == HAMMER_PROVIDER_ID
        assert disposition.source_row_sha256 == digest(
            f"authoritative-hcp-row:{HAMMER_PROVIDER_ID}"
        )
        after = {
            "customers": int(
                await session.scalar(
                    select(func.count())
                    .select_from(Customer)
                    .where(Customer.company_id == context.company.id)
                )
                or 0
            ),
            "contacts": int(
                await session.scalar(
                    select(func.count())
                    .select_from(CustomerContact)
                    .where(CustomerContact.customer_id == first.customer_id)
                )
                or 0
            ),
            "locations": int(
                await session.scalar(
                    select(func.count())
                    .select_from(ServiceLocation)
                    .where(ServiceLocation.customer_id == first.customer_id)
                )
                or 0
            ),
            "events": int(
                await session.scalar(
                    select(func.count())
                    .select_from(BusinessEvent)
                    .where(BusinessEvent.company_id == context.company.id)
                )
                or 0
            ),
            "audits": int(
                await session.scalar(
                    select(func.count())
                    .select_from(AuditRecord)
                    .where(AuditRecord.company_id == context.company.id)
                )
                or 0
            ),
            "dispositions": int(
                await session.scalar(
                    select(func.count())
                    .select_from(CustomerPopulationReconciliationDisposition)
                    .where(
                        CustomerPopulationReconciliationDisposition.company_id
                        == context.company.id
                    )
                )
                or 0
            ),
        }
        assert after == initial
        assert initial["customers"] == 1
        assert initial["contacts"] == 1
        assert initial["locations"] == 2
        for query in ("Hammer Haag", "hammer haag", "Hammer", "Haag"):
            rows, total = await CustomerRepository.search_customers(
                session,
                company_id=context.company.id,
                criteria=CustomerSearchQuery(query=query),
            )
            assert total == 1 and rows[0].id == first.customer_id
        _, archived_total = await CustomerRepository.search_customers(
            session,
            company_id=context.company.id,
            criteria=CustomerSearchQuery(
                query="Hammer", record_state=CustomerRecordState.ARCHIVED
            ),
        )
        assert archived_total == 0

    refreshed = await service.refresh_population(factory, context=context)
    assert refreshed.counts.bound == 1
    assert refreshed.counts.unexplained == 0


@pytest.mark.asyncio
async def test_clean_majority_admits_safe_customer_and_quarantines_only_conflict(
    database,
) -> None:
    _, factory = database
    context = await seed_context(factory, name="Clean Majority Company")
    safe_provider_id = "safe-provider-100"
    conflict_provider_id = "conflict-provider-200"
    await stage_hammer(factory, context, provider_id=safe_provider_id)
    conflict_artifact = await stage_hammer(
        factory, context, provider_id=conflict_provider_id
    )
    async with factory() as session, session.begin():
        conflict_row = await session.scalar(
            select(CustomerMigrationSourceRow).where(
                CustomerMigrationSourceRow.artifact_id == conflict_artifact.id,
                CustomerMigrationSourceRow.source_identity == conflict_provider_id,
            )
        )
        assert conflict_row is not None
        await session.execute(
            delete(CustomerMigrationCandidate).where(
                CustomerMigrationCandidate.source_row_id == conflict_row.id,
                CustomerMigrationCandidate.entity_type == "customer",
            )
        )

    service = CustomerPopulationReconciliationService()
    result = await service.admit_clean_majority(factory, context=context)
    assert result.selected == 2
    assert result.admitted == 1
    assert result.replayed == 0
    assert result.quarantined == 1
    assert result.remaining_unexplained == 0
    assert result.before_digest != result.after_digest

    async with factory() as session:
        binding = await session.scalar(
            select(CustomerSourceIdentity).where(
                CustomerSourceIdentity.company_id == context.company.id,
                CustomerSourceIdentity.source_customer_id == safe_provider_id,
            )
        )
        assert binding is not None
        latest_conflict = await session.scalar(
            select(CustomerPopulationReconciliationDisposition)
            .where(
                CustomerPopulationReconciliationDisposition.company_id
                == context.company.id,
                CustomerPopulationReconciliationDisposition.source_customer_id
                == conflict_provider_id,
            )
            .order_by(CustomerPopulationReconciliationDisposition.version.desc())
            .limit(1)
        )
        assert latest_conflict is not None
        assert latest_conflict.disposition == "HELD"
        assert (
            latest_conflict.reason_code == "source_aggregate_validation_required"
        )

    replay = await service.admit_clean_majority(factory, context=context)
    assert replay.selected == 0
    assert replay.admitted == replay.replayed == replay.quarantined == 0
    assert replay.remaining_unexplained == 0


@pytest.mark.asyncio
async def test_contradictory_replay_and_tenant_crossing_fail_closed(database) -> None:
    _, factory = database
    first_context = await seed_context(factory, name="First Tenant")
    second_context = await seed_context(factory, name="Second Tenant")
    artifact = await stage_hammer(factory, first_context)
    service = CustomerPopulationReconciliationService()
    request = command(artifact, key="tenant-exact-admission")
    await service.admit_exact(factory, context=first_context, command=request)

    with pytest.raises(CustomerPopulationReconciliationError, match="conflicts"):
        await service.admit_exact(
            factory,
            context=first_context,
            command=replace(request, expected_service_locations=1),
        )
    with pytest.raises(CustomerPopulationReconciliationError, match="scope"):
        await service.admit_exact(
            factory,
            context=second_context,
            command=replace(request, idempotency_key="other-tenant-attempt"),
        )
    async with factory() as session:
        second_count = int(
            await session.scalar(
                select(func.count())
                .select_from(Customer)
                .where(Customer.company_id == second_context.company.id)
            )
            or 0
        )
        assert second_count == 0


@pytest.mark.asyncio
async def test_hold_is_durable_and_prevents_admission(database) -> None:
    _, factory = database
    context = await seed_context(factory, name="Held Tenant")
    artifact = await stage_hammer(factory, context)
    service = CustomerPopulationReconciliationService()
    await service.refresh_population(factory, context=context)
    first = await service.hold_exact(
        factory,
        context=context,
        source_system="housecall_pro",
        source_customer_id=HAMMER_PROVIDER_ID,
        reason_code="owner_identity_review_required",
    )
    replay = await service.hold_exact(
        factory,
        context=context,
        source_system="housecall_pro",
        source_customer_id=HAMMER_PROVIDER_ID,
        reason_code="owner_identity_review_required",
    )
    assert first.id == replay.id
    report = await service.refresh_population(factory, context=context)
    assert report.counts.held == 1
    with pytest.raises(CustomerPopulationReconciliationError, match="held"):
        await service.admit_exact(
            factory,
            context=context,
            command=command(artifact, key="held-admission-attempt"),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("source_disposition", ["rejected", "duplicate"])
async def test_rejected_and_duplicate_provider_rows_cannot_be_admitted(
    database, source_disposition: str
) -> None:
    _, factory = database
    context = await seed_context(
        factory, name=f"{source_disposition.title()} Source Tenant"
    )
    artifact = await stage_hammer(factory, context)
    async with factory() as session, session.begin():
        source_row = await session.scalar(
            select(CustomerMigrationSourceRow).where(
                CustomerMigrationSourceRow.artifact_id == artifact.id,
                CustomerMigrationSourceRow.source_identity == HAMMER_PROVIDER_ID,
            )
        )
        assert source_row is not None
        source_row.disposition = source_disposition

    service = CustomerPopulationReconciliationService()
    with pytest.raises(
        CustomerPopulationReconciliationError,
        match="exact accepted provider Customer row was not found",
    ):
        await service.admit_exact(
            factory,
            context=context,
            command=command(artifact, key=f"{source_disposition}-admission-attempt"),
        )
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Customer)
                .where(Customer.company_id == context.company.id)
            )
            == 0
        )


@pytest.mark.asyncio
async def test_missing_exact_provider_identity_cannot_be_admitted(database) -> None:
    _, factory = database
    context = await seed_context(factory, name="Missing Source Tenant")
    artifact = await stage_hammer(factory, context)
    service = CustomerPopulationReconciliationService()
    missing = replace(
        command(artifact, key="missing-provider-admission"),
        source_customer_id="mechanically-absent-provider-id",
    )
    with pytest.raises(
        CustomerPopulationReconciliationError,
        match="exact accepted provider Customer row was not found",
    ):
        await service.admit_exact(factory, context=context, command=missing)
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Customer)
                .where(Customer.company_id == context.company.id)
            )
            == 0
        )


@pytest.mark.asyncio
async def test_authenticated_operator_command_refreshes_and_admits_exact_provider(
    database,
) -> None:
    _, factory = database
    context = await seed_context(factory, name="Operator Command Tenant")
    artifact = await stage_hammer(factory, context)
    assert context.active_branch is not None
    common = [
        "--company-id",
        str(context.company.id),
        "--branch-id",
        str(context.active_branch.id),
    ]
    refresh = reconciliation_parser().parse_args([*common, "refresh"])
    report = await execute_reconciliation_action(
        refresh, context=context, factory=factory
    )
    assert report["classification"] == "CUSTOMER_POPULATION_RECONCILED"
    assert report["counts"] == {
        "total": 1,
        "bound": 0,
        "held": 0,
        "ambiguous": 0,
        "unexplained": 1,
    }

    admission = reconciliation_parser().parse_args(
        [
            *common,
            "admit",
            "--provider-customer-id",
            HAMMER_PROVIDER_ID,
            "--source-artifact-id",
            str(artifact.id),
            "--expected-source-sha256",
            artifact.source_sha256,
            "--expected-source-row-sha256",
            digest(f"authoritative-hcp-row:{HAMMER_PROVIDER_ID}"),
            "--expected-customers",
            "1",
            "--expected-contacts",
            "1",
            "--expected-service-locations",
            "2",
            "--expected-billing-addresses",
            "0",
            "--idempotency-key",
            "operator-command-hammer-admission",
            "--reason-code",
            "owner_accepted_exact_provider_admission",
        ]
    )
    first = await execute_reconciliation_action(
        admission, context=context, factory=factory
    )
    replay = await execute_reconciliation_action(
        admission, context=context, factory=factory
    )
    assert first["classification"] == "CUSTOMER_PROVIDER_ID_ADMITTED"
    assert first["counts"] == {
        "customers": 1,
        "contacts": 1,
        "service_locations": 2,
        "billing_addresses": 0,
    }
    assert first["replayed"] is False
    assert replay["customer_id"] == first["customer_id"]
    assert replay["replayed"] is True


def test_operator_command_has_no_name_based_admission_surface() -> None:
    with pytest.raises(SystemExit):
        reconciliation_parser().parse_args(
            [
                "--company-id",
                str(uuid4()),
                "--branch-id",
                str(uuid4()),
                "admit",
                "--customer-name",
                "Hammer Haag",
            ]
        )


@pytest.mark.asyncio
async def test_operator_command_cannot_bypass_customer_manage_permission(
    database,
) -> None:
    _, factory = database
    context = await seed_context(factory, name="Unauthorized Operator Tenant")
    assert context.active_branch is not None
    refresh = reconciliation_parser().parse_args(
        [
            "--company-id",
            str(context.company.id),
            "--branch-id",
            str(context.active_branch.id),
            "refresh",
        ]
    )
    with pytest.raises(PermissionDeniedError, match="Permission denied"):
        await execute_reconciliation_action(
            refresh,
            context=replace(context, effective_permissions=()),
            factory=factory,
        )


@pytest.mark.asyncio
async def test_concurrent_exact_provider_commands_create_one_native_customer(
    database,
) -> None:
    _, factory = database
    context = await seed_context(factory, name="Concurrency Tenant")
    artifact = await stage_hammer(factory, context)
    service = CustomerPopulationReconciliationService()
    first, second = await asyncio.gather(
        service.admit_exact(
            factory,
            context=context,
            command=command(artifact, key="concurrent-admission-one"),
        ),
        service.admit_exact(
            factory,
            context=context,
            command=command(artifact, key="concurrent-admission-two"),
        ),
    )
    assert first.customer_id == second.customer_id
    async with factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Customer)
                .where(Customer.company_id == context.company.id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerSourceIdentity)
                .where(
                    CustomerSourceIdentity.company_id == context.company.id,
                    CustomerSourceIdentity.source_customer_id == HAMMER_PROVIDER_ID,
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(CustomerPopulationReconciliationCommand)
                .where(
                    CustomerPopulationReconciliationCommand.company_id
                    == context.company.id,
                    CustomerPopulationReconciliationCommand.status == "completed",
                )
            )
            == 2
        )
