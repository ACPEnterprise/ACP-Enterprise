from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_preview_migration_runner_requires_separate_maintenance_url() -> None:
    script = (ROOT / "scripts" / "run-preview-migrations.sh").read_text()
    assert '"${MIGRATION_DATABASE_URL:?MIGRATION_DATABASE_URL is required}"' in script
    assert '"${PREVIEW_RELEASE:?PREVIEW_RELEASE must be true}"' in script
    assert 'print(url.username or "")' in script
    assert 'database_user" != "acp_migrate"' in script
    assert "unset DATABASE_URL" in script
    assert "alembic upgrade head" in script


def test_preview_migration_runner_has_no_legacy_fallback_or_url_logging() -> None:
    script = (ROOT / "scripts" / "run-preview-migrations.sh").read_text()
    assert "POSTGRES_USER" not in script
    assert "echo $MIGRATION_DATABASE_URL" not in script
    assert "print(url.password" not in script
