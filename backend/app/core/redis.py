from pathlib import Path

from redis.asyncio import Redis

from app.core.config import Settings


def redis_client(configuration: Settings) -> Redis:
    password: str | None = None
    if configuration.redis_password_file:
        password = Path(configuration.redis_password_file).read_text(
            encoding="utf-8"
        ).strip()

    return Redis.from_url(
        configuration.redis_url,
        encoding="utf-8",
        decode_responses=True,
        username=configuration.redis_username,
        password=password,
    )
