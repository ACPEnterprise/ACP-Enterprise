from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import stat
from argparse import Namespace
from pathlib import Path

import pytest

from scripts import verify_protected_rehearsal as verifier


def resilience_module():
    script = Path(__file__).parents[3] / "scripts" / "platform-resilience"
    loader = importlib.machinery.SourceFileLoader("protected_resilience", str(script))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def seal(payload: dict[str, object]) -> dict[str, object]:
    payload["digest"] = hashlib.sha256(verifier.canonical(payload)).hexdigest()
    return payload


def private_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)
    return path


def evidence(tmp_path: Path) -> Namespace:
    candidate = "c" * 40
    baseline = "b" * 40
    baseline_head = "old_head"
    expected_head = "new_head"
    database_identity = "isolated-protected-rehearsal"
    backup = tmp_path / "baseline.dump"
    backup.write_bytes(b"synthetic custom-format backup")
    backup.chmod(0o600)
    backup_sha = hashlib.sha256(backup.read_bytes()).hexdigest()
    private_json(
        tmp_path / "baseline.dump.manifest.json",
        {
            "authority_sha": baseline,
            "backup_file": backup.name,
            "contract_version": "platform-resilience.backup.v1",
            "database_identity": "approved-preview-baseline",
            "environment": "preview-isolated",
            "format": "postgresql-custom",
            "schema_head": baseline_head,
            "sha256": backup_sha,
            "size_bytes": backup.stat().st_size,
        },
    )
    private_json(
        tmp_path / "restore.json",
        seal(
            {
                "contract": "platform-resilience.restore-receipt.v2",
                "database_name": "acp_resilience_restore_qualification",
                "environment": "preview-isolated",
                "restored_at": "2026-11-25T12:00:00+00:00",
                "source_authority_sha": baseline,
                "source_database_identity": "approved-preview-baseline",
                "source_schema_head": baseline_head,
                "source_sha256": backup_sha,
                "target_identity": database_identity,
                "target_was_empty": True,
            }
        ),
    )
    private_json(
        tmp_path / "migration.json",
        seal(
            {
                "alembic_check": "PASS",
                "candidate_sha": candidate,
                "contract": "enterprise-release.migration-rehearsal/v1",
                "database_identity": database_identity,
                "expected_head": expected_head,
                "idempotent_reupgrade": True,
                "observed_after_head": expected_head,
                "observed_before_head": baseline_head,
                "single_head": True,
            }
        ),
    )
    safe = {
        "bypassrls": False,
        "createdb": False,
        "createrole": False,
        "login": True,
        "replication": False,
        "superuser": False,
    }
    private_json(
        tmp_path / "roles.json",
        seal(
            {
                "application_connection_role": "acp_app",
                "backup_connection_role": "acp_backup",
                "candidate_sha": candidate,
                "contract": "enterprise-release.database-role-rehearsal/v1",
                "cross_tenant_read_denied": True,
                "cross_tenant_write_denied": True,
                "database_identity": database_identity,
                "migration_connection_role": "acp_migrate",
                "object_owner": "acp_schema_owner",
                "roles": {
                    "acp_app": safe,
                    "acp_backup": {**safe, "bypassrls": True},
                    "acp_migrate": {
                        **safe,
                        "member_of": ["acp_schema_owner"],
                    },
                    "acp_schema_owner": {**safe, "login": False},
                },
            }
        ),
    )
    private_json(
        tmp_path / "readiness.json",
        seal(
            {
                "application_role": "acp_app",
                "candidate_sha": candidate,
                "contract": "enterprise-release.application-readiness-rehearsal/v1",
                "database_identity": database_identity,
                "schema_head": expected_head,
                "state": "HEALTHY",
            }
        ),
    )
    private_json(
        tmp_path / "rollback.json",
        seal(
            {
                "baseline_sha": baseline,
                "candidate_sha": candidate,
                "contract": "enterprise-release.rollback-rehearsal/v1",
                "data_digest_after": "d" * 64,
                "data_digest_before": "d" * 64,
                "restored_head": baseline_head,
                "source_backup_sha256": backup_sha,
                "target_identity": "isolated-rollback-rehearsal",
                "verified": True,
            }
        ),
    )
    return Namespace(
        backup_manifest=tmp_path / "baseline.dump.manifest.json",
        baseline_sha=baseline,
        candidate_sha=candidate,
        expected_head=expected_head,
        migration_evidence=tmp_path / "migration.json",
        output=tmp_path / "verified.json",
        readiness_evidence=tmp_path / "readiness.json",
        restore_receipt=tmp_path / "restore.json",
        role_evidence=tmp_path / "roles.json",
        rollback_evidence=tmp_path / "rollback.json",
    )


def test_complete_rehearsal_is_bound_and_sealed(tmp_path: Path) -> None:
    args = evidence(tmp_path)

    result = verifier.verify(args)
    verifier.write_private(args.output, result)

    assert result["release_decision"] == "QUALIFIED_FOR_INDEPENDENT_REVIEW"
    assert set(result["checks"].values()) == {"PASS"}
    assert result["deployment_authorized"] is False
    assert args.output.stat().st_mode & 0o777 == 0o600


def test_stale_schema_evidence_fails_closed(tmp_path: Path) -> None:
    args = evidence(tmp_path)
    args.expected_head = "unexpected_head"

    with pytest.raises(verifier.RehearsalEvidenceError, match="migration evidence"):
        verifier.verify(args)


def test_backup_tampering_fails_before_acceptance(tmp_path: Path) -> None:
    args = evidence(tmp_path)
    (tmp_path / "baseline.dump").write_bytes(b"tampered")

    with pytest.raises(verifier.RehearsalEvidenceError, match="backup size"):
        verifier.verify(args)


def test_application_bypassrls_is_rejected(tmp_path: Path) -> None:
    args = evidence(tmp_path)
    roles_path = args.role_evidence
    roles = json.loads(roles_path.read_text(encoding="utf-8"))
    roles.pop("digest")
    roles["roles"]["acp_app"]["bypassrls"] = True
    private_json(roles_path, seal(roles))

    with pytest.raises(verifier.RehearsalEvidenceError, match="acp_app role flag"):
        verifier.verify(args)


def test_restore_receipt_verifier_rejects_binding_mismatch(tmp_path: Path) -> None:
    module = resilience_module()
    receipt = {
        "contract": module.RESTORE_RECEIPT_CONTRACT,
        "database_name": "acp_resilience_restore_test",
        "environment": "test",
        "restored_at": "2026-11-25T12:00:00+00:00",
        "source_authority_sha": "a" * 40,
        "source_database_identity": "source",
        "source_schema_head": "head_a",
        "source_sha256": "b" * 64,
        "target_identity": "isolated-target",
        "target_was_empty": True,
    }
    receipt["digest"] = module.payload_digest(receipt)
    path = private_json(tmp_path / "restore.json", receipt)

    with pytest.raises(ValueError, match="source_schema_head"):
        module.verify_restore_receipt(
            Namespace(
                expected_authority_sha="a" * 40,
                expected_backup_sha256="b" * 64,
                expected_schema_head="head_b",
                expected_target_identity="isolated-target",
                receipt=str(path),
            )
        )


def test_private_evidence_writer_refuses_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    verifier.write_private(path, {"qualified": True})

    with pytest.raises(verifier.RehearsalEvidenceError, match="overwrite"):
        verifier.write_private(path, {"qualified": False})

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
