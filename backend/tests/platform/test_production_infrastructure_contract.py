from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from scripts.production_release_preflight import inspect_platform_manifest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _compose() -> dict[str, Any]:
    return yaml.safe_load(
        (REPOSITORY_ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
    )


def test_production_runtime_requires_isolated_external_state() -> None:
    compose = _compose()
    services = compose["services"]
    environment = compose["x-backend-environment"]

    assert "postgres" not in services
    assert "redis" not in services
    assert environment["ENVIRONMENT"] == "production"
    assert "Production PostgreSQL" in environment["DATABASE_URL"]
    assert "Production Redis" in environment["REDIS_URL"]
    assert environment["REDIS_PASSWORD_FILE"].startswith("/run/secrets/")


def test_production_runtime_is_fail_closed_and_nonacquiring() -> None:
    compose = _compose()
    services = compose["services"]
    environment = compose["x-backend-environment"]

    assert environment["QBO_SANDBOX_ENABLED"] == "false"
    assert environment["QBO_PRODUCTION_ENABLED"] == "false"
    assert environment["COMMUNICATIONS_DELIVERY_ENABLED"] == "false"
    assert environment["COMMUNICATIONS_WEBHOOK_ENABLED"] == "false"
    assert "ports" not in services["backend"]
    assert services["frontend"]["ports"] == [
        "127.0.0.1:${PRODUCTION_HTTP_PORT:-8081}:80"
    ]
    assert services["backend"]["depends_on"]["migrate"]["condition"] == (
        "service_completed_successfully"
    )


def test_production_runtime_uses_immutable_images_and_read_only_custody() -> None:
    compose = _compose()
    services = compose["services"]

    for service_name in ("migrate", "backend", "identity-delivery-worker"):
        service = services[service_name]
        assert "immutable backend image digest" in service["image"]
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in service["security_opt"]
        assert all(volume.endswith(":ro") for volume in service["volumes"])

    assert "immutable frontend image digest" in services["frontend"]["image"]


def test_production_runtime_has_bounded_processes_and_no_reload_server() -> None:
    services = _compose()["services"]
    backend = services["backend"]
    frontend = services["frontend"]

    assert "--reload" not in backend["command"]
    assert backend["command"][-1] == "--no-access-log"
    for service in (backend, frontend):
        assert service["init"] is True
        assert service["cpus"]
        assert service["mem_limit"]
        assert service["pids_limit"]
        assert service["stop_grace_period"]
    assert frontend["read_only"] is True
    assert frontend["user"] == "101:101"
    assert "/var/cache/nginx:size=32m,mode=0755,uid=101,gid=101" in frontend[
        "tmpfs"
    ]
    assert "/var/run:size=4m,mode=0755,uid=101,gid=101" in frontend["tmpfs"]


def test_monitoring_contract_covers_launch_critical_dependencies() -> None:
    payload = json.loads(
        (
            REPOSITORY_ROOT
            / "docs/operations/production-monitoring-alert-contract.v1.json"
        ).read_text(encoding="utf-8")
    )
    checks = {entry["check"] for entry in payload["checks"]}

    assert {
        "frontend_https",
        "backend_readiness",
        "postgresql_readiness",
        "redis_readiness",
        "migration",
        "application_errors",
        "authentication_failures",
        "disk_capacity",
        "backup",
        "backup_freshness",
    } <= checks
    assert payload["alert_destination"] == "OWNER_ACTION_REQUIRED"
    assert payload["invariants"] == {
        "secret_values_in_alerts": False,
        "customer_values_in_alerts": False,
        "automatic_database_restore": False,
        "automatic_schema_downgrade": False,
        "automatic_business_mutation": False,
    }


def test_permanent_edge_uses_twelve_hats_platform_domain() -> None:
    environment = (REPOSITORY_ROOT / ".env.production.example").read_text(
        encoding="utf-8"
    )
    caddy = (
        REPOSITORY_ROOT / "docs/deployment/production-caddyfile.example"
    ).read_text(encoding="utf-8")

    assert "PRODUCTION_HOSTNAME=app.twelve-hats.com" in environment
    assert "COMPOSE_PROJECT_NAME=twelve-hats-production" in environment
    assert "/opt/twelve-hats-production/" in environment
    assert 'CORS_ALLOWED_ORIGINS=["https://app.twelve-hats.com"]' in environment
    assert "app.twelve-hats.com {" in caddy
    assert "allcountyhomeservices.com" not in environment
    assert "allcountyhomeservices.com" not in caddy


def test_unprovisioned_platform_manifest_blocks_closed_traffic() -> None:
    findings = inspect_platform_manifest(
        REPOSITORY_ROOT / "docs/deployment/production-platform-manifest.example.json",
        expected_sha="d5148f60ba842f9b4e7c9e83f16d1d3301372491",
    )
    by_check = {finding.check: finding for finding in findings}

    assert by_check["platform_manifest_contract"].status == "READY"
    assert by_check["platform_release_identity"].status == "READY"
    assert by_check["platform_resources"].status == "BLOCKED"
    assert by_check["named_operational_authorities"].status == "BLOCKED"
    assert by_check["owner_operational_decisions"].status == "BLOCKED"
