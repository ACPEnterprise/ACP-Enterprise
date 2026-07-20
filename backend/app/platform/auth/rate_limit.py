from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings, settings
from app.platform.auth.errors import (
    RateLimitExceededError,
    RateLimitUnavailableError,
)


class AuthenticationRateLimiter:
    def __init__(self, configuration: Settings = settings) -> None:
        self.configuration = configuration

    async def enforce(
        self,
        *,
        bucket: str,
        identifier_hash: str,
        limit: int,
        window_seconds: int,
    ) -> None:
        client = Redis.from_url(
            self.configuration.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        key = f"auth-rate:{bucket}:{identifier_hash}"
        try:
            async with client.pipeline(transaction=True) as pipeline:
                pipeline.incr(key)
                pipeline.expire(key, window_seconds, nx=True)
                count, _ = await pipeline.execute()
        except RedisError as error:
            raise RateLimitUnavailableError(
                "Authentication rate limiting is unavailable."
            ) from error
        finally:
            await client.aclose()

        if int(count) > limit:
            raise RateLimitExceededError("Authentication request limit exceeded.")
