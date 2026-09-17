from pathlib import Path

import yaml  # type: ignore[import-untyped]

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _compose() -> dict[str, object]:
    return yaml.safe_load(
        (REPOSITORY_ROOT / "docker-compose.preview.yml").read_text(encoding="utf-8")
    )


def test_mission_control_is_one_optional_coherent_release_pair() -> None:
    compose = _compose()
    services = compose["services"]
    api = services["mission-control-api"]
    web = services["mission-control-web"]

    assert api["profiles"] == ["mission-control"]
    assert web["profiles"] == ["mission-control"]
    assert api["build"] == services["backend"]["build"]
    assert web["build"]["dockerfile"] == "Dockerfile.mission-control"
    assert web["depends_on"] == {
        "mission-control-api": {"condition": "service_healthy"}
    }


def test_mission_control_proxy_alias_is_isolated_and_trusted_exactly() -> None:
    compose = _compose()
    services = compose["services"]
    api = services["mission-control-api"]
    web = services["mission-control-web"]

    assert api["environment"]["TRUSTED_PROXY_CIDRS"] == '["172.32.0.0/24"]'
    assert api["networks"]["mission-control"]["aliases"] == ["backend"]
    assert web["networks"] == {"mission-control": None}
    assert "preview" not in web["networks"]
    assert compose["networks"]["mission-control"]["ipam"]["config"] == [
        {"subnet": "172.32.0.0/24"}
    ]


def test_mission_control_has_loopback_only_host_exposure() -> None:
    compose = _compose()
    services = compose["services"]

    assert services["mission-control-api"].get("ports") is None
    assert services["mission-control-web"]["ports"] == [
        "127.0.0.1:${MISSION_CONTROL_HTTP_PORT:-18008}:80"
    ]
