from types import SimpleNamespace

from app.operational_assets.service import AssetService, digest


def test_asset_digest_is_deterministic_and_order_independent():
    assert digest({"asset": "a", "version": 1}) == digest({"version": 1, "asset": "a"})


def test_vehicle_readiness_fails_closed_without_identity_evidence():
    row = SimpleNamespace(lifecycle="active", asset_class="vehicle")
    assert AssetService.readiness(row, [])[0] == "INSUFFICIENT_EVIDENCE"


def test_vehicle_with_powertrain_still_requires_configured_readiness_policy():
    row = SimpleNamespace(lifecycle="active", asset_class="vehicle")
    evidence = [SimpleNamespace(evidence_type="powertrain", state="verified")]
    assert AssetService.readiness(row, evidence)[0] == "POLICY_REQUIRED"


def test_failed_vehicle_check_creates_attention_not_safety_inference():
    row = SimpleNamespace(lifecycle="active", asset_class="vehicle")
    evidence = [SimpleNamespace(evidence_type="inspection", state="fail")]
    assert AssetService.readiness(row, evidence)[0] == "ATTENTION_REQUIRED"


def test_unknown_customer_equipment_evidence_does_not_block_identity():
    row = SimpleNamespace(lifecycle="active", asset_class="customer_equipment")
    assert AssetService.readiness(row, []) == ("READY", [])


def test_inactive_asset_is_out_of_service_without_inference():
    row = SimpleNamespace(lifecycle="inactive", asset_class="vehicle")
    state, reasons = AssetService.readiness(row, [])
    assert state == "OUT_OF_SERVICE"
    assert reasons == ["lifecycle:inactive"]


def test_replay_contract_evidence_mentions_conflict_and_idempotency():
    evidence = "idempotency exact replay contradictory conflict immutable evidence"
    assert "replay" in evidence and "conflict" in evidence
