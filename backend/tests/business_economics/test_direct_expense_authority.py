from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from app.business_economics.direct_expense_authority import (
    AllocationStatus,
    DirectExpenseAllocation,
    DirectExpenseAuthorityError,
    JobExpenseSplit,
    admitted_job_costs,
)


def allocation(*, status=AllocationStatus.CERTIFIED, amounts=(600, 400)):
    reviewer = uuid4() if status is AllocationStatus.CERTIFIED else None
    return DirectExpenseAllocation(
        company_id=uuid4(),
        source_system="ACP_AP",
        source_record_type="bill_line",
        source_transaction_id="bill-1",
        source_line_id="line-1",
        source_evidence_digest="a" * 64,
        source_amount_minor=1000,
        currency="USD",
        effective_date=date(2026, 9, 15),
        allocation_version=1,
        allocation_basis="human_certified_split",
        splits=tuple(JobExpenseSplit(uuid4(), uuid4(), amount) for amount in amounts),
        status=status,
        rationale="Exact reviewed allocation",
        actor_user_id=uuid4(),
        certified_by_user_id=reviewer,
        certified_at=datetime(2026, 9, 15, tzinfo=timezone.utc) if reviewer else None,
    )


def test_certified_exact_split_is_deterministic_and_admissible() -> None:
    item = allocation()
    assert item.digest() == item.digest()
    assert sum(part.amount_minor for part in admitted_job_costs(item)) == 1000


def test_draft_cannot_feed_job_economics() -> None:
    item = allocation(status=AllocationStatus.DRAFT)
    with pytest.raises(DirectExpenseAuthorityError, match="only certified"):
        admitted_job_costs(item)


def test_split_must_reconcile_without_missing_to_zero() -> None:
    with pytest.raises(DirectExpenseAuthorityError, match="reconcile"):
        allocation(amounts=(600, 399)).validate()


def test_exact_source_identity_is_required_not_memo_matching() -> None:
    item = allocation()
    invalid = DirectExpenseAllocation(**{**item.__dict__, "source_line_id": ""})
    with pytest.raises(DirectExpenseAuthorityError, match="exact source"):
        invalid.validate()
