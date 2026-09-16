from __future__ import annotations

import base64
import json
from pathlib import Path

from scripts.production_release_preflight import inspect


def _write_environment(tmp_path: Path) -> Path:
    protected = tmp_path / "protected"
    redis = tmp_path / "redis"
    evidence = tmp_path / "evidence"
    for directory in (protected, redis, evidence):
        directory.mkdir(mode=0o700)
    encoded_key = base64.urlsafe_b64encode(b"k" * 32).decode()
    for path in (
        protected / "identity-onboarding-delivery-keyring.json",
        protected / "payroll-input-encryption-keyring.json",
    ):
        path.write_text(json.dumps({"production-key": encoded_key}), encoding="utf-8")
        path.chmod(0o600)
    redis_password = redis / "application-password"
    redis_password.write_text("fixture", encoding="utf-8")
    redis_password.chmod(0o600)
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
                "TRUST_FORWARDED_HEADERS=true",
                'TRUSTED_PROXY_CIDRS=["172.31.0.0/24"]',
                "SECURITY_HEADERS_ENABLED=true",
                "HSTS_ENABLED=true",
                "HSTS_MAX_AGE_SECONDS=31536000",
                "HSTS_INCLUDE_SUBDOMAINS=true",
                'ACCESS_TOKEN_KEYS={"production-1":"' + ("d" * 32) + '"}',
                "ACCESS_TOKEN_ACTIVE_KID=production-1",
                f"SECURITY_TOKEN_HMAC_KEY={'e' * 32}",
                "IDENTITY_ONBOARDING_ACTIVE_DELIVERY_KID=production-key",
                "PAYROLL_INPUT_ACTIVE_KID=production-key",
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


def test_preflight_rejects_malformed_or_inactive_keyrings(tmp_path: Path) -> None:
    env_file = _write_environment(tmp_path)
    values = dict(
        line.split("=", 1)
        for line in env_file.read_text(encoding="utf-8").splitlines()
        if line
    )
    protected = Path(values["PRODUCTION_PROTECTED_SECRET_DIR_HOST"])
    identity = protected / "identity-onboarding-delivery-keyring.json"
    identity.write_text(json.dumps({"different-key": "not-base64"}), encoding="utf-8")
    identity.chmod(0o600)

    findings = {item.check: item.status for item in inspect(env_file)}
    assert findings["identity_delivery_keyring"] == "BLOCKED"
    assert findings["protected_input_keyring"] == "READY"


def test_preflight_rejects_host_substrings_wildcards_and_unbounded_proxy(
    tmp_path: Path,
) -> None:
    env_file = _write_environment(tmp_path)
    contents = (
        env_file.read_text(encoding="utf-8")
        .replace(
            'ALLOWED_HOSTS=["app.twelve-hats.com","backend"]',
            'ALLOWED_HOSTS=["evil-app.twelve-hats.com","*"]',
        )
        .replace(
            'TRUSTED_PROXY_CIDRS=["172.31.0.0/24"]', 'TRUSTED_PROXY_CIDRS=["0.0.0.0/0"]'
        )
    )
    env_file.write_text(contents, encoding="utf-8")
    env_file.chmod(0o600)

    findings = {item.check: item.status for item in inspect(env_file)}
    assert findings["production_edge_identity"] == "BLOCKED"
    assert findings["production_transport_security"] == "BLOCKED"
