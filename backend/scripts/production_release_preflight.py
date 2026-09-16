from __future__ import annotations

import argparse
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

PRODUCTION_HOSTNAME = "app.twelve-hats.com"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DIGEST_IMAGE_PATTERN = re.compile(r"^\S+@sha256:[0-9a-f]{64}$")
PLACEHOLDER_MARKERS = ("set_", "replace", "change-before-use", "not-for-production")
REQUIRED_PLATFORM_RESOURCES = {
    "runtime",
    "postgresql",
    "redis",
    "object_storage",
    "registry",
    "backup_pitr",
    "monitoring",
    "alert_delivery",
    "dns_tls",
}


@dataclass(frozen=True)
class Finding:
    check: str
    status: str
    reason: str


def load_environment(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"invalid environment line {line_number}")
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _private_file(path: Path, *, check: str) -> Finding:
    if not path.is_file() or path.is_symlink():
        return Finding(check, "BLOCKED", "required regular secret file is unavailable")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != 0o600:
        return Finding(check, "BLOCKED", "secret file mode must be exactly 0600")
    return Finding(check, "READY", "secret file exists with mode 0600")


def _private_directory(path: Path, *, check: str, writable: bool) -> Finding:
    if not path.is_dir() or path.is_symlink():
        return Finding(check, "BLOCKED", "required custody directory is unavailable")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o027:
        return Finding(
            check, "BLOCKED", "custody directory grants group write or other access"
        )
    if writable and not os.access(path, os.W_OK):
        return Finding(
            check,
            "BLOCKED",
            "custody directory is not writable by the release operator",
        )
    return Finding(check, "READY", "custody directory permissions are restricted")


