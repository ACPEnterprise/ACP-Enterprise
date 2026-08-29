from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.beacon.contracts import BeaconWorkflowAction
from app.platform.permissions.codes import BeaconPermission

ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "docs/architecture/beacon/bank-bea-005-qualification.v1.json"


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def evidence() -> dict[str, object]:
    return json.loads(PATH.read_text(encoding="utf-8"))


def contract_payload() -> dict[str, object]:
    return {
        "actions": sorted(item.value for item in BeaconWorkflowAction),
        "permissions": sorted(BeaconPermission.ALL),
        "acknowledgement_is_resolution": False,
        "ownership_grants_business_authority": False,
        "assign_requires_unowned": True,
        "transfer_requires_owned": True,
        "replay_precedes_source_re_evaluation": True,
    }


def test_qualification_binds_canonical_workflow_contract() -> None:
    payload = evidence()
    assert payload["implementation_sha"] == (
        "64e2cc6ce850529ad52682802cb47f5184a2de02"
    )
    assert payload["contract_digest"] == digest(contract_payload())
    unsigned = dict(payload)
    unsigned.pop("qualification_fingerprint")
    assert payload["qualification_fingerprint"] == digest(unsigned)


def test_qualification_preserves_non_autonomous_successor_gate() -> None:
    payload = evidence()
    assert payload["autonomous_action"] == "PROHIBITED"
    assert payload["successor_gate"] == {
        "milestone_id": "BANK.BEA.006",
        "state": "BLOCKED_PENDING_BANK_BEA_005_OWNER_ACCEPTANCE",
    }
