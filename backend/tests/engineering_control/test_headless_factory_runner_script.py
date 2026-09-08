import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from scripts.headless_factory_runner import admin_access_token, arguments

from scripts import headless_factory_runner


class _Session:
    def __init__(self) -> None:
        self.transaction_active = False
        self.rollback = AsyncMock(side_effect=self._rollback)

    async def _rollback(self) -> None:
        self.transaction_active = False


class _SessionContext:
    def __init__(self, session: _Session) -> None:
        self.session = session

    async def __aenter__(self) -> _Session:
        return self.session

    async def __aexit__(self, *_args: object) -> None:
        if self.session.transaction_active:
            await self.session.rollback()


class _SessionFactory:
    def __init__(self, sessions: list[_Session]) -> None:
        self.sessions = iter(sessions)

    def __call__(self) -> _SessionContext:
        return _SessionContext(next(self.sessions))


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


def test_admin_access_token_environment_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ACP_HEADLESS_ADMIN_ACCESS_TOKEN_FILE", raising=False)
    monkeypatch.setenv("ACP_HEADLESS_ADMIN_ACCESS_TOKEN", "opaque-token")

    assert admin_access_token() == "opaque-token"
    assert "opaque-token" not in os.environ.get("PYTEST_CURRENT_TEST", "")


@pytest.mark.asyncio
async def test_runner_isolates_authorization_worker_and_scheduler_transactions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    security, worker_auth, scheduler = _Session(), _Session(), _Session()
    options = SimpleNamespace(
        company_id=UUID("11111111-1111-1111-1111-111111111111"),
        worker_session_id=UUID("22222222-2222-2222-2222-222222222222"),
        authority_sha="a" * 40,
        delegation_id=UUID("33333333-3333-3333-3333-333333333333"),
    )
    authenticated = object()
    admin = SimpleNamespace(company=SimpleNamespace(id=options.company_id))
    worker_context = SimpleNamespace(company_id=options.company_id)

    async def resolve(session: _Session, **_kwargs: object) -> object:
        assert session is security
        # Reproduce SQLAlchemy's autobegin caused by authorization reads.
        session.transaction_active = True
        return admin

    async def authenticate(session: _Session, **_kwargs: object) -> object:
        assert session is worker_auth
        assert not session.transaction_active
        return SimpleNamespace(context=worker_context)

    run_once = AsyncMock(return_value=("milestone",))
    monkeypatch.setattr(headless_factory_runner, "arguments", lambda: options)
    monkeypatch.setattr(headless_factory_runner, "admin_access_token", lambda: "token")
    monkeypatch.setattr(
        headless_factory_runner,
        "AsyncSessionFactory",
        _SessionFactory([security, worker_auth, scheduler]),
    )
    monkeypatch.setattr(
        headless_factory_runner.access_token_service,
        "decode",
        lambda _token: object(),
    )
    monkeypatch.setattr(
        headless_factory_runner.authentication_service,
        "validate_access_context",
        AsyncMock(return_value=authenticated),
    )
    monkeypatch.setattr(
        headless_factory_runner.authorization_service, "resolve", resolve
    )
    monkeypatch.setattr(
        headless_factory_runner.worker_transport_service,
        "authenticate_http_session",
        authenticate,
    )
    monkeypatch.setattr(
        headless_factory_runner,
        "HeadlessRunner",
        lambda: SimpleNamespace(run_once=run_once),
    )

    assert await headless_factory_runner.run() == 0
    security.rollback.assert_awaited_once()
    run_once.assert_awaited_once()
    assert run_once.await_args.args[0] is scheduler


@pytest.mark.asyncio
async def test_runner_rolls_back_scheduler_transaction_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    security, worker_auth, scheduler = _Session(), _Session(), _Session()
    company_id = UUID("11111111-1111-1111-1111-111111111111")
    options = SimpleNamespace(
        company_id=company_id,
        worker_session_id=UUID("22222222-2222-2222-2222-222222222222"),
        authority_sha="a" * 40,
        delegation_id=UUID("33333333-3333-3333-3333-333333333333"),
    )
    monkeypatch.setattr(headless_factory_runner, "arguments", lambda: options)
    monkeypatch.setattr(headless_factory_runner, "admin_access_token", lambda: "token")
    monkeypatch.setattr(
        headless_factory_runner,
        "AsyncSessionFactory",
        _SessionFactory([security, worker_auth, scheduler]),
    )
    monkeypatch.setattr(
        headless_factory_runner.access_token_service,
        "decode",
        lambda _token: object(),
    )
    monkeypatch.setattr(
        headless_factory_runner.authentication_service,
        "validate_access_context",
        AsyncMock(return_value=object()),
    )
    monkeypatch.setattr(
        headless_factory_runner.authorization_service,
        "resolve",
        AsyncMock(return_value=SimpleNamespace(company=SimpleNamespace(id=company_id))),
    )
    monkeypatch.setattr(
        headless_factory_runner.worker_transport_service,
        "authenticate_http_session",
        AsyncMock(
            return_value=SimpleNamespace(context=SimpleNamespace(company_id=company_id))
        ),
    )

    async def fail(session: _Session, **_kwargs: object) -> None:
        session.transaction_active = True
        raise RuntimeError("command creation failed")

    monkeypatch.setattr(
        headless_factory_runner,
        "HeadlessRunner",
        lambda: SimpleNamespace(run_once=fail),
    )

    with pytest.raises(RuntimeError, match="command creation failed"):
        await headless_factory_runner.run()
    scheduler.rollback.assert_awaited_once()
