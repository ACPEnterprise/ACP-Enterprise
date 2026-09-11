import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.operational_migration.hcp_legacy_projection_classification import (
    LegacyProjectionDisposition,
    LegacyProjectionRecord,
)
from app.operational_migration.hcp_legacy_projection_preview_command import (
    _write_once,
    build_qualified_manifest,
)
from app.operational_migration.hcp_migration2_runner import SafeEvidenceError
from app.operational_migration.hcp_successor_reconciliation import SealedIdentity
from app.operational_migration.hcp_successor_reuse import AdmissionDisposition


def test_builds_blocked_replay_manifest_with_exact_reuse() -> None:
    exact = LegacyProjectionRecord(
        domain="customer",
        source_id="legacy",
        disposition=LegacyProjectionDisposition.EXACT_SUCCESSOR,
        evidence_digest="1" * 64,
        target_id=str(uuid4()),
        successor_source_id="sealed",
    )
    classification = SimpleNamespace(
        records=(exact,),
        report=SimpleNamespace(
            safe_digest="2" * 64, canonical_admission_allowed=False
        ),
    )
    result = build_qualified_manifest(
        company_id=uuid4(),
        branch_id=uuid4(),
        classification=classification,
        sealed=(
            SealedIdentity("customer", "sealed"),
            SealedIdentity("job", "new-job"),
        ),
    )
    assert [item.disposition for item in result.entries] == [
        AdmissionDisposition.REUSE_EXACT_SUCCESSOR,
        AdmissionDisposition.CREATE_NEW,
    ]
    assert result.canonical_reconciliation_admission_allowed is False


def test_write_once_is_replay_safe_and_refuses_replacement(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    target = tmp_path / "packet.json"
    payload = json.dumps({"digest": "1" * 64}).encode()
    _write_once(target, payload)
    _write_once(target, payload)
    assert target.read_bytes() == payload
    assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(SafeEvidenceError, match="classification_output_conflict"):
        _write_once(target, b"different")
