from __future__ import annotations

import importlib.util
import json
import stat
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[3]
CANDIDATE = "a" * 40
TOOLING = "b" * 40
COMPANY = "11111111-1111-4111-8111-111111111111"
BRANCH = "22222222-2222-4222-8222-222222222222"
DENIED = "33333333-3333-4333-8333-333333333333"


def module():
    path = ROOT / "scripts" / "release_evidence_contract.py"
    spec = importlib.util.spec_from_file_location("release_evidence_contract", path)
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def private_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def smoke_payload(mod, provisioner_sha: str, *, token_issued: bool = False):
    return {
        "contract": mod.SMOKE_CONTRACT,
        "candidate_sha": CANDIDATE,
        "tooling_sha": TOOLING,
        "scope": "BETA_PREVIEW",
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "denied_company_id": DENIED,
        "token_path": mod.SMOKE_TOKEN_PATH,
        "token_issued": token_issued,
        "token_required_for_live_acceptance": True,
        "credential_custody": {
            "owner": "root",
            "mode": "0600",
            "mounted_read_only": True,
        },
        "provisioning": {
            "after_signed_approval": True,
            "after_schema_ready": True,
            "procedure_path": mod.PROVISIONER_PATH,
            "procedure_sha256": provisioner_sha,
            "isolated_procedure_passed": True,
        },
    }


def test_pre_signing_smoke_readiness_does_not_require_token(tmp_path: Path) -> None:
    mod = module()
    provisioner = ROOT / mod.PROVISIONER_PATH
    artifact = tmp_path / "smoke.json"
    private_json(artifact, smoke_payload(mod, mod.sha256(provisioner)))

    result = mod.validate_smoke_readiness(
        artifact,
        candidate_sha=CANDIDATE,
        tooling_sha=TOOLING,
        company_id=COMPANY,
        branch_id=BRANCH,
        denied_company_id=DENIED,
        provisioner_path=provisioner,
    )

    assert result["token_state"] == "NOT_ISSUED_PRE_SIGNING"


def test_pre_signing_rejects_issued_or_mismatched_smoke_evidence(
    tmp_path: Path,
) -> None:
    mod = module()
    provisioner = ROOT / mod.PROVISIONER_PATH
    artifact = tmp_path / "smoke.json"
    private_json(
        artifact, smoke_payload(mod, mod.sha256(provisioner), token_issued=True)
    )

    with pytest.raises(ValueError, match="must not contain an issued token"):
        mod.validate_smoke_readiness(
            artifact,
            candidate_sha=CANDIDATE,
            tooling_sha=TOOLING,
            company_id=COMPANY,
            branch_id=BRANCH,
            denied_company_id=DENIED,
            provisioner_path=provisioner,
        )


def test_evidence_binds_application_and_tooling_and_smoke_readiness(
    tmp_path: Path,
) -> None:
    mod = module()
    provisioner = ROOT / mod.PROVISIONER_PATH
    smoke = tmp_path / "smoke.json"
    private_json(smoke, smoke_payload(mod, mod.sha256(provisioner)))
    manifest = tmp_path / "manifest.json"
    private_json(
        manifest,
        {
            "contract": mod.EVIDENCE_CONTRACT,
            "candidate_sha": CANDIDATE,
            "tooling_sha": TOOLING,
            "migration_head": "w2x4z6a8c0e3",
            "backup_receipt_sha256": "c" * 64,
            "restore_receipt_sha256": "d" * 64,
            "rollback_target": {"sha": "e" * 40, "release": "enterprise-beta-e"},
            "smoke_readiness_sha256": mod.sha256(smoke),
        },
    )

    result = mod.validate_evidence_binding(
        manifest,
        smoke,
        candidate_sha=CANDIDATE,
        tooling_sha=TOOLING,
        migration_head="w2x4z6a8c0e3",
        backup_receipt_sha256="c" * 64,
        restore_receipt_sha256="d" * 64,
        rollback_target_sha="e" * 40,
        rollback_target_release="enterprise-beta-e",
        company_id=COMPANY,
        branch_id=BRANCH,
        denied_company_id=DENIED,
        provisioner_path=provisioner,
    )

    assert result["tooling_sha"] == TOOLING

    with pytest.raises(ValueError, match="tooling_sha does not match"):
        mod.validate_evidence_binding(
            manifest,
            smoke,
            candidate_sha=CANDIDATE,
            tooling_sha="f" * 40,
            migration_head="w2x4z6a8c0e3",
            backup_receipt_sha256="c" * 64,
            restore_receipt_sha256="d" * 64,
            rollback_target_sha="e" * 40,
            rollback_target_release="enterprise-beta-e",
            company_id=COMPANY,
            branch_id=BRANCH,
            denied_company_id=DENIED,
            provisioner_path=provisioner,
        )
