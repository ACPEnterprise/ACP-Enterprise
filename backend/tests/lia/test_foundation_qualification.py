from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
QUALIFICATION_PATH = (
    REPOSITORY_ROOT / "docs/architecture/lia/foundation-qualification.v1.json"
)


def test_foundation_qualification_fingerprint_reloads_deterministically() -> None:
    payload = json.loads(QUALIFICATION_PATH.read_text())
    lines = []
    for relative_path, expected_digest in sorted(payload["inputs"].items()):
        actual_digest = hashlib.sha256(
            (REPOSITORY_ROOT / relative_path).read_bytes()
        ).hexdigest()
        assert actual_digest == expected_digest
        lines.append(f"{relative_path}={actual_digest}")

    fingerprint = hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()
    assert fingerprint == payload["qualification_fingerprint"]


def test_foundation_qualification_never_claims_provider_or_mutation_authority() -> (
    None
):
    payload = json.loads(QUALIFICATION_PATH.read_text())

    assert payload["classification"] == "LIA_FOUNDATION_READY_FOR_PROVIDER_IMPLEMENTATION"
    assert payload["provider_configured"] is False
    assert payload["provider_called"] is False
    assert payload["autonomous_mutation_enabled"] is False
    assert payload["production_touched"] is False
