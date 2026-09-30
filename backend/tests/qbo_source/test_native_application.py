from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from app.accounts_payable.models import AccountingVendor, VendorSourceMapping
from app.core.config import settings
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AccountingPermission
from app.platform.permissions.models import Permission
from app.platform.users.models import User
from app.qbo_source.application_models import (
    QboNativeApplicationRecord,
    QboNativeReviewDecision,
    QboNativeReviewItem,
)
from app.qbo_source.contracts import QboSourceEnvelope, SnapshotIdentity
from app.qbo_source.native_application import (
    QboApplicationError,
    QboNativeApplicationService,
    ReviewDecisionCommand,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@pytest_asyncio.fixture
async def database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def seed_context(
    factory: async_sessionmaker[AsyncSession], *, name: str
) -> AuthorizationContext:
    suffix = uuid4().hex[:8]
    async with factory() as session, session.begin():
        permission = await session.scalar(
            select(Permission).where(Permission.code == AccountingPermission.RECONCILE)
        )
        if permission is None:
            permission = Permission(
                code=AccountingPermission.RECONCILE,
                name="Reconcile Accounting",
                description="Synthetic QBO application qualification authority",
                resource="accounting",
                action="reconcile",
                status="active",
            )
            session.add(permission)
        user = User(
            normalized_email=f"qbo-application-{suffix}@example.test",
            first_name="Synthetic",
            last_name="Reviewer",
            display_name="Synthetic Reviewer",
            status="active",
        )
        company = Company(
            name=name,
            code=f"QA{suffix}".upper(),
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


def envelope(
    family: str,
    provider_id: str,
    *,
    realm: str = "all-county-production",
    sync_token: str = "1",
    amount: str = "10.00",
) -> QboSourceEnvelope:
    payload: dict[str, object] = {
        "Id": provider_id,
        "SyncToken": sync_token,
        "DocNumber": f"DOC-{provider_id}",
        "TxnDate": "2026-08-31",
        "TotalAmt": amount,
        "DisplayName": f"Source {provider_id}",
    }
    return QboSourceEnvelope.from_native(
        snapshot=SnapshotIdentity(
            snapshot_id="real-qbo-2026-08-31-g5",
            realm_id=realm,
            environment="production",
            accounting_date_cutoff=date(2026, 8, 31),
            cutoff_timezone="America/New_York",
            started_at=datetime(2026, 8, 31, 20, tzinfo=timezone.utc),
            api_minor_version=75,
        ),
        native_entity_type=family,
        native_id=provider_id,
        payload=payload,
        sync_token=sync_token,
        acquired_at=datetime(2026, 8, 31, 21, tzinfo=timezone.utc),
        source_updated_at=datetime(2026, 8, 31, 19, tzinfo=timezone.utc),
        relationship_ids=("dependency-1",) if family == "invoice" else (),
        currency="USD",
    )


def evidence(envelope_value: QboSourceEnvelope) -> tuple[str, QboSourceEnvelope]:
    return hashlib.sha256(
        f"envelope:{envelope_value.raw_sha256}".encode()
    ).hexdigest(), envelope_value


@pytest.mark.asyncio
async def test_clean_majority_binds_exact_and_quarantines_only_conflicts(database) -> None:
    factory = database
    context = await seed_context(factory, name="QBO Clean Majority")
    realm = "all-county-production"
    async with factory() as session, session.begin():
        vendor = AccountingVendor(
            company_id=context.company.id,
            code="QBO-VENDOR-1",
            legal_name="Exact Vendor",
            display_name="Exact Vendor",
            status="active",
            provenance="qbo_source_reviewed",
            created_by_user_id=context.user.id,
        )
        session.add(vendor)
        await session.flush()
        session.add(
            VendorSourceMapping(
                company_id=context.company.id,
                vendor_id=vendor.id,
                source_system="quickbooks_online",
                source_company_id=realm,
                source_vendor_id="vendor-1",
                source_digest="a" * 64,
                mapped_by_user_id=context.user.id,
            )
        )

    items = (
        evidence(envelope("vendor", "vendor-1", realm=realm)),
        evidence(envelope("invoice", "invoice-conflict", realm=realm)),
        evidence(envelope("employee", "employee-1", realm=realm)),
    )
    service = QboNativeApplicationService()
    result = await service.apply_clean_majority(
        factory, context=context, envelopes=items
    )

    assert result.processed == result.created == 3
    counts = {item.source_family: item for item in result.family_counts}
    assert counts["vendor"].bound == 1
    assert counts["invoice"].quarantined == 1
    assert counts["employee"].unsupported == 1
    assert all(item.unexplained == 0 for item in counts.values())
    reviews = await service.open_review_items(factory, context=context)
    assert len(reviews) == 1
    assert reviews[0].provider_record_id == "invoice-conflict"
    assert reviews[0].source_amount == "10.00"
    assert "HOLD_FOR_ACCOUNTANT" in reviews[0].allowed_actions
    assert reviews[0].affected_dependents == ["dependency-1"]

    replay = await service.apply_clean_majority(
        factory, context=context, envelopes=items
    )
    assert replay.created == 0
    assert replay.replayed == 3
    async with factory() as session:
        assert await session.scalar(
            select(func.count()).select_from(QboNativeApplicationRecord).where(
                QboNativeApplicationRecord.company_id == context.company.id
            )
        ) == 3
        assert await session.scalar(
            select(func.count()).select_from(QboNativeReviewItem).where(
                QboNativeReviewItem.company_id == context.company.id
            )
        ) == 1


@pytest.mark.asyncio
async def test_review_decision_binds_exact_vendor_and_preserves_history(database) -> None:
    factory = database
    context = await seed_context(factory, name="QBO Review Decisions")
    service = QboNativeApplicationService()
    await service.apply_clean_majority(
        factory,
        context=context,
        envelopes=(evidence(envelope("vendor", "vendor-review")),),
    )
    review = (await service.open_review_items(factory, context=context))[0]
    async with factory() as session, session.begin():
        vendor = AccountingVendor(
            company_id=context.company.id,
            code="QBO-REVIEW-VENDOR",
            legal_name="Explicit Review Vendor",
            display_name="Explicit Review Vendor",
            status="active",
            provenance="operator_review",
            created_by_user_id=context.user.id,
        )
        session.add(vendor)
        await session.flush()
        vendor_id = vendor.id

    decision = await service.decide_review(
        factory,
        context=context,
        review_item_id=review.id,
        command=ReviewDecisionCommand(
            action="MAP_VENDOR",
            reason="Owner selected the exact existing Vendor identity.",
            target_native_id=vendor_id,
        ),
    )
    assert decision.authority_class == "OWNER"
    counts = {item.source_family: item for item in await service.family_counts(factory, context=context)}
    assert counts["vendor"].bound == 1
    assert counts["vendor"].quarantined == 0
    assert await service.open_review_items(factory, context=context) == ()
    async with factory() as session:
        assert await session.scalar(
            select(func.count()).select_from(QboNativeReviewDecision).where(
                QboNativeReviewDecision.company_id == context.company.id
            )
        ) == 1


@pytest.mark.asyncio
async def test_review_decision_supersession_is_explicit_and_stale_replay_fails(database) -> None:
    factory = database
    context = await seed_context(factory, name="QBO Review Supersession")
    service = QboNativeApplicationService()
    await service.apply_clean_majority(
        factory,
        context=context,
        envelopes=(evidence(envelope("invoice", "invoice-review")),),
    )
    review = (await service.open_review_items(factory, context=context))[0]
    first = await service.decide_review(
        factory,
        context=context,
        review_item_id=review.id,
        command=ReviewDecisionCommand(
            action="DEFER_EXTERNAL",
            reason="External bank reconciliation is pending.",
            evidence_reference="bank-control-2026-05",
        ),
    )
    with pytest.raises(QboApplicationError, match="stale"):
        await service.decide_review(
            factory,
            context=context,
            review_item_id=review.id,
            command=ReviewDecisionCommand(
                action="DEFER_EXTERNAL",
                reason="Contradictory replay without predecessor.",
            ),
        )
    second = await service.decide_review(
        factory,
        context=context,
        review_item_id=review.id,
        command=ReviewDecisionCommand(
            action="DEFER_EXTERNAL",
            reason="Updated external reconciliation evidence remains pending.",
            evidence_reference="bank-control-2026-05-v2",
            supersedes_decision_id=first.id,
        ),
    )
    assert second.supersedes_decision_id == first.id
    async with factory() as session:
        predecessor = await session.get(QboNativeReviewDecision, first.id)
        assert predecessor is not None and predecessor.superseded_at is not None


@pytest.mark.asyncio
async def test_review_decision_authority_and_company_isolation_fail_closed(database) -> None:
    factory = database
    owner = await seed_context(factory, name="QBO Review Owner")
    foreign = await seed_context(factory, name="QBO Review Foreign")
    service = QboNativeApplicationService()
    await service.apply_clean_majority(
        factory,
        context=owner,
        envelopes=(evidence(envelope("invoice", "invoice-authority")),),
    )
    review = (await service.open_review_items(factory, context=owner))[0]
    with pytest.raises(QboApplicationError, match="finance approval"):
        await service.decide_review(
            factory,
            context=owner,
            review_item_id=review.id,
            command=ReviewDecisionCommand(
                action="HOLD_FOR_ACCOUNTANT",
                reason="Accountant review is required.",
            ),
        )
    with pytest.raises(QboApplicationError, match="not found"):
        await service.decide_review(
            factory,
            context=foreign,
            review_item_id=review.id,
            command=ReviewDecisionCommand(
                action="DEFER_EXTERNAL",
                reason="Must not cross Company scope.",
            ),
        )


@pytest.mark.asyncio
async def test_same_provider_version_with_changed_content_is_quarantined(database) -> None:
    factory = database
    context = await seed_context(factory, name="QBO Version Conflict")
    service = QboNativeApplicationService()
    first = envelope("invoice", "invoice-850", amount="850.00")
    changed = envelope("invoice", "invoice-850", amount="900.00")
    await service.apply_clean_majority(
        factory, context=context, envelopes=(evidence(first),)
    )
    await service.apply_clean_majority(
        factory, context=context, envelopes=(evidence(changed),)
    )

    async with factory() as session:
        current = await session.scalar(
            select(QboNativeApplicationRecord).where(
                QboNativeApplicationRecord.company_id == context.company.id,
                QboNativeApplicationRecord.provider_record_id == "invoice-850",
                QboNativeApplicationRecord.superseded_at.is_(None),
            )
        )
        assert current is not None
        assert current.version == 2
        assert current.disposition == "QUARANTINED"
        assert current.reason_code == "provider_version_content_conflict"
        review = await session.scalar(
            select(QboNativeReviewItem).where(
                QboNativeReviewItem.application_record_id == current.id
            )
        )
        assert review is not None
        assert review.conflicting_fields == ["provider_version", "source_digest"]


@pytest.mark.asyncio
async def test_company_isolation_and_permission_fail_closed(database) -> None:
    factory = database
    first = await seed_context(factory, name="QBO First Company")
    second = await seed_context(factory, name="QBO Second Company")
    service = QboNativeApplicationService()
    await service.apply_clean_majority(
        factory, context=first, envelopes=(evidence(envelope("invoice", "i-1")),)
    )
    assert await service.family_counts(factory, context=second) == ()
    unauthorized = AuthorizationContext(
        user=second.user,
        company=second.company,
        membership=second.membership,
        authorized_branches=second.authorized_branches,
        active_branch=second.active_branch,
        effective_roles=(),
        effective_permissions=(),
        credential_version=1,
        authorization_version=1,
    )
    with pytest.raises(QboApplicationError, match="authority"):
        await service.apply_clean_majority(
            factory,
            context=unauthorized,
            envelopes=(evidence(envelope("invoice", "i-2")),),
        )


@pytest.mark.asyncio
async def test_provider_unavailable_is_explicit_and_replay_safe(database) -> None:
    factory = database
    context = await seed_context(factory, name="QBO Provider Unavailable")
    service = QboNativeApplicationService()
    kwargs = {
        "context": context,
        "realm_id": "all-county-production",
        "source_family": "payroll_history",
        "reason_code": "provider_family_unavailable",
        "explanation": "QuickBooks did not provide this family in the sealed run.",
        "evidence_digest": "b" * 64,
        "acquired_at": datetime(2026, 8, 31, 21, tzinfo=timezone.utc),
    }
    assert await service.record_provider_unavailable(factory, **kwargs) is True
    assert await service.record_provider_unavailable(factory, **kwargs) is False
    counts = await service.family_counts(factory, context=context)
    assert len(counts) == 1
    assert counts[0].provider_unavailable == 1
    assert counts[0].unexplained == 0
