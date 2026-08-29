import hashlib
import json
from pathlib import Path

from app.beacon.catalog import NATIVE_FINANCIAL_SIGNAL_CATALOG


def test_bank_bea_007a_owner_acceptance_is_digest_bound() -> None:
    path = (
        Path(__file__).parents[3]
        / "docs/architecture/beacon/bank-bea-007a-acceptance.v1.json"
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    fingerprint = raw.pop("acceptance_fingerprint")
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"))

    assert hashlib.sha256(canonical.encode()).hexdigest() == fingerprint
    assert raw["implementation_sha"] == (
        "f6a1e45acf4600b90d260be5eec030fb85c91ede"
    )
    assert raw["catalog_digest"] == NATIVE_FINANCIAL_SIGNAL_CATALOG.catalog_digest
    assert raw["state"] == "COMPLETE_ACCEPTED"
    assert raw["successor_gates"] == {
        "BANK.BEA.007B": "BLOCKED_FINANCE_POLICY",
        "BANK.BEA.007C": "BLOCKED_SOURCE_ACCEPTANCE",
        "BANK.BEA.008": "BLOCKED_PARENT_INCOMPLETE",
    }


def test_parent_bank_authority_is_not_falsely_completed() -> None:
    path = (
        Path(__file__).parents[2]
        / "app/engineering_control/scheduler/milestone-authority.v1.json"
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    completed = {
        item["bank_milestone_id"] for item in raw["completion_evidence"]
    }
    assert "BANK.BEA.007" not in completed
