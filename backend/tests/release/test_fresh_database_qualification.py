from __future__ import annotations

import pytest
from scripts.qualify_release_database import (
    require_pristine_database,
    require_utf8_database,
    sync_database_url,
)


def test_async_database_url_is_converted_without_adding_credentials() -> None:
    assert (
        sync_database_url("postgresql+asyncpg://qualification@postgres/db")
        == "postgresql://qualification@postgres/db"
    )


def test_nonempty_or_reused_database_fails_closed() -> None:
    require_pristine_database(())
    with pytest.raises(RuntimeError, match="not pristine"):
        require_pristine_database(("public.alembic_version:r",))


def test_database_encoding_must_be_utf8() -> None:
    require_utf8_database("UTF8")
    with pytest.raises(RuntimeError, match="must use UTF8"):
        require_utf8_database("SQL_ASCII")
