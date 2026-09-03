from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _compose(path: str) -> dict[str, object]:
    return yaml.safe_load((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))


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
