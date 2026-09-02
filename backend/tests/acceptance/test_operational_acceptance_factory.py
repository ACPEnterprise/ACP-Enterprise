from pathlib import Path

from scripts.operational_acceptance_factory import (
    ALLOWED_CLASSIFICATIONS,
    SCENARIO_VERSION,
    SCENARIOS,
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
