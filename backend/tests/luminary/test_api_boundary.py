from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import ForeignKeyConstraint

from app.business_economics.workspace import EconomicsWorkspaceService
from app.luminary.models import LuminaryBriefingRecord, LuminaryFindingRecord
from app.luminary.router import _luminary_http_error, require_luminary_analyst
from app.luminary.service import LuminaryNotFoundError, LuminaryService
from app.platform.reliability.correlation import request_correlation_id


@pytest.mark.parametrize(
    ("error", "status_code", "code", "recovery"),
    [
        (
            LuminaryNotFoundError("protected-source-canary"),
            404,
            "not_found",
            "TERMINAL_FAILURE",
        ),
        (
            ValueError("protected-validation-canary"),
            422,
            "validation",
            "USER_CORRECTION_REQUIRED",
        ),
        (
            RuntimeError("protected-internal-canary"),
            500,
            "internal_failure",
            "TEMPORARILY_UNAVAILABLE",
        ),
    ],
)
def test_luminary_failures_are_classified_correlated_and_non_reflective(
    error: Exception, status_code: int, code: str, recovery: str
) -> None:
    correlation_id = uuid4()
    token = request_correlation_id.set(correlation_id)
    try:
        response = _luminary_http_error(error)
    finally:
        request_correlation_id.reset(token)

    assert response.status_code == status_code
    assert response.detail["code"] == code
    assert response.detail["recovery"] == recovery
    assert response.detail["correlation_id"] == str(correlation_id)
    assert "canary" not in str(response.detail)


def test_luminary_models_bind_branch_and_successor_to_company() -> None:
    finding_constraints = {
        constraint.name
        for constraint in LuminaryFindingRecord.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    briefing_constraints = {
        constraint.name
        for constraint in LuminaryBriefingRecord.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    assert {
        "fk_luminary_finding_company_branch",
        "fk_luminary_finding_company_supersedes",
    } <= finding_constraints
    assert {
        "fk_luminary_briefing_company_branch",
        "fk_luminary_briefing_company_supersedes",
    } <= briefing_constraints


@pytest.mark.asyncio
async def test_briefing_projection_fails_closed_for_missing_scoped_finding() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    session.scalars.return_value = result
    record = SimpleNamespace(
        company_id=uuid4(),
        branch_id=uuid4(),
        finding_ids=[str(uuid4())],
        finding_digests=["a" * 64],
    )

    with pytest.raises(RuntimeError, match="authority is incomplete"):
        await LuminaryService()._projection(session, record)


@pytest.mark.asyncio
async def test_analyze_permission_does_not_imply_luminary_read() -> None:
    context = SimpleNamespace(
        has_permission=lambda code: code == "COMPANY_LUMINARY_ANALYZE",
        user=SimpleNamespace(id=uuid4()),
        company=SimpleNamespace(id=uuid4()),
        active_branch=SimpleNamespace(id=uuid4()),
    )

    with pytest.raises(HTTPException) as denied:
        await require_luminary_analyst(context)

    assert denied.value.status_code == 403
    assert denied.value.detail == "Permission denied."

    authorized = SimpleNamespace(
        **{
            **context.__dict__,
            "has_permission": lambda code: (
                code in {"COMPANY_LUMINARY_READ", "COMPANY_LUMINARY_ANALYZE"}
            ),
        }
    )
    assert await require_luminary_analyst(authorized) is authorized


@pytest.mark.asyncio
async def test_owner_economics_projection_has_no_persistence_or_event_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id, branch_id = uuid4(), uuid4()
    context = SimpleNamespace(
        company=SimpleNamespace(id=company_id),
        active_branch=SimpleNamespace(id=branch_id),
    )
    workspace = {
        "period": {"start": "2026-08-01", "end": "2026-08-31"},
        "quality_state": "unavailable",
        "totals": None,
        "jobs": [],
        "branches": [],
        "customers": [],
        "service_categories": [],
        "fully_allocated_available": False,
        "readiness": {},
    }
    overview = AsyncMock(return_value=workspace)
    monkeypatch.setattr(EconomicsWorkspaceService, "overview", overview)
    session = AsyncMock()

    result = await LuminaryService().owner_economics_readonly(
        session,
        context=context,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
    )

    assert result["mutation_authority"] == "none"
    overview.assert_awaited_once()
    session.execute.assert_not_awaited()
    session.flush.assert_not_awaited()
    session.commit.assert_not_awaited()
