import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _compose(path: str) -> dict[str, object]:
    return yaml.safe_load((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))


def test_compose_state_images_are_immutable() -> None:
    for compose_name in (
        "docker-compose.yml",
        "docker-compose.preview.yml",
        "docker-compose.migration-rehearsal.yml",
        "docker-compose.redis-qualification.yml",
        "docker-compose.release-qualification.yml",
    ):
        services = _compose(compose_name)["services"]
        for service_name in ("postgres", "redis"):
            service = services.get(service_name)
            if service is not None:
                assert "@sha256:" in service["image"]


def test_release_qualification_access_token_keys_use_runtime_mapping_shape() -> None:
    compose = _compose("docker-compose.release-qualification.yml")
    environment = compose["services"]["qualifier"]["environment"]
    encoded_keys = environment["ACCESS_TOKEN_KEYS"]

    assert json.loads(encoded_keys) == {
        "release-qualification": "release-qualification-disposable-signing-key-32-bytes"
    }
    assert len(environment["SECURITY_TOKEN_HMAC_KEY"]) >= 32
    assert (
        environment["SECURITY_TOKEN_HMAC_KEY"]
        != environment["INVITATION_TOKEN_HMAC_KEY"]
    )


def test_development_service_ports_are_loopback_only() -> None:
    compose = _compose("docker-compose.yml")

    assert compose["services"]["postgres"]["ports"] == ["127.0.0.1:5432:5432"]
    assert compose["services"]["redis"]["ports"] == ["127.0.0.1:6379:6379"]
    assert compose["services"]["backend"]["ports"] == ["127.0.0.1:8000:8000"]


def test_preview_infrastructure_does_not_publish_a_host_port() -> None:
    compose = _compose("docker-compose.preview.yml")

    assert "ports" not in compose["services"]["postgres"]
    assert "ports" not in compose["services"]["redis"]
    assert "ports" not in compose["services"]["backend"]


def test_application_acceptance_backend_waits_for_schema_and_bootstrap() -> None:
    compose = _compose("docker-compose.application-acceptance.yml")
    depends_on = compose["services"]["backend"]["depends_on"]

    assert compose["services"]["postgres"]["ports"] == [
        "127.0.0.1:${ACCEPTANCE_POSTGRES_PORT:-15432}:5432"
    ]
    assert depends_on["postgres"]["condition"] == "service_healthy"
    assert depends_on["redis"]["condition"] == "service_healthy"
    assert depends_on["bootstrap"]["condition"] == "service_completed_successfully"


