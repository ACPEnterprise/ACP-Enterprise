from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from scripts.preview_synthetic_tenant_fixture import execute


class SessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_args):
        return None


@pytest.mark.asyncio
async def test_command_ends_authorization_read_transaction_before_fixture_mutation():
    security = SimpleNamespace()
    application = SimpleNamespace(rollback=AsyncMock())
    sessions = Mock(side_effect=(SessionContext(security), SessionContext(application)))
    context = object()
    authenticated = object()
    result = SimpleNamespace(
        action="created",
        company_id=uuid4(),
        branch_id=uuid4(),
        audit_record_id=uuid4(),
    )
    args = SimpleNamespace(
        authorizing_company_id=str(uuid4()), authorizing_branch_id=str(uuid4())
    )
    with (
        patch("sys.stdin.read", return_value="opaque-token"),
        patch("scripts.preview_synthetic_tenant_fixture.AsyncSessionFactory", sessions),
        patch(
            "scripts.preview_synthetic_tenant_fixture.access_token_service.decode",
            return_value=object(),
        ),
        patch(
            "scripts.preview_synthetic_tenant_fixture.authentication_service.validate_access_context",
            new=AsyncMock(return_value=authenticated),
        ),
        patch(
            "scripts.preview_synthetic_tenant_fixture.authorization_service.resolve",
            new=AsyncMock(return_value=context),
        ),
        patch(
            "scripts.preview_synthetic_tenant_fixture.preview_synthetic_tenant_fixture_service.create_or_reuse",
            new=AsyncMock(return_value=result),
        ) as fixture,
        patch(
            "scripts.preview_synthetic_tenant_fixture.engine",
            new=SimpleNamespace(dispose=AsyncMock()),
        ),
    ):
        payload = await execute(args)
    application.rollback.assert_awaited_once_with()
    fixture.assert_awaited_once()
    assert payload["classification"] == "PREVIEW_SYNTHETIC_TENANT_READY"
