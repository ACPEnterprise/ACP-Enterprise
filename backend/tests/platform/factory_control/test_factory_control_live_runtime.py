from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from app.platform.factory_control.live_runtime import LiveFactoryControlConfig


def environment(tmp_path: Path) -> dict[str, str]:
    key = tmp_path / "factory-control.key"
    key.write_text("not-read-by-config-validation", encoding="utf-8")
    key.chmod(0o600)
    return {
        "FACTORY_CONTROL_BASE_URL": "https://beta.example.test",
        "FACTORY_CONTROL_WORKER_ID": str(uuid4()),
        "FACTORY_CONTROL_PRIVATE_KEY_FILE": str(key),
        "FACTORY_CONTROL_PROTECTED_SHA": "a" * 40,
        "FACTORY_CONTROL_BETA_SHA": "b" * 40,
        "FACTORY_CONTROL_LANE_TARGETS": json.dumps(
            [
                {
                    "lane_code": "OM2E",
                    "worker_id": str(uuid4()),
                    "controlling_enterprise": "OM2E",
                    "lifecycle_state": "WAITING_INTEGRATION",
                    "self_refill_health": "WAITING_INTEGRATION",
                    "milestone_code": "PAYROLL.MUTATION.AUTHORITY",
                    "current_assignment": "Issue #449 cumulative integration",
                    "queue_depth": 3,
                    "last_handoff_at": "2026-09-18T20:14:05Z",
                    "evidence": ["PR #450", "PR #470", "PR #471"],
                }
            ]
        ),
    }


def test_live_config_preserves_controller_state_separately_from_node_capacity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for key, value in environment(tmp_path).items():
        monkeypatch.setenv(key, value)

    config = LiveFactoryControlConfig.from_environment()

    assert config.targets[0]["lifecycle_state"] == "WAITING_INTEGRATION"
    assert config.targets[0]["queue_depth"] == 3
    assert config.targets[0]["last_handoff_at"] == "2026-09-18T20:14:05Z"
    assert config.targets[0]["evidence"] == ["PR #450", "PR #470", "PR #471"]


def test_live_config_rejects_capacity_only_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    values = environment(tmp_path)
    target = json.loads(values["FACTORY_CONTROL_LANE_TARGETS"])[0]
    for field in ("lifecycle_state", "self_refill_health", "evidence"):
        target.pop(field)
    values["FACTORY_CONTROL_LANE_TARGETS"] = json.dumps([target])
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    with pytest.raises(ValueError, match="Field required"):
        LiveFactoryControlConfig.from_environment()
