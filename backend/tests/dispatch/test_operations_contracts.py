import json
from pathlib import Path

ROOT = Path(__file__).parents[2] / "operations"


def load(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_future_action_intents_are_human_confirmed_and_non_executable() -> None:
    contract = load("scheduling-dispatch-action-intents.v1.json")
    assert contract["mutation_authority"] == "none"
    assert contract["lia_execution"] == "prohibited"
    assert set(contract["actions"]) == {
        "ASSIGN",
        "REASSIGN",
        "RESCHEDULE",
        "CANCEL_APPOINTMENT",
    }
    for action in contract["actions"].values():
        assert action["confirmation"] == "authorized_human_explicit"
        assert action["current_version"]
        assert action["permissions"]
        assert {
            "actor_user_id",
            "occurred_at",
            "prior_state",
            "new_state",
            "reason",
            "idempotency_key",
        }.issubset(action["audit"])


def test_real_acceptance_contract_has_no_synthetic_or_production_fallback() -> None:
    contract = load("scheduling-dispatch-real-acceptance.v1.json")
    assert contract["environment"] == "Preview"
    assert contract["synthetic_fallback"] == "prohibited"
    assert contract["production"] == "prohibited"
    assert contract["default_mode"] == "read_only"
    assert contract["mutation_gate"]["required"] is True
    assert "owner_certified_real_employee" in contract["mutation_gate"]["requirements"]
    assert (
        "owner_sanctioned_real_appointment" in contract["mutation_gate"]["requirements"]
    )
    assert {
        "real_customer",
        "real_service_location",
        "real_job",
        "real_appointment",
        "real_employee",
    } == set(contract["subjects"])
