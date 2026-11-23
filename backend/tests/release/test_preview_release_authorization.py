from __future__ import annotations

import base64
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

ROOT = Path(__file__).resolve().parents[3]


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def approval_fixture(tmp_path: Path) -> tuple[object, Path, Path, dict[str, object]]:
    module = load("preview_approval", "validate-preview-approval.py")
    private = Ed25519PrivateKey.generate()
    public_path = tmp_path / "issuer-public.pem"
    public_path.write_bytes(
        private.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    )
    public_path.chmod(0o600)
    issued = datetime.now(timezone.utc) - timedelta(minutes=1)
    unsigned: dict[str, object] = {
        "contract": module.CONTRACT,
        "approval_id": "3b241101-e2bb-4255-8caf-4136c566a962",
        "candidate_sha": "a" * 40,
        "migration_head": "s1a3g5k7m9q2",
        "backup_receipt_sha256": "b" * 64,
        "restore_receipt_sha256": "c" * 64,
        "rollback_target": {"sha": "d" * 40, "release": "enterprise-beta-dddddddd"},
        "scope": module.SCOPE,
        "issued_at": issued.isoformat(),
        "expires_at": (issued + timedelta(hours=1)).isoformat(),
        "authorized_issuer": {
            "id": module.ISSUER_ID,
            "role": module.ISSUER_ROLE,
            "key_id": "om1e-preview-2026-01",
        },
    }
    artifact_digest = module.hashlib.sha256(module.canonical(unsigned)).hexdigest()
    signed = {**unsigned, "artifact_digest": artifact_digest}
    signature = private.sign(module.canonical(signed))
    artifact = {
        **signed,
        "signature": {
            "algorithm": "Ed25519",
            "encoding": "base64",
            "value": base64.b64encode(signature).decode("ascii"),
        },
    }
    artifact_path = tmp_path / "approval.json"
    artifact_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    artifact_path.chmod(0o600)
    return module, artifact_path, public_path, artifact


def expected(module: object) -> dict[str, str]:
    return {
        "expected_key_id": "om1e-preview-2026-01",
        "candidate_sha": "a" * 40,
        "migration_head": "s1a3g5k7m9q2",
        "backup_receipt_sha256": "b" * 64,
        "restore_receipt_sha256": "c" * 64,
        "rollback_target_sha": "d" * 40,
        "rollback_target_release": "enterprise-beta-dddddddd",
    }


def test_enterprise_approval_validates_and_binds_all_release_inputs(tmp_path: Path) -> None:
    module, artifact, public_key, _ = approval_fixture(tmp_path)

    result = module.validate_approval(artifact, public_key, **expected(module))

    assert result["issuer"] == "OM1E"
    assert result["scope"] == "BETA_PREVIEW"
    assert result["candidate_sha"] == "a" * 40


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("candidate_sha", "e" * 40, "candidate does not match"),
        ("backup_receipt_sha256", "f" * 64, "backup receipt does not match"),
        ("rollback_target", {"sha": "e" * 40, "release": "wrong"}, "rollback target does not match"),
    ),
)
def test_approval_mismatch_fails_closed(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    module, artifact_path, public_key, artifact = approval_fixture(tmp_path)
    artifact[field] = value
    artifact_path.write_text(json.dumps(artifact) + "\n", encoding="utf-8")
    artifact_path.chmod(0o600)

    with pytest.raises(module.ApprovalError, match=message):
        module.validate_approval(artifact_path, public_key, **expected(module))


def test_approval_expiry_and_untrusted_issuer_fail_closed(tmp_path: Path) -> None:
    module, artifact_path, public_key, artifact = approval_fixture(tmp_path)
    expired = datetime.now(timezone.utc) + timedelta(hours=2)
    artifact["issued_at"] = expired.isoformat()
    artifact["expires_at"] = (expired + timedelta(hours=1)).isoformat()
    artifact_path.write_text(json.dumps(artifact) + "\n", encoding="utf-8")
    artifact_path.chmod(0o600)

    with pytest.raises(module.ApprovalError, match="expired or not yet valid"):
        module.validate_approval(artifact_path, public_key, **expected(module))


def test_approval_artifact_cannot_be_issued_by_candidate(tmp_path: Path) -> None:
    module, artifact_path, public_key, artifact = approval_fixture(tmp_path)
    artifact["authorized_issuer"]["id"] = "LAPTOP_MASTER"  # type: ignore[index]
    artifact_path.write_text(json.dumps(artifact) + "\n", encoding="utf-8")
    artifact_path.chmod(0o600)

    with pytest.raises(module.ApprovalError, match="not the Enterprise release authority"):
        module.validate_approval(artifact_path, public_key, **expected(module))


def test_approval_wrong_scope_is_rejected_as_non_beta_target(tmp_path: Path) -> None:
    module, artifact_path, public_key, artifact = approval_fixture(tmp_path)
    artifact["scope"] = "OTHER_TENANT"
    artifact_path.write_text(json.dumps(artifact) + "\n", encoding="utf-8")
    artifact_path.chmod(0o600)

    with pytest.raises(module.ApprovalError, match="not Beta-only"):
        module.validate_approval(artifact_path, public_key, **expected(module))
