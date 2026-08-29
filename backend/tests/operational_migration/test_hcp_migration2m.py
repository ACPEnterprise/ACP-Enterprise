from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Self

import pytest

from app.operational_migration import hcp_migration2_command as command
from app.operational_migration.hcp_migration2_command import (
    ProtectedExecutionAuthority,
    run_command,
)
from app.operational_migration.hcp_migration2_runner import SafeEvidenceError


def _payload(tmp_path: Path) -> dict[str, object]:
    package = tmp_path / "package"
    migration = tmp_path / "migration"
    control = tmp_path / "control.csv"
    package.mkdir()
    migration.mkdir()
    control.write_text("safe synthetic control")
    return {
        "expected_repository_sha": "d" * 40,
        "package_root": str(package),
        "control_csv": str(control),
        "migration1a_root": str(migration),
        "master_run_id": "63273602-8619-5c0b-8b49-8537338b04b5",
        "original_plan_id": "8c717798-db5e-5c49-99be-ca3d250536e3",
        "original_plan_digest": "a" * 64,
        "generation1_repair_id": "5e17975d-0461-5187-b0ea-f1cbe7b58df1",
        "generation1_repair_plan_digest": "b" * 64,
        "failed_operational_child_run_id": "a5896cb7-deea-477a-86e5-5d606ecf0582",
        "superseding_plan_id": "a39f3927-0f7f-59a4-8056-97077012832f",
        "superseding_plan_digest": "c" * 64,
        "sequence_contract_version": "hcp-migration-2k1-appointment-sequence/v1",
        "sequence_digest": "d" * 64,
        "checkpoint_digest": "e" * 64,
        "customer_child_run_id": "4b99260f-43e7-4ae5-81c2-d0cc215b323f",
        "original_operational_child_run_id": "4b8f089d-d47c-4757-a583-e8408f7c4ffd",
        "original_financial_child_run_id": "b8315c42-9d24-4f48-a64f-8fdc05176cce",
        "history_child_run_id": "b612df45-341a-44b7-b85d-964c356ffd17",
        "financial_repair_id": "f37c8f8a-e6a9-56d2-a84b-cea11c5f52ca",
        "nonconforming_financial_child_run_id": "ee397b19-61f2-42b6-9bce-d9c68bdef8c1",
        "financial_successor_plan_id": "8d3a78a3-c62d-55f8-8de3-f63286f099ad",
        "financial_successor_plan_digest": "f" * 64,
        "empty_invoice_identity_digest": "1" * 64,
        "invoice_evidence_count": 117,
        "company_id": "3ddf07ce-0f44-4b67-a40f-fb0ec41bb7cd",
        "branch_id": "887f413a-70dc-4ab1-98aa-8e84f4e7efd0",
        "actor_id": "c427ebd1-7583-4c0d-9c54-55a0c1214174",
        "package_digest": "2" * 64,
        "builder_version": "hcp-migration-2g-plan-builder/v1",
        "expected_schema_head": "c6e8a0b2d435",
    }


def _authority_file(tmp_path: Path) -> Path:
    path = tmp_path / "authority.json"
    path.write_text(json.dumps(_payload(tmp_path)))
    path.chmod(0o600)
    return path


def test_protected_authority_loads_without_manual_objects(tmp_path: Path) -> None:
    authority = ProtectedExecutionAuthority.load(_authority_file(tmp_path))
    assert authority.invoice_evidence_count == 117
    assert str(authority.application_authority().successor_plan_id) == (
        "8d3a78a3-c62d-55f8-8de3-f63286f099ad"
    )


def test_protected_authority_rejects_unsafe_permissions(tmp_path: Path) -> None:
    path = _authority_file(tmp_path)
    path.chmod(0o644)
    with pytest.raises(SafeEvidenceError) as captured:
        ProtectedExecutionAuthority.load(path)
    assert captured.value.code == "protected_authority_permissions_unsafe"
    assert "safe synthetic control" not in str(captured.value)


class _Session:
    def __init__(self, status: str) -> None:
        self.status = status

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, _model: object, _identity: object) -> SimpleNamespace:
        return SimpleNamespace(status=self.status)

    async def scalar(self, _statement: object) -> str:
        return "c6e8a0b2d435"


class _Factory:
    def __init__(self, status: str) -> None:
        self.status = status

    def __call__(self) -> _Session:
        return _Session(self.status)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "status", "application_method", "expected"),
    (
        ("qualify", "running", "qualify", "QUALIFIED"),
        ("execute", "running", "execute", "COMPLETED"),
        ("replay", "completed", "execute", "REPLAY_VERIFIED"),
    ),
)
async def test_public_command_routes_only_through_application(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mode: str,
    status: str,
    application_method: str,
    expected: str,
) -> None:
    authority_file = _authority_file(tmp_path)
    monkeypatch.setattr(command, "_repository_sha", lambda: "d" * 40)
    monkeypatch.setattr(command, "_target", lambda: SimpleNamespace())
    monkeypatch.setattr(
        command, "resolve_rehearsal_context", lambda *_args: _async(SimpleNamespace())
    )
    calls: list[str] = []

    class Application:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def qualify_financial_superseding_repair(
            self, *_args: object, **_kwargs: object
        ) -> dict[str, object]:
            calls.append("qualify")
            return {"state": "QUALIFIED"}

        async def execute(
            self, *_args: object, **_kwargs: object
        ) -> dict[str, object]:
            calls.append("execute")
            return {"state": expected}

    monkeypatch.setattr(command, "HcpMigration2Application", Application)
    result = await run_command(
        mode=mode,
        authority_file=authority_file,
        authorize_execution=mode != "qualify",
        factory=_Factory(status),  # type: ignore[arg-type]
    )
    assert result["state"] == expected
    assert calls == [application_method]


async def _async(value: object) -> object:
    return value


@pytest.mark.asyncio
async def test_execute_requires_explicit_authorization(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(command, "_repository_sha", lambda: "d" * 40)
    monkeypatch.setattr(command, "_target", lambda: SimpleNamespace())
    monkeypatch.setattr(
        command, "resolve_rehearsal_context", lambda *_args: _async(SimpleNamespace())
    )
    with pytest.raises(SafeEvidenceError) as captured:
        await run_command(
            mode="execute",
            authority_file=_authority_file(tmp_path),
            authorize_execution=False,
            factory=_Factory("running"),  # type: ignore[arg-type]
        )
    assert captured.value.code == "explicit_execution_authorization_required"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "status", "code"),
    (
        ("execute", "completed", "execution_mode_master_state_mismatch"),
        ("replay", "running", "replay_mode_master_state_mismatch"),
    ),
)
async def test_mode_cannot_cross_master_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mode: str,
    status: str,
    code: str,
) -> None:
    monkeypatch.setattr(command, "_repository_sha", lambda: "d" * 40)
    monkeypatch.setattr(command, "_target", lambda: SimpleNamespace())
    monkeypatch.setattr(
        command, "resolve_rehearsal_context", lambda *_args: _async(SimpleNamespace())
    )
    with pytest.raises(SafeEvidenceError) as captured:
        await run_command(
            mode=mode,
            authority_file=_authority_file(tmp_path),
            authorize_execution=True,
            factory=_Factory(status),  # type: ignore[arg-type]
        )
    assert captured.value.code == code
