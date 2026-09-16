from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _compose() -> dict[str, Any]:
    return yaml.safe_load(
        (REPOSITORY_ROOT / "docker-compose.production.yml").read_text(
            encoding="utf-8"
        )
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
