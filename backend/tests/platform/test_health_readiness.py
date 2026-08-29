from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.platform.health.contracts import ComponentHealth, HealthState
from app.platform.health.service import PlatformHealthService


def _component(name: str, state: HealthState, *, required: bool) -> ComponentHealth:
    return ComponentHealth(
        component=name,
        state=state,
        required=required,
        classification="HARD_REQUIRED" if required else "DEGRADABLE",
        reason="test evidence",
        observed_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_required_component_failure_makes_process_not_ready() -> None:
    service = PlatformHealthService(configuration=Settings(environment="test"), engine=AsyncMock())
    service.database = AsyncMock(return_value=_component("database", HealthState.HEALTHY, required=True))
    service.schema = AsyncMock(return_value=_component("schema", HealthState.NOT_READY, required=True))
    service.redis = AsyncMock(return_value=_component("redis", HealthState.HEALTHY, required=True))

    result = await service.inspect()

    assert result.state is HealthState.NOT_READY


@pytest.mark.asyncio
async def test_optional_dependency_failure_is_truthfully_degraded() -> None:
    service = PlatformHealthService(configuration=Settings(environment="test"), engine=AsyncMock())
    service.database = AsyncMock(return_value=_component("database", HealthState.HEALTHY, required=True))
    service.schema = AsyncMock(return_value=_component("schema", HealthState.HEALTHY, required=True))
    service.redis = AsyncMock(return_value=_component("redis", HealthState.DEGRADED, required=False))

    result = await service.inspect()

    assert result.state is HealthState.DEGRADED


@pytest.mark.asyncio
async def test_health_projection_contains_safe_classifications_only() -> None:
    service = PlatformHealthService(configuration=Settings(environment="test"), engine=AsyncMock())
    service.database = AsyncMock(return_value=_component("database", HealthState.HEALTHY, required=True))
    service.schema = AsyncMock(return_value=_component("schema", HealthState.HEALTHY, required=True))
    service.redis = AsyncMock(return_value=_component("redis", HealthState.HEALTHY, required=True))

    payload = (await service.inspect()).model_dump(mode="json")

    assert "database_url" not in str(payload)
    assert "redis_url" not in str(payload)
    assert {item["component"] for item in payload["components"]} == {
        "database",
        "schema",
        "redis",
    }