def inspect(env_file: Path) -> list[Finding]:
    values = load_environment(env_file)
    findings: list[Finding] = []
    mode = stat.S_IMODE(env_file.stat().st_mode)
    findings.append(
        Finding(
            "environment_file_mode",
            "READY" if mode == 0o600 else "BLOCKED",
            "environment file mode is 0600"
            if mode == 0o600
            else "environment file mode must be exactly 0600",
        )
    )

    required = {
        "APP_VERSION",
        "PLATFORM_CONTRACT_EXPECTED_FINGERPRINT",
        "ACP_BACKEND_IMAGE",
        "ACP_FRONTEND_IMAGE",
        "DATABASE_URL",
        "REDIS_URL",
        "REDIS_USERNAME",
        "PRODUCTION_HOSTNAME",
        "CORS_ALLOWED_ORIGINS",
        "ALLOWED_HOSTS",
        "ACCESS_TOKEN_KEYS",
        "ACCESS_TOKEN_ACTIVE_KID",
        "SECURITY_TOKEN_HMAC_KEY",
        "PRODUCTION_PROTECTED_SECRET_DIR_HOST",
        "PRODUCTION_REDIS_SECRET_DIR_HOST",
        "PRODUCTION_EVIDENCE_DIR_HOST",
    }
    missing = sorted(key for key in required if not values.get(key))
    findings.append(
        Finding(
            "required_configuration",
            "READY" if not missing else "BLOCKED",
            "all required keys are present"
            if not missing
            else f"missing keys: {','.join(missing)}",
        )
    )

    version = values.get("APP_VERSION", "")
    findings.append(
        Finding(
            "immutable_release_revision",
            "READY" if SHA_PATTERN.fullmatch(version) else "BLOCKED",
            "APP_VERSION is an exact Git SHA"
            if SHA_PATTERN.fullmatch(version)
            else "APP_VERSION must be an exact 40-character Git SHA",
        )
    )
    for key in ("ACP_BACKEND_IMAGE", "ACP_FRONTEND_IMAGE"):
        value = values.get(key, "")
        findings.append(
            Finding(
                key.lower(),
                "READY" if DIGEST_IMAGE_PATTERN.fullmatch(value) else "BLOCKED",
                "image is pinned by sha256 digest"
                if DIGEST_IMAGE_PATTERN.fullmatch(value)
                else "image must be an immutable @sha256 digest reference",
            )
        )

    hostname = values.get("PRODUCTION_HOSTNAME")
    origin_ok = (
        values.get("CORS_ALLOWED_ORIGINS") == f'["https://{PRODUCTION_HOSTNAME}"]'
    )
    host_ok = hostname == PRODUCTION_HOSTNAME and PRODUCTION_HOSTNAME in values.get(
        "ALLOWED_HOSTS", ""
    )
    findings.append(
        Finding(
            "production_edge_identity",
            "READY" if origin_ok and host_ok else "BLOCKED",
            "hostname, trusted host, and CORS origin bind to Twelve Hats Production"
            if origin_ok and host_ok
            else "edge identity must bind exactly to app.twelve-hats.com",
        )
    )

    database = urlparse(values.get("DATABASE_URL", ""))
    db_ok = (
        database.scheme == "postgresql+asyncpg"
        and bool(database.hostname)
        and database.hostname not in {"localhost", "127.0.0.1", "postgres"}
    )
    findings.append(
        Finding(
            "postgresql_endpoint",
            "READY BUT UNPROVEN" if db_ok else "BLOCKED",
            "dedicated nonlocal PostgreSQL endpoint is configured; connectivity remains to be proven"
            if db_ok
            else "PostgreSQL must use a nonlocal postgresql+asyncpg endpoint",
        )
    )
    redis = urlparse(values.get("REDIS_URL", ""))
    redis_ok = (
        redis.scheme == "rediss"
        and bool(redis.hostname)
        and redis.hostname not in {"localhost", "127.0.0.1", "redis"}
    )
    findings.append(
        Finding(
            "redis_endpoint",
            "READY BUT UNPROVEN" if redis_ok else "BLOCKED",
            "TLS nonlocal Redis endpoint is configured; connectivity remains to be proven"
            if redis_ok
            else "Redis must use a nonlocal rediss endpoint",
        )
    )

    try:
        keys = json.loads(values.get("ACCESS_TOKEN_KEYS", "{}"))
    except json.JSONDecodeError:
        keys = {}
    active_kid = values.get("ACCESS_TOKEN_ACTIVE_KID", "")
    keyring_ok = (
        isinstance(keys, dict)
        and active_kid in keys
        and all(isinstance(value, str) and len(value) >= 32 for value in keys.values())
    )
    distinct_ok = (
        keyring_ok
        and values.get("SECURITY_TOKEN_HMAC_KEY", "") not in set(keys.values())
        and len(values.get("SECURITY_TOKEN_HMAC_KEY", "")) >= 32
    )
    placeholders = any(
        marker in value.lower()
        for marker in PLACEHOLDER_MARKERS
        for value in [
            values.get("PLATFORM_CONTRACT_EXPECTED_FINGERPRINT", ""),
            values.get("SECURITY_TOKEN_HMAC_KEY", ""),
            *[str(item) for item in keys.values()],
        ]
    )
    findings.append(
        Finding(
            "production_key_material",
            "READY" if distinct_ok and not placeholders else "BLOCKED",
            "distinct signing and HMAC key material is structurally valid"
            if distinct_ok and not placeholders
            else "key material is missing, shared, short, or placeholder data",
        )
    )

    protected_dir_text = values.get("PRODUCTION_PROTECTED_SECRET_DIR_HOST", "")
    redis_dir_text = values.get("PRODUCTION_REDIS_SECRET_DIR_HOST", "")
    evidence_dir_text = values.get("PRODUCTION_EVIDENCE_DIR_HOST", "")
    for check, text, writable in (
        ("protected_secret_custody", protected_dir_text, False),
        ("redis_secret_custody", redis_dir_text, False),
        ("evidence_custody", evidence_dir_text, True),
    ):
        findings.append(
            _private_directory(Path(text), check=check, writable=writable)
            if Path(text).is_absolute()
            else Finding(check, "BLOCKED", "custody path must be absolute")
        )
    if protected_dir_text and Path(protected_dir_text).is_absolute():
        findings.extend(
            [
                _private_file(
                    Path(protected_dir_text)
                    / "identity-onboarding-delivery-keyring.json",
                    check="identity_delivery_keyring",
                ),
                _private_file(
                    Path(protected_dir_text) / "payroll-input-encryption-keyring.json",
                    check="protected_input_keyring",
                ),
            ]
        )
    if redis_dir_text and Path(redis_dir_text).is_absolute():
        findings.append(
            _private_file(
                Path(redis_dir_text) / "application-password",
                check="redis_password_file",
            )
        )

    disabled = all(
        values.get(key, "").lower() == "false"
        for key in (
            "COMMUNICATIONS_DELIVERY_ENABLED",
            "COMMUNICATIONS_WEBHOOK_ENABLED",
            "QBO_SANDBOX_ENABLED",
            "QBO_PRODUCTION_ENABLED",
        )
    )
    findings.append(
        Finding(
            "external_mutation_controls",
            "READY" if disabled else "BLOCKED",
            "communications and acquisition controls are disabled"
            if disabled
            else "external communications and acquisition controls must remain disabled",
        )
    )
    return findings


