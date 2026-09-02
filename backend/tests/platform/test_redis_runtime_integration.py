from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from app.core.config import Settings, settings
from app.platform.auth.errors import (
    RateLimitExceededError,
    RateLimitUnavailableError,
)
from app.platform.auth.rate_limit import AuthenticationRateLimiter
from app.platform.health.contracts import HealthState
from app.platform.health.service import PlatformHealthService


def _configuration(redis_url: str) -> Settings:
    return Settings(
        environment="test",
        database_url=settings.database_url,
        redis_url=redis_url,
        redis_required_for_readiness=True,
        access_token_signing_key="synthetic-redis-test-signing-key-0001",
        security_token_hmac_key="synthetic-redis-test-hmac-key-000001",
    )


@pytest.mark.asyncio
async def test_real_redis_round_trip_serialization_ttl_and_cleanup() -> None:
    client = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    key = f"qualification:round-trip:{uuid4()}"
    payload = {"classification": "synthetic", "version": 1}
    try:
        assert await client.ping() is True
        assert await client.set(key, json.dumps(payload, sort_keys=True), ex=1) is True
        stored = await client.get(key)
        assert stored is not None
        assert json.loads(stored) == payload
        ttl = await client.ttl(key)
        assert 0 <= ttl <= 1
        await asyncio.sleep(1.1)
        assert await client.get(key) is None
    finally:
        await client.delete(key)
        await client.aclose()


@pytest.mark.asyncio
async def test_rate_limit_is_atomic_expiring_isolated_and_reconnectable() -> None:
    limiter = AuthenticationRateLimiter(_configuration(settings.redis_url))
    first = f"qualification-{uuid4()}"
    second = f"qualification-{uuid4()}"
    await limiter.enforce(
        bucket="login", identifier_hash=first, limit=2, window_seconds=5
    )
    await limiter.enforce(
        bucket="login", identifier_hash=first, limit=2, window_seconds=5
    )
    with pytest.raises(RateLimitExceededError):
        await limiter.enforce(
            bucket="login", identifier_hash=first, limit=2, window_seconds=5
        )
    await limiter.enforce(
        bucket="login", identifier_hash=second, limit=1, window_seconds=5
    )

    client = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    try:
        assert await client.get(f"auth-rate:login:{first}") == "3"
        assert await client.ttl(f"auth-rate:login:{first}") > 0
        assert await client.get(f"auth-rate:login:{second}") == "1"
    finally:
        await client.delete(
            f"auth-rate:login:{first}", f"auth-rate:login:{second}"
        )
        await client.aclose()

    # Each enforcement owns and closes its client; a later call reconnects cleanly.
    await limiter.enforce(
        bucket="login",
        identifier_hash=f"qualification-{uuid4()}",
        limit=1,
        window_seconds=1,
    )


@pytest.mark.asyncio
async def test_required_redis_fails_closed_then_live_runtime_recovers() -> None:
    unavailable = AuthenticationRateLimiter(
        _configuration("redis://redis-unavailable.invalid:6379/15")
    )
    with pytest.raises(RateLimitUnavailableError):
        await unavailable.enforce(
            bucket="recovery",
            identifier_hash=f"qualification-{uuid4()}",
            limit=1,
            window_seconds=1,
        )

    live_configuration = _configuration(settings.redis_url)
    live = AuthenticationRateLimiter(live_configuration)
    await live.enforce(
        bucket="recovery",
        identifier_hash=f"qualification-{uuid4()}",
        limit=1,
        window_seconds=1,
    )

    readiness = await PlatformHealthService(
        configuration=live_configuration, engine=None  # type: ignore[arg-type]
    ).redis()
    assert readiness.state is HealthState.HEALTHY
    assert readiness.required is True
    assert readiness.safe_facts == {}
