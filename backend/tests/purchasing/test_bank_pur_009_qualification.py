import hashlib
import json
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError

from app.inventory.models import InventoryItem
from app.purchasing.errors import PurchasingNotFound, PurchasingValidation
from app.purchasing.models import (
    BranchPurchasingPolicy,
    BranchPurchasingPolicyRevision,
)
from app.purchasing.schemas import BranchPurchasingPolicyWrite
from app.purchasing.service import PurchasingService

pytest_plugins = ("tests.purchasing.test_purchasing_foundation",)

QUALIFICATION_PATH = (
    Path(__file__).parents[3]
    / "docs/architecture/purchasing/bank-pur-009-qualification.v1.json"
)


def _command(*, branch_id, item_id, key: str) -> BranchPurchasingPolicyWrite:
    return BranchPurchasingPolicyWrite(
        branch_id=branch_id,
        inventory_item_id=item_id,
        target_available_quantity=Decimal(8),
        status="active",
        provenance_reference="synthetic independent qualification",
        reason="Qualified branch target",
        expected_version=None,
        idempotency_key=key,
    )


async def _item(factory, *, company_id, actor_id) -> InventoryItem:
    async with factory() as session, session.begin():
        item = InventoryItem(
            company_id=company_id,
            code=f"Q9-{uuid4().hex[:8].upper()}",
            name="Synthetic qualified policy item",
            stocking_unit="each",
            status="active",
            created_by_user_id=actor_id,
            updated_by_user_id=actor_id,
        )
        session.add(item)
        await session.flush()
        return item


def test_bank_pur_009_qualification_artifact_is_canonical() -> None:
    payload = json.loads(QUALIFICATION_PATH.read_text())
    fingerprint = payload.pop("qualification_fingerprint")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    assert payload["implementation_sha"] == (
        "559536c7bec0b6ffa18de3f2bdf72e3c7f35a3d5"
    )
    assert payload["integration_sha"] == (
        "f65548968f94e9f5e57610c9aae2863d4d4446cd"
    )
    assert payload["state"] == "QUALIFIED_AWAITING_OWNER_ACCEPTANCE"
    assert payload["successor_gate"]["state"] == (
        "BLOCKED_PENDING_BANK_PUR_009_OWNER_ACCEPTANCE"
    )
    assert fingerprint == hashlib.sha256(canonical.encode()).hexdigest()


@pytest.mark.asyncio
async def test_policy_revision_evidence_is_database_immutable(
    purchasing_fixture,
) -> None:
    factory, company, _, branch, _, preparer, _ = purchasing_fixture
    service = PurchasingService()
    item = await _item(
        factory, company_id=company.id, actor_id=preparer.user.id
    )
    async with factory() as session:
        policy = await service.configure_branch_policy(
            session,
            context=preparer,
            payload=_command(
                branch_id=branch.id,
                item_id=item.id,
                key=f"q9-immutable-{uuid4()}",
            ),
        )
        revision_id = await session.scalar(
            select(BranchPurchasingPolicyRevision.id).where(
                BranchPurchasingPolicyRevision.company_id == company.id,
                BranchPurchasingPolicyRevision.policy_id == policy.id,
                BranchPurchasingPolicyRevision.version == 1,
            )
        )
        assert revision_id is not None

    async with factory() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                update(BranchPurchasingPolicyRevision)
                .where(BranchPurchasingPolicyRevision.id == revision_id)
                .values(reason="prohibited rewrite", evidence_digest="0" * 64)
            )
    async with factory() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                delete(BranchPurchasingPolicyRevision).where(
                    BranchPurchasingPolicyRevision.id == revision_id
                )
            )
    async with factory() as session:
        stored = await session.get(BranchPurchasingPolicyRevision, revision_id)
        assert stored is not None
        assert stored.reason == "Qualified branch target"
        assert stored.evidence_digest == policy.revisions[0].evidence_digest


@pytest.mark.asyncio
async def test_policy_fails_closed_for_cross_company_item_and_unauthorized_branch(
    purchasing_fixture,
) -> None:
    factory, company, other_company, branch, other_branch, preparer, _ = (
        purchasing_fixture
    )
    service = PurchasingService()
    foreign_item = await _item(
        factory,
        company_id=other_company.id,
        actor_id=preparer.user.id,
    )

    with pytest.raises(PurchasingValidation):
        async with factory() as session:
            await service.configure_branch_policy(
                session,
                context=preparer,
                payload=_command(
                    branch_id=branch.id,
                    item_id=foreign_item.id,
                    key=f"q9-foreign-item-{uuid4()}",
                ),
            )
    with pytest.raises(PurchasingNotFound):
        async with factory() as session:
            await service.configure_branch_policy(
                session,
                context=preparer,
                payload=_command(
                    branch_id=other_branch.id,
                    item_id=foreign_item.id,
                    key=f"q9-foreign-branch-{uuid4()}",
                ),
            )

    async with factory() as session:
        assert (
            await session.scalar(
                select(BranchPurchasingPolicy).where(
                    BranchPurchasingPolicy.company_id == company.id
                )
            )
            is None
        )
