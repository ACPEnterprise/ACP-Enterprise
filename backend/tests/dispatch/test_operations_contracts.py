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
        "fresh_hcp_delta_acquired_and_sealed",
        "zero_unexplained_open_work_gap",
        "admitted_source_identity_chain_verified",
    }.issubset(contract["mutation_gate"]["requirements"])
    assert {
        "real_customer",
        "real_service_location",
        "real_job",
        "real_appointment",
        "real_employee",
    } == set(contract["subjects"])
    assert contract["physical_path"] == [
        "customer",
        "service_location",
        "job",
        "appointment",
        "schedule",
        "assign_technician",
        "dispatch",
        "technician_my_day",
        "csr_fresh_session_readback",
    ]
    assert {
        "same_identity_chain_in_technician_my_day",
        "csr_fresh_session_readback",
    }.issubset(contract["checks"])
    assert {
        "hcp_delta_acquired_at",
        "hcp_delta_manifest_digest",
        "open_work_reconciliation_digest",
        "open_work_source_admitted_held_and_unexplained_counts",
    }.issubset(contract["evidence"])
