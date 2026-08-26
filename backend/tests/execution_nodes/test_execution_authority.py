from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from app.execution_nodes.authority import ExecutionAuthorityRegistry


def test_execution_authority_is_bounded_and_monotonic() -> None:
    registry = ExecutionAuthorityRegistry()
    execution_id, lease_id = uuid4(), uuid4()
    future = datetime.now(timezone.utc) + timedelta(minutes=5)
    registry.record(execution_id, lease_id, future)
    registry.require_valid(execution_id, lease_id)

    with pytest.raises(ValueError, match="backward"):
        registry.record(execution_id, lease_id, future - timedelta(seconds=1))
    registry.record(execution_id, lease_id, future + timedelta(minutes=5))
    registry.require_valid(execution_id, lease_id)


def test_execution_authority_fails_closed_when_missing_or_expired() -> None:
    registry = ExecutionAuthorityRegistry()
    execution_id, lease_id = uuid4(), uuid4()
    with pytest.raises(RuntimeError, match="expired"):
        registry.require_valid(execution_id, lease_id)
    with pytest.raises(ValueError, match="already expired"):
        registry.record(
            execution_id,
            lease_id,
            datetime.now(timezone.utc) - timedelta(seconds=1),
        )
