from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from app.platform.audit.access_service import AuditAccessService
from app.platform.audit.contracts import AuditQuery
from app.platform.permissions.authorization import AuthorizationContext


class CapturingRepository:
    query: AuditQuery | None = None

    async def list_company_records(self, session: object, *, query: AuditQuery):
        self.query = query
        return ()


@pytest.mark.asyncio
async def test_audit_product_filters_preserve_tenant_and_branch_authority() -> None:
    company_id, branch_id, actor_id, correlation_id = uuid4(), uuid4(), uuid4(), uuid4()
    occurred_before = datetime(2026, 8, 30, tzinfo=timezone.utc)
    context = cast(
        AuthorizationContext,
        SimpleNamespace(
            company=SimpleNamespace(id=company_id),
            membership=SimpleNamespace(has_all_branch_access=False),
            authorized_branch_ids=frozenset({branch_id}),
            can_access_branch=lambda candidate: candidate == branch_id,
        ),
    )
    repository = CapturingRepository()
    service = AuditAccessService(repository=repository)  # type: ignore[arg-type]

    assert (
        await service.list_records(
            cast(object, None),  # type: ignore[arg-type]
            context=context,
            branch_id=branch_id,
            actor_user_id=actor_id,
            resource_type="job",
            action="job.completed",
            outcome="success",
            correlation_id=correlation_id,
            occurred_before=occurred_before,
            before_id=correlation_id,
            limit=25,
        )
        == ()
    )
    assert repository.query == AuditQuery(
        company_id=company_id,
        authorized_branch_ids=frozenset({branch_id}),
        has_all_branch_access=False,
        branch_id=branch_id,
        actor_user_id=actor_id,
        resource_type="job",
        action="job.completed",
        outcome="success",
        correlation_id=correlation_id,
        occurred_before=occurred_before,
        before_id=correlation_id,
        limit=25,
    )
