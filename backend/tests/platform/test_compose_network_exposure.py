import json
from pathlib import Path

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

    # These bounded jobs require root only to establish ownership on named volumes.
    for initializer_name in ("qbo-sandbox-init", "qbo-production-init"):
        initializer = services[initializer_name]
        assert initializer["user"] == "root"
        assert initializer["restart"] == "no"


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
