from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from app.operational_migration.hcp_migration2_command import (
    _rehearsal_context_is_valid,
)
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership, MembershipBranchAccess
from app.platform.company.models import Company
from app.platform.users.models import User, UserCredential


def _context_parts(*, all_branches: bool) -> dict[str, object]:
    user_id = uuid4()
    company_id = uuid4()
    return {
        "user": SimpleNamespace(id=user_id, status="active"),
        "company": SimpleNamespace(id=company_id, status="active"),
        "branch": SimpleNamespace(company_id=company_id, status="active"),
        "membership": SimpleNamespace(
            user_id=user_id,
            company_id=company_id,
            status="active",
            has_all_branch_access=all_branches,
        ),
        "branch_access": None,
        "credential": SimpleNamespace(),
        "credentialed": True,
    }


def _is_valid(parts: dict[str, object]) -> bool:
    return _rehearsal_context_is_valid(
        user=cast(User, parts["user"]),
        company=cast(Company, parts["company"]),
        branch=cast(Branch, parts["branch"]),
        membership=cast(Membership, parts["membership"]),
        branch_access=cast(
            MembershipBranchAccess | None, parts["branch_access"]
        ),
        credential=cast(UserCredential | None, parts["credential"]),
        credentialed=cast(bool, parts["credentialed"]),
    )


def test_credentialed_all_branch_membership_does_not_require_access_row() -> None:
    assert _is_valid(_context_parts(all_branches=True))


def test_explicitly_scoped_membership_requires_access_row() -> None:
    parts = _context_parts(all_branches=False)
    assert not _is_valid(parts)
    parts["branch_access"] = SimpleNamespace()
    assert _is_valid(parts)


def test_all_branch_membership_rejects_cross_company_branch() -> None:
    parts = _context_parts(all_branches=True)
    parts["branch"] = SimpleNamespace(company_id=uuid4(), status="active")
    assert not _is_valid(parts)


@pytest.mark.parametrize(
    ("record", "status"),
    (("user", "disabled"), ("company", "inactive"), ("branch", "inactive")),
)
def test_all_branch_membership_rejects_inactive_context(
    record: str, status: str
) -> None:
    parts = _context_parts(all_branches=True)
    cast(SimpleNamespace, parts[record]).status = status
    assert not _is_valid(parts)


def test_all_branch_membership_rejects_revoked_membership() -> None:
    parts = _context_parts(all_branches=True)
    cast(SimpleNamespace, parts["membership"]).status = "revoked"
    assert not _is_valid(parts)
