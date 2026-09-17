from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (REPOSITORY_ROOT / path).read_text(encoding="utf-8")


def test_backup_is_restricted_atomic_and_validated_before_publication() -> None:
    script = _read("scripts/backup-preview-postgres.sh")

    assert "umask 077" in script
    assert 'install -d -m 700 "$backup_root"' in script
    assert "PREVIEW_POSTGRES_CONTAINER:-acp-enterprise-postgres" in script
    assert "docker inspect" in script
    assert 'docker exec "$postgres_container"' in script
    assert 'docker exec -i "$postgres_container"' in script
    assert "pg_dump" in script
    assert "--format=custom" in script
    assert "pg_restore --list" in script
    assert 'test -s "$temporary_dump"' in script
    assert 'chmod 600 "$temporary_dump"' in script
    assert "sha256sum" in script
    assert '"$(basename "$final_dump")"' in script
    assert 'mv "$temporary_dump" "$final_dump"' in script
    assert "find " not in script


def test_host_audit_fails_closed_for_runtime_disk_and_backup_drift() -> None:
    script = _read("scripts/audit-beta-runtime-host.sh")

    assert "systemctl is-active --quiet caddy" in script
    assert "DISK_WARNING_PERCENT:-85" in script
    assert "DISK_BLOCKER_PERCENT:-90" in script
    assert "(unhealthy\\)|Restarting" in script
    assert "MAX_BACKUP_AGE_HOURS:-26" in script
    assert '"$backup_mode" != "600"' in script
    assert "newest Preview backup has no SHA-256 sidecar" in script
    assert "checksum does not bind the newest dump" in script
    assert "sha256sum --check --status" in script
    assert "latest_preview_backup_checksum=verified" in script
    assert 'script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)' in script
    assert '"$script_dir/verify-beta-connectivity.sh"' in script


def test_backup_timer_is_hardened_and_does_not_delete_history() -> None:
    service = _read("docs/deployment/acp-preview-backup.service.example")
    timer = _read("docs/deployment/acp-preview-backup.timer.example")

    assert "NoNewPrivileges=true" in service
    assert "ProtectSystem=strict" in service
    assert "UMask=0077" in service
    assert "ReadWritePaths=/opt/acp-enterprise/backups /run/docker.sock" in service
    assert "OnCalendar=*-*-* 02:30:00 UTC" in timer
    assert "Persistent=true" in timer
    assert "rm " not in service
    assert "rm " not in timer
