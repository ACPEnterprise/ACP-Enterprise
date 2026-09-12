import ast
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import app.main  # noqa: F401 -- register the complete ORM graph
import pytest
from app.business_economics.break_even_policy import (
    BreakEvenPolicyKind,
    PolicyApprovalState,
    PolicyApproverRole,
)
from app.business_economics.owner_policy_operations import (
    InMemoryPolicyOperationRepository,
    OwnerPolicyOperationsService,
    PolicyActor,
    verify_policy_operation_event,
)
from app.business_economics.owner_policy_persistence import (
    PolicyPersistenceConflict,
    _from_record,
    _to_record,
)

MIGRATION = Path(
    "backend/alembic/versions/e5g7i9k1m3o5_create_break_even_policy_events.py"
)
NOW = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)


def _event():
    company = uuid4()
    actor = PolicyActor(
        uuid4(),
        company,
        None,
        frozenset({"COMPANY_ECONOMICS_POLICY_DRAFT"}),
        PolicyApproverRole.OWNER,
    )
    service = OwnerPolicyOperationsService(InMemoryPolicyOperationRepository())
    return service.draft(
        actor,
        kind=BreakEvenPolicyKind.CAPACITY_BUFFER,
        value=Decimal("0.25"),
        effective_start=date(2026, 9, 1),
        provenance="owner_record",
        provenance_digest="a" * 64,
        rationale="round trip",
        occurred_at=NOW,
    )


def test_sql_record_round_trip_preserves_immutable_contract() -> None:
    event = _event()
    record = _to_record(event)
    reloaded = _from_record(record)
    assert reloaded == event
    assert reloaded.policy.policy_digest == event.policy.policy_digest
    assert reloaded.event_digest == event.event_digest
    assert reloaded.state is PolicyApprovalState.DRAFT


def test_tampered_persisted_policy_or_event_digest_fails_closed() -> None:
    record = _to_record(_event())
    record.policy_digest = "b" * 64
    with pytest.raises(PolicyPersistenceConflict, match="policy digest"):
        _from_record(record)
    record = _to_record(_event())
    record.event_digest = "c" * 64
    with pytest.raises(ValueError, match="event digest"):
        _from_record(record)


def test_event_identity_mismatch_fails_before_persistence() -> None:
    event = _event()
    object.__setattr__(event, "company_id", uuid4())
    with pytest.raises(ValueError, match="scope or identity"):
        verify_policy_operation_event(event)


def test_migration_is_one_bounded_revision_on_current_parent() -> None:
    tree = ast.parse(MIGRATION.read_text())
    values = {}
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(
            node.targets[0] if isinstance(node, ast.Assign) else node.target, ast.Name
        ):
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if target.id in {"revision", "down_revision", "depends_on"}:
                values[target.id] = ast.literal_eval(node.value)
    assert values == {
        "revision": "e5g7i9k1m3o5",
        "down_revision": "d4f6h8j0l2n4",
        "depends_on": None,
    }


def test_migration_preserves_legacy_table_and_has_concurrency_guards() -> None:
    source = MIGRATION.read_text()
    assert "economics_company_policy_versions" not in source
    assert "uq_eco_be_policy_version_state" in source
    assert "uq_eco_be_policy_event_digest" in source
    assert "scope_id = COALESCE(branch_id, company_id)" in source
    assert "trg_eco_be_policy_event_immutable" in source
    assert "append-only" in source
    assert 'op.drop_table("economics_break_even_policy_events")' in source