def inspect_platform_manifest(path: Path, *, expected_sha: str) -> list[Finding]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    findings: list[Finding] = []
    findings.append(
        Finding(
            "platform_manifest_contract",
            "READY"
            if payload.get("contract") == "twelve-hats-production-platform/v1"
            else "BLOCKED",
            "platform manifest contract is recognized"
            if payload.get("contract") == "twelve-hats-production-platform/v1"
            else "unrecognized platform manifest contract",
        )
    )
    manifest_sha = payload.get("release_candidate_sha")
    findings.append(
        Finding(
            "platform_release_identity",
            "READY" if manifest_sha == expected_sha else "BLOCKED",
            "platform manifest matches APP_VERSION"
            if manifest_sha == expected_sha
            else "platform manifest release candidate does not match APP_VERSION",
        )
    )
    resources = payload.get("resources", {})
    missing = sorted(REQUIRED_PLATFORM_RESOURCES - set(resources))
    unready = sorted(
        name
        for name in REQUIRED_PLATFORM_RESOURCES & set(resources)
        if resources[name].get("state") != "PROVISIONED_AND_VERIFIED"
    )
    findings.append(
        Finding(
            "platform_resources",
            "READY" if not missing and not unready else "BLOCKED",
            "all closed-traffic resources are provisioned and verified"
            if not missing and not unready
            else f"missing={','.join(missing) or 'none'}; unready={','.join(unready) or 'none'}",
        )
    )
    controls = payload.get("authorities", {})
    required_controls = {"release", "security", "incident", "backup", "restore", "secret_recovery"}
    unresolved = sorted(
        name for name in required_controls if not controls.get(name, {}).get("principal")
    )
    findings.append(
        Finding(
            "named_operational_authorities",
            "READY" if not unresolved else "BLOCKED",
            "all operational authorities are named"
            if not unresolved
            else f"unnamed authorities: {','.join(unresolved)}",
        )
    )
    decisions = payload.get("owner_decisions", {})
    undecided = sorted(
        name for name in ("rpo", "rto", "retention", "region", "geographic_separation", "alert_destination")
        if not decisions.get(name)
    )
    findings.append(
        Finding(
            "owner_operational_decisions",
            "READY" if not undecided else "BLOCKED",
            "required owner operational decisions are recorded"
            if not undecided
            else f"unresolved decisions: {','.join(undecided)}",
        )
    )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed Twelve Hats Production release preflight"
    )
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--platform-manifest", type=Path)
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args()
    findings = inspect(arguments.env_file.resolve(strict=True))
    if arguments.platform_manifest:
        values = load_environment(arguments.env_file.resolve(strict=True))
        findings.extend(
            inspect_platform_manifest(
                arguments.platform_manifest.resolve(strict=True),
                expected_sha=values.get("APP_VERSION", ""),
            )
        )
    else:
        findings.append(
            Finding(
                "platform_manifest",
                "BLOCKED",
                "closed-traffic preflight requires --platform-manifest",
            )
        )
    report = {
        "contract": "twelve-hats-production-release-preflight/v1",
        "safe_to_continue": all(
            item.status in {"READY", "READY BUT UNPROVEN"} for item in findings
        ),
        "findings": [item.__dict__ for item in findings],
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.report:
        arguments.report.write_text(rendered, encoding="utf-8")
        arguments.report.chmod(0o600)
    else:
        print(rendered, end="")
    return 0 if report["safe_to_continue"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
