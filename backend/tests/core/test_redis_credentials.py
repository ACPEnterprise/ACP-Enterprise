from pathlib import Path
from secrets import token_urlsafe

from app.core.config import Settings
from app.core.redis import redis_client


def test_redis_client_reads_password_from_file(tmp_path: Path) -> None:
    password = token_urlsafe(32)
    password_file = tmp_path / "application-password"
    password_file.write_text(f"{password}\n", encoding="utf-8")
    configuration = Settings(
        redis_url="redis://redis:6379/0",
        redis_username="acp-application",
        redis_password_file=str(password_file),
    )

    client = redis_client(configuration)

    assert client.connection_pool.connection_kwargs["username"] == "acp-application"
    assert client.connection_pool.connection_kwargs["password"] == password
    assert password not in configuration.model_dump_json()
