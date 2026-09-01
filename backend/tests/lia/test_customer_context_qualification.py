from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_customer_context_qualification_is_deterministic_and_non_mutating() -> None:
    root = Path(__file__).resolve().parents[3]
    path = (
        root
        / "docs/architecture/lia/customer-context-composition-qualification.v1.json"
    )
    evidence = json.loads(path.read_text())
    expected = evidence.pop("qualification_fingerprint")
    assert expected == _digest(evidence)
    assert evidence["projection_contract"] == "CUSTOMER.LIA_CONTEXT.v1"
    assert evidence["security"]["autonomous_mutation_enabled"] is False
    assert evidence["security"]["ai_provider_called"] is False
    assert evidence["security"]["production_touched"] is False
    assert evidence["validation"]["alembic_head_count"] == 1
