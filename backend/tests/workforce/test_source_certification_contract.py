from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from app.workforce.models import WorkforceSourceCertification
from app.workforce.schemas import SourceCertificationDecisionRequest
from app.workforce.source_certification import (
    SourceCertificationConflict,
    SourceCertificationService,
)
from pydantic import ValidationError


def command(decision: str, **values) -> SourceCertificationDecisionRequest:
    return SourceCertificationDecisionRequest(
        decision=decision,
        expected_revision=values.pop("expected_revision", 0),
        reason=values.pop("reason", "Owner reviewed exact source evidence."),
        **values,
    )


def test_decision_contract_is_explicit_and_versioned() -> None:
    assert command("HOLD").expected_revision == 0
    assert command("LEGACY_ONLY").decision == "LEGACY_ONLY"
    with pytest.raises(ValidationError):
        command("AUTO_MATCH")
    with pytest.raises(ValidationError):
        command("CONFIRM", expected_revision=-1)


@pytest.mark.asyncio
async def test_confirm_requires_persisted_source_target() -> None:
    with pytest.raises(SourceCertificationConflict, match="no ACP Employee"):
        await SourceCertificationService._targets(
            AsyncMock(),
            SimpleNamespace(company=SimpleNamespace(id=uuid4())),
            SimpleNamespace(employee_id=None),
            command("CONFIRM"),
        )


@pytest.mark.asyncio
async def test_hold_and_legacy_cannot_smuggle_target() -> None:
    with pytest.raises(SourceCertificationConflict, match="cannot bind"):
        await SourceCertificationService._targets(
            AsyncMock(),
            SimpleNamespace(company=SimpleNamespace(id=uuid4())),
            SimpleNamespace(employee_id=None),
            command("HOLD", employee_id=uuid4()),
        )


@pytest.mark.asyncio
async def test_select_existing_is_tenant_scoped() -> None:
    session = AsyncMock()
    session.scalar.return_value = None
    with pytest.raises(SourceCertificationConflict, match="outside Company"):
        await SourceCertificationService._targets(
            session,
            SimpleNamespace(company=SimpleNamespace(id=uuid4())),
            SimpleNamespace(employee_id=None),
            command("SELECT_EXISTING", employee_id=uuid4()),
        )


def test_database_contract_guards_source_and_target_uniqueness() -> None:
    constraints = {
        item.name for item in WorkforceSourceCertification.__table__.constraints
    }
    indexes = {item.name for item in WorkforceSourceCertification.__table__.indexes}
    assert "uq_workforce_source_certification_identity" in constraints
    assert "fk_workforce_source_certification_employee" in constraints
    assert "fk_workforce_source_certification_branch" in constraints
    assert "uq_workforce_source_certification_active_employee" in indexes
    assert "uq_workforce_source_certification_active_onboarding" in indexes
