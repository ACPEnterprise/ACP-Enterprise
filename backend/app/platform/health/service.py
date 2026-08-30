from __future__ import annotations

from datetime import UTC, datetime

from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.platform.health.contracts import ComponentHealth, HealthState, SystemReadiness


class PlatformHealthService:
    """Produces safe health evidence without promoting optional capability state."""

    def __init__(self, *, configuration: Settings, engine: AsyncEngine) -> None:
        self.configuration = configuration
        self.engine = engine

    def _component(
        self,
        component: str,
        state: HealthState,
        *,
        required: bool,
        classification: str,
        reason: str,
        facts: dict[str, str | int | bool | None] | None = None,
    ) -> ComponentHealth:
        return ComponentHealth(
            component=component,
            state=state,
            required=required,
            classification=classification,
            reason=reason,
            observed_at=datetime.now(UTC),
            safe_facts=facts or {},
        )

    async def database(self) -> ComponentHealth:
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return self._component(
                "database",
                HealthState.NOT_READY,
                required=True,
                classification="HARD_REQUIRED",
                reason="Database authority is unavailable.",
            )
        return self._component(
            "database",
            HealthState.HEALTHY,
            required=True,
            classification="HARD_REQUIRED",
            reason="Database authority accepted a read probe.",
        )

    async def schema(self) -> ComponentHealth:
        try:
            config = Config(self.configuration.alembic_config_path)
            expected = tuple(ScriptDirectory.from_config(config).get_heads())
            async with self.engine.connect() as connection:
                actual = tuple(
                    row[0]
                    for row in (
                        await connection.execute(
                            text("SELECT version_num FROM alembic_version ORDER BY version_num")
                        )
                    ).all()
                )
        except (CommandError, OSError, SQLAlchemyError, ValueError):
            return self._component(
                "schema",
                HealthState.NOT_READY,
                required=True,
                classification="HARD_REQUIRED",
                reason="Schema authority could not be established.",
            )
        if len(expected) != 1 or actual != expected:
            return self._component(
                "schema",
                HealthState.NOT_READY,
                required=True,
                classification="HARD_REQUIRED",
                reason="Database schema does not match the application migration head.",
                facts={"expected_head_count": len(expected), "current_head_count": len(actual)},
            )
        return self._component(
            "schema",
            HealthState.HEALTHY,
            required=True,
            classification="HARD_REQUIRED",
            reason="Database schema matches the single application migration head.",
            facts={"revision": actual[0]},
        )

    async def redis(self) -> ComponentHealth:
        client = Redis.from_url(
            self.configuration.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        required = self.configuration.redis_required_for_readiness
        try:
            await client.ping()
        except RedisError:
            return self._component(
                "redis",
                HealthState.NOT_READY if required else HealthState.DEGRADED,
                required=required,
                classification="SESSION_COORDINATION",
                reason="Redis coordination is unavailable; durable database authority is unchanged.",
            )
        finally:
            await client.aclose()
        return self._component(
            "redis",
            HealthState.HEALTHY,
            required=required,
            classification="SESSION_COORDINATION",
            reason="Redis coordination accepted a read probe.",
        )

    async def inspect(self) -> SystemReadiness:
        components = [await self.database(), await self.schema(), await self.redis()]
        required_states = {item.state for item in components if item.required}
        all_states = {item.state for item in components}
        if HealthState.NOT_READY in required_states or HealthState.BLOCKED in required_states:
            state = HealthState.NOT_READY
        elif HealthState.DEGRADED in all_states or HealthState.UNKNOWN in all_states:
            state = HealthState.DEGRADED
        else:
            state = HealthState.HEALTHY
        return SystemReadiness(
            state=state,
            application=self.configuration.app_name,
            version=self.configuration.app_version,
            environment=self.configuration.environment,
            observed_at=datetime.now(UTC),
            components=components,
        )
