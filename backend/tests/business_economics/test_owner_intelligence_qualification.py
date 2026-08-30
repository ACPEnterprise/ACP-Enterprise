import hashlib
import json
from pathlib import Path

PATH = (
    Path(__file__).resolve().parents[3]
    / "docs/architecture/economics-owner-intelligence-portfolio-qualification.json"
)


def test_owner_intelligence_qualification_is_deterministic_and_read_only() -> None:
    evidence = json.loads(PATH.read_text(encoding="utf-8"))
    unsigned = dict(evidence)
    fingerprint = unsigned.pop("qualification_fingerprint")
    assert (
        fingerprint
        == hashlib.sha256(
            json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    assert evidence["database_contract"]["result_update"] == ("REJECTED_SQLSTATE_55000")
    assert evidence["owner_intelligence"]["mutation_authority"] == "NONE"
    assert evidence["classification"]["lia"] == "ECONOMICS_LIA_READY_READ_ONLY"
    assert evidence["classification"]["production"] == "UNTOUCHED"
