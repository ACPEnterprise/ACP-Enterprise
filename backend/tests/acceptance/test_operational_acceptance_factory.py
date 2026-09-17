from pathlib import Path

import pytest

from scripts.operational_acceptance_factory import (
    ALLOWED_CLASSIFICATIONS,
    SCENARIO_VERSION,
    SCENARIOS,
    _selected_scenarios,
    _test_environment,
)


def test_scenario_catalog_is_complete_unique_and_safely_classified() -> None:
    assert SCENARIO_VERSION == "ENTERPRISE.OPERATIONAL.ACCEPTANCE.FACTORY.v1"
    assert len(SCENARIOS) >= 50
    assert len({scenario.scenario_id for scenario in SCENARIOS}) == len(SCENARIOS)
    for scenario in SCENARIOS:
        assert scenario.persona
        assert scenario.expected
        if scenario.gate_classification is None:
            assert scenario.test_nodes
        else:
            assert scenario.gate_classification in ALLOWED_CLASSIFICATIONS
            assert scenario.limitation


def test_every_test_node_binds_to_a_repository_test_file() -> None:
    backend_root = Path(__file__).resolve().parents[2]
    for scenario in SCENARIOS:
        for node in scenario.test_nodes:
            relative_path = node.split("::", 1)[0]
            assert relative_path.startswith("tests/")
            assert (backend_root / relative_path).is_file(), node


def test_catalog_contains_no_real_provider_or_production_execution() -> None:
    serialized = " ".join(
        node for scenario in SCENARIOS for node in scenario.test_nodes
    ).lower()
    assert "production" not in serialized
    assert "real_qbo" not in serialized
    assert "real_provider" not in serialized


def test_employee_time_payroll_scenario_reuses_bounded_authoritative_proofs() -> None:
    scenario = next(
        value
        for value in SCENARIOS
        if value.scenario_id == "employee_time_payroll_crossdomain"
    )
    serialized = " ".join(scenario.test_nodes)
    assert "test_authorization_service.py" in serialized
    assert "test_jobs_api.py" in serialized
    assert "test_workday_authority.py" in serialized
    assert "test_job_clock_operations.py" in serialized
    assert "test_labor_evidence.py" in serialized
    assert "test_gross_pay_calculation.py" in serialized
    assert "test_tax_deduction_calculation.py" in serialized
    assert "test_reporting.py" in serialized
    assert "payment_execution" not in serialized
    assert "payment_release" not in serialized


def test_focused_scenario_selection_is_ordered_and_fails_closed() -> None:
    selected = _selected_scenarios(("dispatch", "scheduling"))
    assert [scenario.scenario_id for scenario in selected] == [
        "scheduling",
        "dispatch",
    ]

    with pytest.raises(ValueError, match="unknown acceptance scenario"):
        _selected_scenarios(("not-a-real-scenario",))


def test_child_test_environment_does_not_inherit_qualification_secrets(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ACCESS_TOKEN_KEYS", '{"qualification":"secret"}')
    monkeypatch.setenv("ACCESS_TOKEN_SIGNING_KEY", "secret")
    monkeypatch.setenv("ACCESS_TOKEN_ACTIVE_KID", "qualification")
    monkeypatch.setenv("SECURITY_TOKEN_HMAC_KEY", "secret")

    environment = _test_environment()

    assert environment["ENVIRONMENT"] == "test"
    assert environment["PYTHONPATH"]
    assert "ACCESS_TOKEN_KEYS" not in environment
    assert "ACCESS_TOKEN_SIGNING_KEY" not in environment
    assert "ACCESS_TOKEN_ACTIVE_KID" not in environment
    assert "SECURITY_TOKEN_HMAC_KEY" not in environment
