from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from app.operational_migration.hcp_current_overlay import (
    CurrentOverlayManifest,
    OverlayAssertion,
    OverlayRecord,
)
from app.operational_migration.hcp_current_overlay_command import (
    COMMAND_CONTRACT,
    RESTORE_RECEIPT_CONTRACT,
    CurrentOverlayExecutionAuthority,
)

DIGEST = "a" * 64
DELTA = "b" * 64
ACQUIRED = "2026-09-12T17:00:00+00:00"


def _write(path: Path, value: object) -> str:
    path.write_text(json.dumps(value))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _authority(tmp_path: Path) -> tuple[Path, CurrentOverlayExecutionAuthority]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    company_id, branch_id, actor_id = uuid4(), uuid4(), uuid4()
    manifest = CurrentOverlayManifest.build(
        base_source4_digest=DIGEST,
        delta_digest=DELTA,
        company_id=str(company_id),
        branch_id=str(branch_id),
        acquired_at=ACQUIRED,
        records=(
            OverlayRecord(
                "customer",
                "cus_1",
                OverlayAssertion.CREATE,
                DELTA,
                ACQUIRED,
                {"first_name": "Ada", "last_name": "Lovelace"},
            ),
        ),
    )
    overlay = tmp_path / "overlay.json"
    hold = tmp_path / "holds.json"
    classification = tmp_path / "classification.json"
    backup = tmp_path / "backup.dump"
    restore = tmp_path / "restore.json"
    overlay_digest = _write(overlay, manifest.private_payload())
    hold_digest = _write(hold, {"contract": "holds/v1"})
    classification_result_digest = "c" * 64
    classification_digest = _write(
        classification,
        {
            "digest": classification_result_digest,
            "report": {"canonical_admission_allowed": False},
        },
    )
    backup.write_bytes(b"qualified backup")
    backup_digest = hashlib.sha256(backup.read_bytes()).hexdigest()
    restore_digest = _write(
        restore,
        {
            "contract": RESTORE_RECEIPT_CONTRACT,
            "backup_digest": backup_digest,
            "restore_verified": True,
            "schema_head": "head",
        },
    )
    idempotency = hashlib.sha256(
        json.dumps(
            {
                "contract": COMMAND_CONTRACT,
                "manifest_digest": manifest.digest,
                "backup_digest": backup_digest,
                "company_id": str(company_id),
                "branch_id": str(branch_id),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    authority = CurrentOverlayExecutionAuthority(
        expected_repository_sha="d" * 40,
        expected_schema_head="head",
        expected_database="acp_enterprise_preview",
        company_id=company_id,
        branch_id=branch_id,
        actor_id=actor_id,
        master_run_id=uuid4(),
        customer_run_id=uuid4(),
        operational_run_id=uuid4(),
        overlay_path=overlay,
        overlay_file_digest=overlay_digest,
        overlay_manifest_digest=manifest.digest,
        hold_path=hold,
        hold_digest=hold_digest,
        classification_path=classification,
        classification_digest=classification_digest,
        classification_result_digest=classification_result_digest,
        expected_base_source4_digest=DIGEST,
        backup_path=backup,
        backup_digest=backup_digest,
        restore_receipt_path=restore,
        restore_receipt_digest=restore_digest,
        idempotency_identity=idempotency,
        zero_migration_drift=True,
        expected_classification_admission_allowed=False,
        current_operational_admission_allowed=True,
    )
    path = tmp_path / "authority.json"
    value = {
        "contract": COMMAND_CONTRACT,
        **{
            key: str(item) if isinstance(item, (Path, type(company_id))) else item
            for key, item in authority.__dict__.items()
        },
    }
    _write(path, value)
    os.chmod(path, 0o600)
    return path, authority


def test_authority_loads_and_verifies_every_bound_artifact(tmp_path: Path) -> None:
    path, expected = _authority(tmp_path)
    loaded = CurrentOverlayExecutionAuthority.load(path)
    assert loaded == expected
    assert loaded.verify_artifacts().digest == expected.overlay_manifest_digest


def test_authority_rejects_tamper_and_unverified_restore(tmp_path: Path) -> None:
    _, authority = _authority(tmp_path)
    authority.hold_path.write_text("tampered")
    with pytest.raises(ValueError, match="artifact mismatch"):
        authority.verify_artifacts()

    _, authority = _authority(tmp_path / "second")
    restore = json.loads(authority.restore_receipt_path.read_bytes())
    restore["restore_verified"] = False
    authority.restore_receipt_path.write_text(json.dumps(restore))
    object.__setattr__(
        authority,
        "restore_receipt_digest",
        hashlib.sha256(authority.restore_receipt_path.read_bytes()).hexdigest(),
    )
    with pytest.raises(ValueError, match="restore receipt"):
        authority.verify_artifacts()
