from __future__ import annotations

from pathlib import Path


def script() -> str:
    root = Path(__file__).parents[3]
    return (root / "scripts/qualify-release-database").read_text(encoding="utf-8")


def test_recovery_uses_new_empty_database_and_single_transaction_restore() -> None:
    content = script()

    assert "acp_resilience_restore_recovery" in content
    assert 'test "$recovery_existing_relations" = 0' in content
    assert content.count("--single-transaction") >= 2
    assert "DROP DATABASE" not in content
    assert "DROP TABLE qualification_recovery.partial_execution_marker" not in content


def test_injected_failure_must_fail_and_leave_transaction_data_unchanged() -> None:
    content = script()

    assert "intentional isolated migration failure" in content
    assert "transaction failure injection unexpectedly succeeded" in content
    assert 'test "$post_failure_snapshot" = "$probe_snapshot"' in content
    assert 'test "$rolled_back_table" = t' in content


def test_partial_target_is_abandoned_and_reupgrade_is_verified() -> None:
    content = script()

    assert "qualification_recovery.partial_execution_marker" in content
    assert 'test "$recovery_partial_marker" = t' in content
    assert "python -m alembic upgrade head" in content
    assert "python -m alembic check" in content
    assert 'test "$recovery_head" = "$schema_head"' in content
    assert 'test "$recovery_probe_digest" = "$probe_digest"' in content


def test_recovery_credentials_remain_file_backed_and_receipt_cannot_deploy() -> None:
    content = script()

    assert 'database_password="$(cat "$DATABASE_PASSWORD_FILE")"' in content
    assert "enterprise-release.rollback-recovery-qualification/v1" in content
    assert '"new_recovery_target": True' in content
    assert '"transaction_failure_rolled_back": True' in content
    assert "docker compose" in content
    assert " deploy " not in content
