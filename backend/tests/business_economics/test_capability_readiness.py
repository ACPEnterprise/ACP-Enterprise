from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.business_economics.capability_readiness import capability_readiness_matrix
from app.business_economics.router import economics_capabilities


def test_capability_matrix_is_deterministic_and_preserves_authority_boundaries() -> (
    None
):
    first = capability_readiness_matrix()
    second = capability_readiness_matrix()
    assert first == second
    states = {item["capability"]: item["state"] for item in first["capabilities"]}
    assert states["overhead_allocation_authority"] == "AUTHORITATIVE"
    assert states["allocated_job_profitability"] == "POLICY_REQUIRED"
    assert states["callback_warranty_economics"] == "SOURCE_REQUIRED"
    assert states["real_qbo_evidence"] == "ACTIVE_OWNER_COLLISION"
    assert first["mutation_authority"] == "none"
    assert first["real_qbo_boundary"] == "migration_owned"


def test_capability_matrix_has_no_false_completion_for_gated_work() -> None:
    value = capability_readiness_matrix()
    gated = {
        item["capability"]: item
        for item in value["capabilities"]
        if item["state"]
        in {
            "POLICY_REQUIRED",
            "SOURCE_REQUIRED",
            "EXTERNAL_GATE",
            "DEPENDENCY_BLOCKED",
            "ACTIVE_OWNER_COLLISION",
        }
    }
    assert gated
    assert all(item["blockers"] for item in gated.values())


@pytest.mark.asyncio
async def test_capability_projection_is_company_and_branch_scoped_without_values() -> (
    None
):
    company_id, branch_id = uuid4(), uuid4()
    context = SimpleNamespace(
        company=SimpleNamespace(id=company_id),
        active_branch=SimpleNamespace(id=branch_id),
    )
    value = await economics_capabilities(context)
    assert value["company_id"] == str(company_id)
    assert value["branch_id"] == str(branch_id)
    assert "amount" not in str(value).casefold()
