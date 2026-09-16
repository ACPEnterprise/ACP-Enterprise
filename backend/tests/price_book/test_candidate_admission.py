import copy
import json
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from app.core.config import settings
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.users.models import User
from app.price_book.candidate_admission import (
    admit_candidate_plan,
    candidate_review_page,
    classify_packet,
)
from app.price_book.errors import PriceBookConflict
from app.price_book.models import (
    PriceBookAuditEntry,
    PriceBookCandidateBinding,
    PriceBookCategory,
    PriceBookPriceVersion,
    PriceBookServiceItem,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT = Path(__file__).parents[3]
CONFIGURATION = (
    ROOT / "docs/architecture/price-book/all-county-build-1.configuration.json"
)
READINESS = ROOT / "docs/architecture/price-book/all-county-activation-readiness-1.json"


@pytest_asyncio.fixture
async def price_book_fixture():
    engine = create_async_engine(settings.database_url)
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(connection, expire_on_commit=False)
    async with factory() as session, session.begin():
        company = Company(
            name="Candidate Admission Test",
            code="PBA" + uuid4().hex[:8].upper(),
            status="active",
            timezone="America/New_York",
        )
        branch = Branch(
            company=company,
            name="Main",
            code="B" + uuid4().hex[:8].upper(),
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        actor = User(
            normalized_email=f"admission-{uuid4().hex}@example.test",
            first_name="Price",
            last_name="Owner",
            display_name="Price Owner",
            status="active",
        )
        session.add_all([company, branch, actor])
        await session.flush()
    membership = Membership(
        user_id=actor.id,
        company_id=company.id,
        status="active",
        has_all_branch_access=True,
    )
    context = AuthorizationContext(
        user=actor,
        company=company,
        membership=membership,
        authorized_branches=(branch,),
        active_branch=branch,
        effective_roles=(),
        effective_permissions=(),
        credential_version=1,
        authorization_version=actor.authorization_version,
    )
    try:
        yield factory, context, branch
    finally:
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


def load_plan():
    return classify_packet(
        json.loads(CONFIGURATION.read_text()), json.loads(READINESS.read_text())
    )


def test_sealed_candidate_packet_classifies_every_row() -> None:
    plan = load_plan()
    assert plan.counts == {
        "candidate_categories": 16,
        "candidate_services": 218,
        "safe_draft_admission": 179,
        "held_source_conflict": 39,
        "material_mapping_required": 194,
        "tax_review_required": 218,
        "price_review_required": 218,
        "activation_ready": 0,
    }
    assert all(item["activation_blockers"] for item in plan.services)


@pytest.mark.asyncio
async def test_admission_is_draft_only_replay_safe_and_searchable(
    price_book_fixture,
) -> None:
    factory, context, _branch = price_book_fixture
    plan = load_plan()
    async with factory() as session:
        first = await admit_candidate_plan(
            session,
            company_id=context.company.id,
            actor_user_id=context.user.id,
            plan=plan,
            idempotency_key="all-county-build-1-admission-v1",
        )
    assert first.result_counts["created_categories"] == 16
    assert first.result_counts["created_services"] == 179
    assert first.result_counts["activated_prices"] == 0

    async with factory() as session:
        counts = {
            "categories": await session.scalar(
                select(func.count())
                .select_from(PriceBookCategory)
                .where(PriceBookCategory.company_id == context.company.id)
            ),
            "services": await session.scalar(
                select(func.count())
                .select_from(PriceBookServiceItem)
                .where(PriceBookServiceItem.company_id == context.company.id)
            ),
            "active_versions": await session.scalar(
                select(func.count())
                .select_from(PriceBookPriceVersion)
                .where(
                    PriceBookPriceVersion.status == "active",
                    PriceBookPriceVersion.company_id == context.company.id,
                )
            ),
            "bindings": await session.scalar(
                select(func.count())
                .select_from(PriceBookCandidateBinding)
                .where(PriceBookCandidateBinding.company_id == context.company.id)
            ),
            "audits": await session.scalar(
                select(func.count())
                .select_from(PriceBookAuditEntry)
                .where(PriceBookAuditEntry.company_id == context.company.id)
            ),
        }
    async with factory() as session:
        replay = await admit_candidate_plan(
            session,
            company_id=context.company.id,
            actor_user_id=context.user.id,
            plan=plan,
            idempotency_key="all-county-build-1-admission-v1",
        )
    assert replay.id == first.id
    assert counts == {
        "categories": 16,
        "services": 179,
        "active_versions": 0,
        "bindings": 234,
        "audits": 196,
    }

    async with factory() as session:
        after = {
            "categories": await session.scalar(
                select(func.count())
                .select_from(PriceBookCategory)
                .where(PriceBookCategory.company_id == context.company.id)
            ),
            "services": await session.scalar(
                select(func.count())
                .select_from(PriceBookServiceItem)
                .where(PriceBookServiceItem.company_id == context.company.id)
            ),
            "bindings": await session.scalar(
                select(func.count())
                .select_from(PriceBookCandidateBinding)
                .where(PriceBookCandidateBinding.company_id == context.company.id)
            ),
            "audits": await session.scalar(
                select(func.count())
                .select_from(PriceBookAuditEntry)
                .where(PriceBookAuditEntry.company_id == context.company.id)
            ),
        }
        for term in ("drain", "water heater", "toilet", "sewer"):
            page = await candidate_review_page(
                session,
                company_id=context.company.id,
                search=term,
                category=None,
                admission_status=None,
                review_flag=None,
                limit=200,
                offset=0,
                costs_visible=False,
            )
            assert page["total"] > 0
            assert all(item["labor_hours"] is None for item in page["items"])
    assert after == {
        "categories": 16,
        "services": 179,
        "bindings": 234,
        "audits": 196,
    }


@pytest.mark.asyncio
async def test_changed_evidence_under_same_identity_fails_closed(
    price_book_fixture,
) -> None:
    factory, context, _branch = price_book_fixture
    plan = load_plan()
    async with factory() as session:
        await admit_candidate_plan(
            session,
            company_id=context.company.id,
            actor_user_id=context.user.id,
            plan=plan,
            idempotency_key="all-county-build-1-admission-v1",
        )
    changed = copy.copy(plan)
    object.__setattr__(changed, "packet_digest", "f" * 64)
    async with factory() as session:
        with pytest.raises(PriceBookConflict):
            await admit_candidate_plan(
                session,
                company_id=context.company.id,
                actor_user_id=context.user.id,
                plan=changed,
                idempotency_key="all-county-build-1-admission-v1",
            )
