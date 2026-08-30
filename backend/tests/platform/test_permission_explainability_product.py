import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from app.platform.launch_controls import LAUNCH_ROLE_MATRIX
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.router import (
    explain_effective_permission,
    launch_role_matrix,
)


def context(
    *, permissions: frozenset[str], branches: frozenset
) -> AuthorizationContext:
    return cast(
        AuthorizationContext,
        SimpleNamespace(
            permission_codes=permissions,
            can_access_branch=lambda branch_id: branch_id in branches,
        ),
    )


@pytest.mark.asyncio
async def test_permission_explanation_never_grants_missing_or_cross_branch_access() -> (
    None
):
    allowed_branch, denied_branch = uuid4(), uuid4()
    allowed = await explain_effective_permission(
        "COMPANY_JOB_READ",
        context(
            permissions=frozenset({"COMPANY_JOB_READ"}),
            branches=frozenset({allowed_branch}),
        ),
        allowed_branch,
    )
    assert allowed.decision == "ALLOWED"
    assert allowed.reasons == ["ALLOWED_BY_ROLE"]

    denied = await explain_effective_permission(
        "COMPANY_PAYROLL_REPORTING_READ",
        context(
            permissions=frozenset({"COMPANY_JOB_READ"}),
            branches=frozenset({allowed_branch}),
        ),
        denied_branch,
    )
    assert denied.decision == "DENIED"
    assert denied.reasons == ["DENIED_MISSING_PERMISSION", "DENIED_BRANCH_SCOPE"]


@pytest.mark.asyncio
async def test_launch_role_product_is_read_only_canonical_evidence() -> None:
    roles = await launch_role_matrix(cast(AuthorizationContext, SimpleNamespace()))
    by_code = {role.code: role for role in roles}
    assert "TECHNICIAN" in by_code
    assert "COMPANY_JOB_EXECUTE" in by_code["TECHNICIAN"].permission_codes
    assert "COMPANY_ADMINISTER" not in by_code["TECHNICIAN"].permission_codes
    assert by_code["SUPPORT"].permission_codes == []


def test_owner_acceptance_personas_never_invent_noncanonical_privilege() -> None:
    packet = json.loads(
        (
            Path(__file__).parents[3]
            / "docs/quality/owner-role-acceptance-matrix.v1.json"
        ).read_text()
    )
    canonical = {role.code.value for role in LAUNCH_ROLE_MATRIX}
    assert packet["synthetic_only"] is True
    assert {item["persona"] for item in packet["personas"]} == {
        "TECHNICIAN",
        "DISPATCHER",
        "CSR",
        "MANAGER",
        "ADMIN",
        "RESTRICTED_EMPLOYEE",
    }
    for persona in packet["personas"]:
        if persona["canonical_role"] is None:
            assert persona["state"] == "CONFIGURATION_BLOCKED"
        else:
            assert persona["canonical_role"] in canonical
