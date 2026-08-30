from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.business_economics.models import (
    EconomicsProfitabilityResultRecord,
    EconomicsProfitabilityResultSupersessionRecord,
)
from app.business_economics.result_history import EconomicsResultHistoryService

MIGRATION = (
    Path(__file__).parents[2]
    / "alembic/versions/h6f8j0l2n497_immutable_economics_result_history.py"
)
BRANCH_MIGRATION = (
    Path(__file__).parents[2]
    / "alembic/versions/n2l1j60i7g3e_bind_economics_result_branch_lineage.py"
)


def test_database_contract_rejects_result_and_history_mutation() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "BEFORE UPDATE OR DELETE ON economics_profitability_results" in source
    assert (
        "BEFORE UPDATE OR DELETE ON economics_profitability_result_supersessions"
        in source
    )
    assert "ERRCODE = '55000'" in source
    assert "refusing destructive downgrade" in source


def test_supersession_contract_is_non_forking_and_company_bound() -> None:
    constraints = {
        item.name
        for item in EconomicsProfitabilityResultSupersessionRecord.__table__.constraints
    }
    assert "uq_eco_profitability_single_successor" in constraints
    assert "uq_eco_profitability_single_predecessor" in constraints
    assert "fk_eco_profitability_supersession_predecessor" in constraints
    assert "fk_eco_profitability_supersession_successor" in constraints
    result_constraints = {
        item.name for item in EconomicsProfitabilityResultRecord.__table__.constraints
    }
    assert "uq_eco_profitability_result_company_id" in result_constraints


def test_supersession_contract_is_branch_bound_forward() -> None:
    source = BRANCH_MIGRATION.read_text(encoding="utf-8")
    assert "predecessor.branch_id" in source
    assert "successor.branch_id" in source
    assert 'down_revision: str | Sequence[str] | None = "m1k0i59h6f2d"' in source


def test_result_history_scope_rejects_unselected_branch() -> None:
    allowed_branch = uuid4()
    denied_branch = uuid4()
    context = SimpleNamespace(
        active_branch=None,
        can_access_branch=lambda branch_id: branch_id == allowed_branch,
    )

    assert EconomicsResultHistoryService._can_access_result(
        context, SimpleNamespace(branch_id=None)
    )
    assert EconomicsResultHistoryService._can_access_result(
        context, SimpleNamespace(branch_id=allowed_branch)
    )
    assert not EconomicsResultHistoryService._can_access_result(
        context, SimpleNamespace(branch_id=denied_branch)
    )
