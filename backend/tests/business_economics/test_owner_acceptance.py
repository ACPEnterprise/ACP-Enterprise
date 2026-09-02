from app.business_economics.owner_acceptance import owner_question_acceptance_matrix
from app.platform.permissions.codes import (
    AccountingPermission,
    AccountsPayablePermission,
    EconomicsPolicyPermission,
    InvoicePermission,
    PaymentPermission,
)

ALL_READ = frozenset(
    {
        EconomicsPolicyPermission.MEASUREMENT_READ,
        InvoicePermission.READ,
        PaymentPermission.READ,
        AccountsPayablePermission.REPORT_READ,
        AccountingPermission.REPORT_READ,
    }
)


def _workspace(quality: str = "complete") -> dict[str, object]:
    return {
        "quality_state": quality,
        "jobs": [{"result_id": "synthetic"}],
        "service_categories": [{"label": "Synthetic service"}],
        "branches": [{"label": "Synthetic branch"}],
        "comparison": {"state": "available"},
        "readiness": {"policy_gaps": []},
    }


def _rows(matrix: dict[str, object]) -> dict[str, dict[str, object]]:
    questions = matrix["questions"]
    assert isinstance(questions, list)
    return {str(row["key"]): row for row in questions if isinstance(row, dict)}


def test_matrix_is_deterministic_and_keeps_cash_external() -> None:
    first = owner_question_acceptance_matrix(_workspace(), ALL_READ)
    second = owner_question_acceptance_matrix(_workspace(), ALL_READ)
    assert first == second
    rows = _rows(first)
    assert rows["work"]["disposition"] == "ANSWERABLE"
    assert rows["collected"]["disposition"] == "EXTERNAL_GATE"
    assert rows["profit_cash"]["disposition"] == "EXTERNAL_GATE"
    assert "not substituted" in str(rows["collected"]["why"])
    assert first["mutation_authority"] == "none"


def test_matrix_distinguishes_partial_policy_missing_and_not_applicable() -> None:
    workspace = _workspace("partial")
    workspace["readiness"] = {
        "policy_gaps": [{"gap_key": "allocation", "state": "open"}]
    }
    rows = _rows(owner_question_acceptance_matrix(workspace, ALL_READ))
    assert rows["work"]["disposition"] == "PARTIALLY_ANSWERABLE"
    assert rows["decisions"]["disposition"] == "POLICY_REQUIRED"
    assert rows["stale"]["disposition"] == "NOT_APPLICABLE"
    assert "not the same as zero" in str(rows["stale"]["why"])


def test_matrix_fails_closed_before_cross_domain_retrieval() -> None:
    permissions = frozenset({EconomicsPolicyPermission.MEASUREMENT_READ})
    rows = _rows(owner_question_acceptance_matrix(_workspace(), permissions))
    assert rows["work"]["disposition"] == "ANSWERABLE"
    assert rows["unpaid"]["disposition"] == "NOT_AUTHORIZED"
    assert rows["vendor"]["disposition"] == "NOT_AUTHORIZED"
    assert rows["unpaid"]["missing_permissions"]


def test_matrix_distinguishes_absent_populations_from_zero() -> None:
    workspace = _workspace()
    workspace["jobs"] = []
    workspace["service_categories"] = []
    workspace["branches"] = []
    rows = _rows(owner_question_acceptance_matrix(workspace, ALL_READ))
    assert rows["jobs_most"]["disposition"] == "SOURCE_REQUIRED"
    assert rows["services_most"]["disposition"] == "SOURCE_REQUIRED"
    assert rows["branch"]["disposition"] == "SOURCE_REQUIRED"
