from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from app.engineering_control.scheduler import delegation
from app.engineering_control.scheduler.delegation import (
    REQUIRED,
    ActivateDelegation,
    SchedulerDelegationDenied,
    SchedulerDelegationService,
)

NOW = datetime(2026, 9, 4, tzinfo=timezone.utc)


class Session:
    def __init__(self, scalar: object | None = None) -> None:
        self.scalar_result = scalar
        self.added: list[object] = []
        self.commits = 0

    async def scalar(self, _statement: object) -> object | None:
        return self.scalar_result

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        row = cast(Any, self.added[0])
        if getattr(row, "id", None) is None:
            row.id = uuid4()

    async def commit(self) -> None:
        self.commits += 1


def context(**changes: object) -> SimpleNamespace:
    values = {
        "company": SimpleNamespace(id=uuid4()),
        "user": SimpleNamespace(id=uuid4()),
        "credential_version": 3,
        "authorization_version": 7,
        "permission_codes": REQUIRED,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def queue(*, fingerprint: str = "a" * 64) -> SimpleNamespace:
    return SimpleNamespace(
        queue_id="approved-queue",
        fingerprint=fingerprint,
        items=(
            SimpleNamespace(
                milestone_id="SAFE.ONE",
                execution_mode="repository_only",
                hard_boundary_operations=(),
            ),
            SimpleNamespace(
                milestone_id="BOUNDARY",
                execution_mode="repository_only",
                hard_boundary_operations=("production",),
            ),
            SimpleNamespace(
                milestone_id="EXTERNAL",
                execution_mode="external",
                hard_boundary_operations=(),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_activation_persists_only_bounded_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(delegation, "load_approved_factory_queue", queue)
    session = Session()
    actor = context()
    row = await SchedulerDelegationService().activate(
        session,  # type: ignore[arg-type]
        context=actor,  # type: ignore[arg-type]
        request=ActivateDelegation("b" * 40, NOW + timedelta(hours=72)),
        now=NOW,
    )
    assert row.scope["milestone_ids"] == ("SAFE.ONE",)
    assert row.scope["non_production"] is True
    assert "production" in cast(tuple[str, ...], row.scope["forbidden_operations"])
    assert row.credential_version == actor.credential_version
    assert row.authorization_version == actor.authorization_version
    assert session.commits == 1
    assert len(session.added) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("hours", [0, 73])
async def test_activation_rejects_invalid_expiry(
    monkeypatch: pytest.MonkeyPatch, hours: int
) -> None:
    monkeypatch.setattr(delegation, "load_approved_factory_queue", queue)
    with pytest.raises(SchedulerDelegationDenied, match="expiry"):
        await SchedulerDelegationService().activate(
            Session(),  # type: ignore[arg-type]
            context=context(),  # type: ignore[arg-type]
            request=ActivateDelegation("b" * 40, NOW + timedelta(hours=hours)),
            now=NOW,
        )


@pytest.mark.asyncio
async def test_activation_requires_complete_permission_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(delegation, "load_approved_factory_queue", queue)
    with pytest.raises(SchedulerDelegationDenied, match="permissions"):
        await SchedulerDelegationService().activate(
            Session(),  # type: ignore[arg-type]
            context=context(permission_codes=frozenset()),  # type: ignore[arg-type]
            request=ActivateDelegation("b" * 40, NOW + timedelta(hours=1)),
            now=NOW,
        )


@pytest.mark.asyncio
async def test_live_delegation_rejects_expiry_queue_drift_and_auth_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = context()
    row = SimpleNamespace(
        state="active",
        expires_at=NOW + timedelta(hours=1),
        queue_id="approved-queue",
        queue_fingerprint="a" * 64,
        company_id=actor.company.id,
        activated_by_user_id=actor.user.id,
        credential_version=actor.credential_version,
        authorization_version=actor.authorization_version,
    )
    service = SchedulerDelegationService()
    monkeypatch.setattr(delegation, "load_approved_factory_queue", queue)
    assert (
        await service.require_live(
            Session(row),  # type: ignore[arg-type]
            delegation_id=uuid4(),
            context=actor,  # type: ignore[arg-type]
            now=NOW,
        )
        is row
    )
    for changed_row, changed_context, changed_queue, expected in (
        (
            SimpleNamespace(**{**vars(row), "expires_at": NOW}),
            actor,
            queue(),
            "expired",
        ),
        (row, actor, queue(fingerprint="c" * 64), "identity changed"),
        (
            row,
            context(
                company=actor.company,
                user=actor.user,
                credential_version=actor.credential_version + 1,
            ),
            queue(),
            "no longer authorized",
        ),
    ):
        monkeypatch.setattr(
            delegation,
            "load_approved_factory_queue",
            lambda selected=changed_queue: selected,
        )
        with pytest.raises(SchedulerDelegationDenied, match=expected):
            await service.require_live(
                Session(changed_row),  # type: ignore[arg-type]
                delegation_id=uuid4(),
                context=changed_context,  # type: ignore[arg-type]
                now=NOW,
            )
