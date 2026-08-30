import hashlib
import json
from pathlib import Path

PATH = (
    Path(__file__).parents[3]
    / "docs/architecture/beacon/operational-intelligence-portfolio-qualification.v1.json"
)


def test_portfolio_qualification_fingerprint_and_gates_are_deterministic() -> None:
    payload = json.loads(PATH.read_text(encoding="utf-8"))
    expected = payload.pop("qualification_fingerprint")
    actual = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    assert expected == actual
    assert payload["intelligence_contract"] == "BEACON.INTELLIGENCE.v1"
    assert payload["state"] == "QUALIFIED_INTEGRATION_READY_WITH_EXPLICIT_GATES"
    assert payload["explicit_gates"]["financial_signals_007b"] == (
        "BLOCKED_FINANCE_POLICY"
    )
    assert payload["explicit_gates"]["external_signals_007c"] == (
        "BLOCKED_SOURCE_ACCEPTANCE"
    )
