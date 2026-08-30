import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "docs/architecture/business-economics-independent-acceptance-1.json"


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_independent_acceptance_evidence_is_deterministic_and_non_autonomous() -> None:
    evidence = json.loads(PATH.read_text(encoding="utf-8"))
    unsigned = dict(evidence)
    fingerprint = unsigned.pop("qualification_fingerprint")
    assert fingerprint == _digest(unsigned)
    assert evidence["autonomous_action"] == "PROHIBITED"
    assert evidence["production"] == "UNTOUCHED"
    assert evidence["repairs"][0] == "P0_duplicate_source_lineage_double_count"
    assert evidence["double_counting_boundaries"]["qbo_plus_acp"] == (
        "qbo_source_reported_not_accepted_native_truth"
    )
