from __future__ import annotations

import json
from pathlib import Path

from scripts.production_release_preflight import inspect


def _write_environment(tmp_path: Path) -> Path:
    protected = tmp_path / "protected"
    redis = tmp_path / "redis"
    evidence = tmp_path / "evidence"
    for directory in (protected, redis, evidence):
        directory.mkdir(mode=0o700)
    for path in (
        protected / "identity-onboarding-delivery-keyring.json",
        protected / "payroll-input-encryption-keyring.json",
        redis / "application-password",
    ):
        path.write_text("fixture", encoding="utf-8")
        path.chmod(0o600)
    env_file = tmp_path / ".env.production"
    env_file.write_text(
        "\n".join(
            (
                f"APP_VERSION={'a' * 40}",
                "PLATFORM_CONTRACT_EXPECTED_FINGERPRINT=qualified-fingerprint",
                f"ACP_BACKEND_IMAGE=registry.example/twelve-hats/backend@sha256:{'b' * 64}",
                f"ACP_FRONTEND_IMAGE=registry.example/twelve-hats/frontend@sha256:{'c' * 64}",
                "DATABASE_URL=postgresql+asyncpg://app:private@db.internal:5432/twelve_hats",
                "REDIS_URL=rediss://app@redis.internal:6379/0",
                "REDIS_USERNAME=app",
                "PRODUCTION_HOSTNAME=app.twelve-hats.com",
                'CORS_ALLOWED_ORIGINS=["https://app.twelve-hats.com"]',
                'ALLOWED_HOSTS=["app.twelve-hats.com","backend"]',
                'ACCESS_TOKEN_KEYS={"production-1":"' + ("d" * 32) + '"}',
                "ACCESS_TOKEN_ACTIVE_KID=production-1",
                f"SECURITY_TOKEN_HMAC_KEY={'e' * 32}",
                f"PRODUCTION_PROTECTED_SECRET_DIR_HOST={protected}",
                f"PRODUCTION_REDIS_SECRET_DIR_HOST={redis}",
                f"PRODUCTION_EVIDENCE_DIR_HOST={evidence}",
                "COMMUNICATIONS_DELIVERY_ENABLED=false",
                "COMMUNICATIONS_WEBHOOK_ENABLED=false",
                "QBO_SANDBOX_ENABLED=false",
                "QBO_PRODUCTION_ENABLED=false",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    env_file.chmod(0o600)
    return env_file


def test_preflight_accepts_structurally_complete_private_configuration(
    tmp_path: Path,
) -> None:
    findings = inspect(_write_environment(tmp_path))
    assert all(item.status in {"READY", "READY BUT UNPROVEN"} for item in findings)
    assert {item.check: item.status for item in findings}[
        "postgresql_endpoint"
    ] == "READY BUT UNPROVEN"


def test_preflight_rejects_mutable_images_wrong_host_and_open_secret_mode(
    tmp_path: Path,
) -> None:
    env_file = _write_environment(tmp_path)
    contents = (
        env_file.read_text(encoding="utf-8")
        .replace(
            f"registry.example/twelve-hats/backend@sha256:{'b' * 64}",
            "registry.example/twelve-hats/backend:latest",
        )
        .replace("app.twelve-hats.com", "preview.allcountyhomeservices.com")
    )
    env_file.write_text(contents, encoding="utf-8")
    env_file.chmod(0o644)
    findings = {item.check: item.status for item in inspect(env_file)}
    assert findings["environment_file_mode"] == "BLOCKED"
    assert findings["acp_backend_image"] == "BLOCKED"
    assert findings["production_edge_identity"] == "BLOCKED"


def test_preflight_report_contains_no_secret_values(tmp_path: Path) -> None:
    findings = inspect(_write_environment(tmp_path))
    rendered = json.dumps([item.__dict__ for item in findings])
    assert "d" * 32 not in rendered
    assert "e" * 32 not in rendered