@pytest.mark.parametrize(
    ("override", "expected"),
    ((None, "15432"), ("25432", "25432")),
)
def test_application_acceptance_postgres_port_interpolates_safely(
    override: str | None, expected: str
) -> None:
    """Verify Compose's default and explicit loopback-only port contracts."""
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose is required to verify interpolation")
    environment = os.environ.copy()
    environment.update(
        {
            "ACCEPTANCE_ADMIN_PASSWORD": "disposable-admin-password",
            "ACCEPTANCE_APP_PASSWORD": "disposable-app-password",
            "ACCEPTANCE_MIGRATE_PASSWORD": "disposable-migrate-password",
            "ACCEPTANCE_BACKUP_PASSWORD": "disposable-backup-password",
            "ACCEPTANCE_OWNER_PASSWORD": "disposable-owner-password",
        }
    )
    if override is None:
        environment.pop("ACCEPTANCE_POSTGRES_PORT", None)
    else:
        environment["ACCEPTANCE_POSTGRES_PORT"] = override
    completed = subprocess.run(
        (
            "docker",
            "compose",
            "-f",
            "docker-compose.application-acceptance.yml",
            "config",
            "--format",
            "json",
        ),
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    rendered = json.loads(completed.stdout)
    port = rendered["services"]["postgres"]["ports"][0]
    assert port["host_ip"] == "127.0.0.1"
    assert port["published"] == expected
    assert port["target"] == 5432


def test_disposable_qualification_services_are_internal_only() -> None:
    for compose_name, network_name in (
        ("docker-compose.migration-rehearsal.yml", "migration_rehearsal"),
        ("docker-compose.redis-qualification.yml", "qualification"),
        ("docker-compose.release-qualification.yml", "qualification"),
    ):
        compose = _compose(compose_name)
        assert compose["networks"][network_name]["internal"] is True
        for service in compose["services"].values():
            assert "ports" not in service


def test_redis_qualification_uses_production_acl_and_secret_indirection() -> None:
    compose = _compose("docker-compose.redis-qualification.yml")
    redis = compose["services"]["redis"]
    qualification = compose["services"]["qualification"]

    assert "--aclfile" in redis["command"]
    assert redis["command"][redis["command"].index("--protected-mode") + 1] == "yes"
    assert "--user acp-health" in redis["healthcheck"]["test"][1]
    assert qualification["environment"]["REDIS_USERNAME"] == "acp-application"
    assert qualification["environment"]["REDIS_PASSWORD_FILE"].startswith(
        "/run/secrets/"
    )
    assert "REDIS_PASSWORD" not in qualification["environment"]
    assert compose["secrets"]["redis_qualification_acl"]["file"].endswith("/users.acl")


def test_release_qualification_has_fresh_restore_and_readiness_targets() -> None:
    compose = _compose("docker-compose.release-qualification.yml")
    services = compose["services"]

    assert services["postgres"]["image"].startswith("postgres:16-alpine@sha256:")
    assert services["restore-postgres"]["image"] == services["postgres"]["image"]
    assert services["postgres"]["volumes"] != services["restore-postgres"]["volumes"]
    for service_name in ("postgres", "restore-postgres"):
        service = services[service_name]
        assert service["environment"]["POSTGRES_PASSWORD_FILE"] == (
            "/run/secrets/postgres-password"
        )
        assert service["environment"]["POSTGRES_INITDB_ARGS"] == "--encoding=UTF8"
        assert "POSTGRES_PASSWORD" not in service["environment"]
    assert services["readiness"]["depends_on"]["restore-postgres"]["condition"] == (
        "service_healthy"
    )
    assert services["readiness"]["depends_on"]["redis"]["condition"] == (
        "service_healthy"
    )
    assert "/health/ready" in services["readiness"]["healthcheck"]["test"][3]


def test_preview_application_runtimes_are_hardened() -> None:
    compose = _compose("docker-compose.preview.yml")
    services = compose["services"]

    for service_name in (
        "migrate",
        "backend",
        "mission-control-api",
        "mission-control-web",
        "identity-delivery-worker",
        "frontend",
    ):
        service = services[service_name]
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in service["security_opt"]
        assert service["tmpfs"]

    for service_name in ("mission-control-web", "frontend"):
        service = services[service_name]
        assert service["user"] == "101:101"
        assert "/var/cache/nginx:size=32m,mode=0755,uid=101,gid=101" in service["tmpfs"]
        assert "/var/run:size=4m,mode=0755,uid=101,gid=101" in service["tmpfs"]

    # These bounded jobs require root only to establish ownership on named volumes.
    for initializer_name in ("qbo-sandbox-init", "qbo-production-init"):
        initializer = services[initializer_name]
        assert initializer["user"] == "root"
        assert initializer["restart"] == "no"

    production_init = services["qbo-production-init"]
    command = " ".join(production_init["command"])
    assert "chown acp:acp /var/lib/acp-qbo-production" in command
    assert "chmod 700 /var/lib/acp-qbo-production" in command


def test_preview_migrations_use_a_separate_maintenance_database_identity() -> None:
    compose = _compose("docker-compose.preview.yml")

    runtime_database_url = compose["x-backend-environment"]["DATABASE_URL"]
    migration_database_url = compose["services"]["migrate"]["environment"][
        "DATABASE_URL"
    ]

    assert runtime_database_url == "${DATABASE_URL:?Set DATABASE_URL in .env.preview}"
    assert migration_database_url == (
        "${MIGRATION_DATABASE_URL:?Set MIGRATION_DATABASE_URL in .env.preview}"
    )
    assert migration_database_url != runtime_database_url
    assert (
        compose["services"]["migrate"]["command"][-1]
        .strip()
        .endswith("python -m app.platform.permissions.sync_catalog")
    )


def test_preview_backup_service_mounts_protected_backup_secret() -> None:
    compose = _compose("docker-compose.preview.yml")
    backup = compose["services"]["backup"]

    assert backup["profiles"] == ["backup"]
    assert backup["image"].startswith("postgres:16-alpine@sha256:")
    assert (
        backup["environment"]["PGUSER"] == "${PREVIEW_BACKUP_DATABASE_USER:-acp_backup}"
    )
    assert backup["environment"]["BACKUP_PASSWORD_FILE"] == (
        "/run/secrets/acp_backup_password"
    )
    assert backup["secrets"] == [
        {"source": "preview_backup_password", "target": "acp_backup_password"}
    ]
    assert any(":/backups" in volume for volume in backup["volumes"])
    command = " ".join(backup["command"])
    assert "pg_dump --format=custom" in command
    assert "pg_restore --list" in command
    assert 'mktemp "$$BACKUP_ROOT/.preview-$$timestamp.dump.XXXXXX"' in command
    assert compose["secrets"]["preview_backup_password"]["file"] == (
        "${PREVIEW_BACKUP_SECRET_FILE_HOST:?Set PREVIEW_BACKUP_SECRET_FILE_HOST in .env.preview}"
    )


def test_worker_provisioner_and_runtime_mount_the_same_private_key() -> None:
    compose = _compose("docker-compose.preview.yml")
    worker = compose["services"]["worker"]
    provisioner = compose["services"]["worker-provision"]
    env_example = (REPOSITORY_ROOT / ".env.preview.example").read_text(encoding="utf-8")

    runtime_mounts = worker["volumes"]
    provisioner_mounts = provisioner["volumes"]
    assert (
        "${ACP_WORKER_PRIVATE_KEY_FILE_HOST:-/opt/acp-enterprise/shared/secrets/worker-preview/preview-worker.key}"
        ":/run/secrets/preview-worker.key:ro"
    ) in runtime_mounts
    assert (
        "${ACP_WORKER_SECRET_DIRECTORY_HOST:-/opt/acp-enterprise/shared/secrets/worker-preview}"
        ":/run/secrets"
    ) in provisioner_mounts
    assert (
        "ACP_WORKER_PRIVATE_KEY_FILE_HOST=/opt/acp-enterprise/shared/secrets/worker-preview/preview-worker.key"
        in env_example
    )


def test_preview_backend_images_include_release_security_executables() -> None:
    compose = _compose("docker-compose.preview.yml")
    for service in compose["services"].values():
        if "build" not in service:
            continue
        if service["build"].get("dockerfile") != "backend/Dockerfile.preview":
            continue
        assert service["build"]["context"] == "."
        assert service["build"]["dockerfile"] == "backend/Dockerfile.preview"

    dockerfile = (REPOSITORY_ROOT / "backend/Dockerfile.preview").read_text(
        encoding="utf-8"
    )
    assert (
        "COPY --chown=acp:acp scripts/protected-database-security-probe.py"
        in dockerfile
    )
    assert "COPY --chown=acp:acp scripts/protected-runtime-check.py" in dockerfile
    assert "COPY --chown=acp:acp scripts/protected-smoke-check.py" in dockerfile


def test_preview_network_ranges_are_overrideable_for_isolated_rehearsals() -> None:
    compose = _compose("docker-compose.preview.yml")
    networks = compose["networks"]

    assert networks["preview"]["ipam"]["config"][0]["subnet"] == (
        "${PREVIEW_NETWORK_SUBNET:-172.30.0.0/24}"
    )
    assert networks["mission-control"]["ipam"]["config"][0]["subnet"] == (
        "${MISSION_CONTROL_NETWORK_SUBNET:-172.32.0.0/24}"
    )


def test_migration_role_can_create_trusted_extensions_without_elevating_app() -> None:
    sql = (REPOSITORY_ROOT / "scripts/qualify-database-roles.sql").read_text(
        encoding="utf-8"
    )

    assert "GRANT CREATE ON DATABASE" in sql
    assert "TO acp_schema_owner" in sql
    assert "ALTER ROLE acp_app NOSUPERUSER" in sql
    assert "NOBYPASSRLS" in sql


def test_preview_redis_requires_acl_file_and_secret_indirection() -> None:
    compose = _compose("docker-compose.preview.yml")
    redis = compose["services"]["redis"]
    backend = compose["services"]["backend"]

    command = redis["command"]
    assert "--aclfile" in command
    assert command[command.index("--protected-mode") + 1] == "yes"
    assert command[command.index("--appendonly") + 1] == "no"
    assert command[command.index("--save") + 1] == ""
    assert any("/run/secrets/redis:ro" in volume for volume in redis["volumes"])
    assert any("/run/secrets/redis:ro" in volume for volume in backend["volumes"])
    assert "REDIS_PASSWORD" not in compose["x-backend-environment"]
    assert compose["x-backend-environment"]["REDIS_PASSWORD_FILE"].startswith(
        "/run/secrets/"
    )


def test_acl_renderer_disables_default_and_denies_admin_commands() -> None:
    renderer = (REPOSITORY_ROOT / "scripts/render-redis-acl").read_text(
        encoding="utf-8"
    )

    assert "user default off" in renderer
    assert "user acp-application" in renderer
    assert "user acp-health" in renderer
    assert "user acp-breakglass" in renderer
    for command in (
        "config",
        "module",
        "replicaof",
        "slaveof",
        "shutdown",
        "flushall",
        "flushdb",
        "debug",
        "migrate",
    ):
        assert f"-{command}" in renderer
