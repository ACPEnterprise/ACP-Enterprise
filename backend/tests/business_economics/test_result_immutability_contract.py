from pathlib import Path

from app.business_economics.models import (
    EconomicsProfitabilityResultRecord,
    EconomicsProfitabilityResultSupersessionRecord,
)


MIGRATION = (
    Path(__file__).parents[2]
    / "alembic/versions/h6f8j0l2n497_immutable_economics_result_history.py"
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
