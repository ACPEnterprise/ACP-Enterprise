from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.operational_migration.hcp_migration2_runner import SafeEvidenceError
from app.operational_migration.hcp_november_executor import _digest
from app.operational_migration.hcp_november_payload_materializer import (
    materialize_executable_payloads,
)


def _packet() -> dict:
    return {
        "contract": "hcp-november-bounded-admissible-records/v1",
        "records": [
            {
                "domain": "customer",
                "source_id": "cus_1",
                "disposition": "CREATE",
                "source_digest": "a" * 64,
                "payload_locator": "gate/provider-observations.json#customer:cus_1",
                "parent_lineage": [],
                "payload": {"payload_locator": "stale"},
            },
            {
                "domain": "job",
                "source_id": "job_held",
                "disposition": "HOLD_QUARANTINE",
                "source_digest": "b" * 64,
                "payload_locator": "gate/provider-observations.json#job:job_held",
                "parent_lineage": [],
                "payload": {},
            },
        ],
    }


def _evidence(tmp_path: Path) -> Path:
    root = tmp_path / "bundle"
    (root / "gate").mkdir(parents=True)
    (root / "gate/provider-observations.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "domain": "customer",
                        "source_id": "cus_1",
                        "source_digest": "a" * 64,
                        "parent_keys": [],
                        "payload": {"first_name": "A", "last_name": "B"},
                    }
                ]
            },
            sort_keys=True,
        )
    )
    (root / "gate/provider-observations.json").chmod(0o600)
    return root


def test_materializer_resolves_executable_and_preserves_hold(tmp_path: Path) -> None:
    source = _packet()
    result = materialize_executable_payloads(source, evidence_root=_evidence(tmp_path))
    assert result["records"][0]["payload"] == {"first_name": "A", "last_name": "B"}
    assert result["records"][0]["payload_evidence_sha256"] == hashlib.sha256(
        (tmp_path / "bundle/gate/provider-observations.json").read_bytes()
    ).hexdigest()
    assert result["records"][1] == source["records"][1]
    assert source["records"][0]["payload"] == {"payload_locator": "stale"}


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda item: item.update(payload_locator="missing.json#customer:cus_1"), "hcp_november_payload_source_object_missing"),
        (lambda item: item.update(source_digest="c" * 64), "hcp_november_payload_digest_mismatch"),
        (lambda item: item.update(payload_locator="gate/provider-observations.json#job:cus_1"), "hcp_november_payload_locator_identity_mismatch"),
    ],
)
def test_materializer_fails_closed(tmp_path: Path, mutate, code: str) -> None:
    source = _packet()
    mutate(source["records"][0])
    with pytest.raises(SafeEvidenceError, match=code):
        materialize_executable_payloads(source, evidence_root=_evidence(tmp_path))


def test_materializer_rejects_ambiguous_source(tmp_path: Path) -> None:
    root = _evidence(tmp_path)
    path = root / "gate/provider-observations.json"
    value = json.loads(path.read_text())
    value["records"].append(value["records"][0])
    path.write_text(json.dumps(value, sort_keys=True))
    path.chmod(0o600)
    with pytest.raises(SafeEvidenceError, match="hcp_november_payload_resolution_ambiguous"):
        materialize_executable_payloads(_packet(), evidence_root=root)
