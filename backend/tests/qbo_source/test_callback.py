from __future__ import annotations

import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.qbo_source.callback import (
    CALLBACK_PATH,
    ProtectedAuthorizationStateStore,
    exact_callback_uri,
)
from app.qbo_source.intuit import IntuitEnvironment, PendingAuthorization


def test_callback_uri_is_exact_https_and_has_no_wildcard() -> None:
    assert (
        exact_callback_uri("https://sandbox-acquisition.example")
        == "https://sandbox-acquisition.example" + CALLBACK_PATH
    )
    for invalid in (
        "http://localhost:8000",
        "https://*.example.com",
        "https://example.com/other",
        "https://example.com?callback=1",
    ):
        with pytest.raises(ValueError, match="exact HTTPS"):
            exact_callback_uri(invalid)


@pytest.mark.asyncio
async def test_protected_state_is_restricted_and_single_use(tmp_path: Path) -> None:
    root = tmp_path / "oauth-state"
    repository = tmp_path / "repository"
    repository.mkdir()
    store = ProtectedAuthorizationStateStore(root, repository_root=repository)
    pending = PendingAuthorization(
        state="synthetic-state-" + "x" * 32,
        environment=IntuitEnvironment.SANDBOX,
        redirect_uri="https://sandbox-acquisition.example" + CALLBACK_PATH,
        token_reference="secret://synthetic/token",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )

    await store.put(pending)
    stored_paths = list(root.iterdir())

    assert len(stored_paths) == 1
    assert pending.state not in stored_paths[0].name
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(stored_paths[0].stat().st_mode) == 0o600
    assert await store.consume(pending.state) == pending
    assert await store.consume(pending.state) is None
    assert not list(root.iterdir())


def test_state_store_rejects_open_directory(tmp_path: Path) -> None:
    root = tmp_path / "open"
    root.mkdir(mode=0o755)
    os.chmod(root, 0o755)
    with pytest.raises(ValueError, match="permissions are too open"):
        ProtectedAuthorizationStateStore(root, repository_root=tmp_path / "repository")


def test_state_store_rejects_repository_location(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    with pytest.raises(ValueError, match="outside Git"):
        ProtectedAuthorizationStateStore(
            repository / "oauth-state", repository_root=repository
        )
