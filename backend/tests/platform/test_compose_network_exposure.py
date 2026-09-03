from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _compose(path: str) -> dict[str, object]:
    return yaml.safe_load((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))


def test_development_redis_port_is_loopback_only() -> None:
    compose = _compose("docker-compose.yml")
    redis = compose["services"]["redis"]

    assert redis["ports"] == ["127.0.0.1:6379:6379"]


def test_preview_redis_does_not_publish_a_host_port() -> None:
    compose = _compose("docker-compose.preview.yml")
    redis = compose["services"]["redis"]

    assert "ports" not in redis
