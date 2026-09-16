from app.business_economics.profitability_readiness_gates import (
    EconomicPrerequisite,
    PrerequisiteState,
    evaluate_profitability_gates,
)


def fact(key, state=PrerequisiteState.AVAILABLE):
    return EconomicPrerequisite(
        key,
        state,
        "a" * 64 if state is PrerequisiteState.AVAILABLE else None,
        "certified-test",
    )


def gate(result, name):
    return next(item for item in result["gates"] if item["gate"] == name)


def test_direct_contribution_requires_every_cost_family() -> None:
    result = evaluate_profitability_gates(
        (
            fact("invoiced_revenue"),
            fact("direct_wage_cost"),
            fact("direct_material_cost"),
        )
    )
    value = gate(result, "DIRECT_CONTRIBUTION_READY")
    assert value["state"] == "BLOCKED"
    assert value["blockers"] == [
        {"key": "other_direct_cost_completeness", "state": "MISSING"}
    ]
    assert result["missing_is_zero"] is False


def test_uncertified_policy_blocks_burdened_contribution() -> None:
    keys = (
        "invoiced_revenue",
        "direct_wage_cost",
        "direct_material_cost",
        "other_direct_cost_completeness",
        "employer_burden_components",
    )
    result = evaluate_profitability_gates(
        tuple(fact(key) for key in keys)
        + (
            fact(
                "employer_burden_allocation_policy",
                PrerequisiteState.POLICY_UNCERTIFIED,
            ),
        )
    )
    value = gate(result, "BURDENED_CONTRIBUTION_READY")
    assert value["state"] == "BLOCKED"
    assert value["blockers"][0]["state"] == "POLICY_UNCERTIFIED"


def test_company_ready_does_not_make_branch_ready() -> None:
    result = evaluate_profitability_gates(
        tuple(
            fact(key)
            for key in (
                "reconciled_overhead_evidence",
                "overhead_pool_policy",
                "overhead_allocation_policy",
                "productive_hour_definition",
                "productive_hours",
            )
        )
    )
    assert gate(result, "COMPANY_BREAK_EVEN_READY")["state"] == "READY"
    assert gate(result, "BRANCH_BREAK_EVEN_READY")["state"] == "BLOCKED"


def test_replay_digest_is_stable_and_no_mutation_exists() -> None:
    inputs = (fact("invoiced_revenue"),)
    assert evaluate_profitability_gates(inputs) == evaluate_profitability_gates(inputs)
    assert evaluate_profitability_gates(inputs)["mutation_authority"] == "none"
