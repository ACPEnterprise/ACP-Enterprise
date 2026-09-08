import os
from pathlib import Path

import pytest

from scripts.headless_factory_runner import admin_access_token, arguments


def test_runner_cli_requires_delegation_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "headless_factory_runner",
            "--company-id",
            "11111111-1111-1111-1111-111111111111",
            "--worker-session-id",
            "22222222-2222-2222-2222-222222222222",
            "--authority-sha",
            "a" * 40,
        ],
    )
    with pytest.raises(SystemExit):
        arguments()


def test_admin_access_token_reads_only_mode_0600_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secret = tmp_path / "scheduler.token"
    secret.write_text("opaque-token\n", encoding="utf-8")
    secret.chmod(0o600)
    monkeypatch.setenv("ACP_HEADLESS_ADMIN_ACCESS_TOKEN_FILE", str(secret))
    monkeypatch.delenv("ACP_HEADLESS_ADMIN_ACCESS_TOKEN", raising=False)

    assert admin_access_token() == "opaque-token"


def test_admin_access_token_rejects_group_readable_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secret = tmp_path / "scheduler.token"
    secret.write_text("opaque-token\n", encoding="utf-8")
    secret.chmod(0o640)
    monkeypatch.setenv("ACP_HEADLESS_ADMIN_ACCESS_TOKEN_FILE", str(secret))

    with pytest.raises(SystemExit, match="mode-0600"):
        admin_access_token()


def test_admin_access_token_environment_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ACP_HEADLESS_ADMIN_ACCESS_TOKEN_FILE", raising=False)
    monkeypatch.setenv("ACP_HEADLESS_ADMIN_ACCESS_TOKEN", "opaque-token")

    assert admin_access_token() == "opaque-token"
    assert "opaque-token" not in os.environ.get("PYTEST_CURRENT_TEST", "")
