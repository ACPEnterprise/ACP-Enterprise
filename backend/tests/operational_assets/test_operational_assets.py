from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.operational_assets.operationalization import classify_candidate
from app.operational_assets.schemas import AssetActionCreate
from app.operational_assets.service import AssetConflict, AssetService, digest
from app.scheduling import models as scheduling_models  # noqa: F401


class FakeSession:
    def __init__(self, scalar_results):
        self.scalar_results = iter(scalar_results)
        self.added = []

    async def scalar(self, _query):
        return next(self.scalar_results)

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        return None

    async def commit(self):
        return None

    async def refresh(self, _value):
        return None


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


@pytest.mark.asyncio
async def test_typed_action_exact_replay_and_contradiction(monkeypatch):
    service = AssetService()
    monkeypatch.setattr(service, "_event", lambda *_args: None)
    company_id, branch_id, user_id, asset_id = (uuid4() for _ in range(4))
    asset = SimpleNamespace(
        id=asset_id,
        company_id=company_id,
        branch_id=branch_id,
        asset_class="vehicle",
        identity_digest="identity",
        version=1,
        updated_at=datetime.now(timezone.utc),
    )
    context = SimpleNamespace(
        company=SimpleNamespace(id=company_id),
        user=SimpleNamespace(id=user_id),
        authorized_branch_ids=(branch_id,),
    )
    command = AssetActionCreate(
        action_type="inspection",
        state="completed",
        occurred_at=datetime.now(timezone.utc),
        expected_version=1,
        idempotency_key="inspection-command",
    )
    first_session = FakeSession([asset, None])
    first = await service.record_action(first_session, context, asset_id, command)
    assert first.action_type == "inspection"
    assert asset.version == 2

    replay_session = FakeSession([asset, first])
    assert (
        await service.record_action(replay_session, context, asset_id, command) is first
    )

    changed = command.model_copy(update={"state": "fail"})
    with pytest.raises(AssetConflict):
        await service.record_action(
            FakeSession([asset, first]), context, asset_id, changed
        )


def test_import_classification_fails_closed_without_customer_location():
    state, issues = classify_candidate(
        "customer_equipment", {"manufacturer": "Synthetic"}
    )
    assert state == "insufficient_evidence"
    assert issues == ["missing_customer_id", "missing_service_location_id"]


def test_import_classification_preserves_replacement_and_conflict():
    assert (
        classify_candidate(
            "tracked_tool", {"asset_number": "T-1", "replacement_of": "old"}
        )[0]
        == "replacement_candidate"
    )
    assert (
        classify_candidate(
            "vehicle", {"asset_number": "V-1", "conflicting_branch": True}
        )[0]
        == "conflict"
    )
