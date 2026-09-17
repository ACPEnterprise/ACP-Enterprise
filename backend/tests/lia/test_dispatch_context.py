from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.dispatch.errors import DispatchNotFound
from app.dispatch.service import dispatch_service
from app.lia.owner_answers import compose_owner_answer
from app.lia.retrieval import GovernedRetrievalService
from app.platform.permissions.codes import DispatchPermission


def _context():
    branch = SimpleNamespace(id=uuid4())
    return SimpleNamespace(
        company=SimpleNamespace(id=uuid4()),
        active_branch=branch,
        authorized_branch_ids=frozenset({branch.id}),
        authorization_version=4,
        has_permission=lambda permission: permission == DispatchPermission.READ,
    )


@pytest.mark.asyncio
async def test_appointment_dispatch_context_names_authoritative_assignment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    appointment_id = uuid4()
    assignment = SimpleNamespace(
        id=uuid4(),
        appointment_number="APT-000267",
        branch_id=uuid4(),
        primary_employee_id=uuid4(),
        primary_employee_name="Jason Technician",
        status="assigned",
        arrival_state="not_started",
        effective_at=datetime.now(timezone.utc),
        version=3,
    )
    monkeypatch.setattr(dispatch_service, "detail", AsyncMock(return_value=assignment))

    session = AsyncMock()
    session.scalar.return_value = appointment_id
    evidence = await GovernedRetrievalService().retrieve(
        session,
        context=_context(),
        domains={"dispatch"},
        entity_id=appointment_id,
        entity_domain="scheduling",
    )

    assert len(evidence) == 1
    assert evidence[0].authority == "DISPATCH.LIA_CONTEXT.v1"
    assert "assigned to Jason Technician" in (evidence[0].state or "")
    answer = compose_owner_answer("Who is assigned?", evidence)
    assert "Jason Technician" in answer.text
    assert "did not assign or release" in answer.text


@pytest.mark.asyncio
async def test_missing_assignment_is_truthful_unassigned_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dispatch_service,
        "detail",
        AsyncMock(side_effect=DispatchNotFound("Assignment was not found.")),
    )
    appointment_id = uuid4()
    session = AsyncMock()
    session.scalar.return_value = appointment_id
    evidence = await GovernedRetrievalService().retrieve(
        session,
        context=_context(),
        domains={"dispatch"},
        entity_id=appointment_id,
        entity_domain="scheduling",
    )
    assert evidence[0].count == 0
    assert evidence[0].state == (
        "UNASSIGNED|This Appointment has no authoritative Dispatch assignment."
    )


@pytest.mark.asyncio
async def test_foreign_or_unknown_appointment_has_no_dispatch_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detail = AsyncMock()
    monkeypatch.setattr(dispatch_service, "detail", detail)
    session = AsyncMock()
    session.scalar.return_value = None
    evidence = await GovernedRetrievalService().retrieve(
        session,
        context=_context(),
        domains={"dispatch"},
        entity_id=uuid4(),
        entity_domain="scheduling",
    )
    assert evidence == ()
    detail.assert_not_awaited()
