from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from app.platform.onboarding.preview_fixture import (
    FIXTURE_KEY,
    PreviewIdentityFixtureCommand,
    PreviewIdentityFixtureReset,
    PreviewIdentityFixtureService,
)
from app.platform.onboarding.service import OnboardingConflictError


class Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class Session:
    def begin(self):
        return Transaction()


@pytest.mark.asyncio
async def test_fixture_identity_binds_to_onboarding_and_is_idempotency_keyed():
    onboarding = SimpleNamespace(initiate=AsyncMock(return_value=SimpleNamespace(id=uuid4())))
    service = PreviewIdentityFixtureService(
        configuration=SimpleNamespace(environment="preview"), onboarding=onboarding
    )
    command = PreviewIdentityFixtureCommand(
        FIXTURE_KEY, True, uuid4(), "tech@fixture.invalid", (uuid4(),)
    )
    result = await service.provision_identity(Session(), context=object(), command=command)
    assert result.id
    submitted = onboarding.initiate.await_args.kwargs["command"]
    assert submitted.request_key == FIXTURE_KEY
    assert submitted.login_email == "tech@fixture.invalid"
    assert submitted.display_name == "Synthetic Beta Technician"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "environment,authorized,login",
    [
        ("production", True, "tech@fixture.invalid"),
        ("preview", False, "tech@fixture.invalid"),
        ("preview", True, "tech@example.com"),
    ],
)
async def test_fixture_identity_fails_closed(environment, authorized, login):
    onboarding = SimpleNamespace(initiate=AsyncMock())
    service = PreviewIdentityFixtureService(
        configuration=SimpleNamespace(environment=environment), onboarding=onboarding
    )
    with pytest.raises(OnboardingConflictError):
        await service.provision_identity(
            Session(),
            context=object(),
            command=PreviewIdentityFixtureCommand(
                FIXTURE_KEY, authorized, uuid4(), login, (uuid4(),)
            ),
        )
    onboarding.initiate.assert_not_awaited()


@pytest.mark.asyncio
async def test_reset_revokes_invitation_sessions_then_membership():
    membership_id = uuid4()
    user_id = uuid4()
    record = SimpleNamespace(
        id=uuid4(),
        request_key=FIXTURE_KEY,
        status="invited",
        membership_id=membership_id,
        user_id=user_id,
    )
    revoked = SimpleNamespace(**{**record.__dict__, "status": "revoked"})
    onboarding = SimpleNamespace(
        get=AsyncMock(return_value=record), revoke=AsyncMock(return_value=revoked)
    )
    company = SimpleNamespace(set_membership_status=AsyncMock())
    service = PreviewIdentityFixtureService(
        configuration=SimpleNamespace(environment="preview"),
        onboarding=onboarding,
        company_administration=company,
    )
    session = Session()
    context = object()
    with patch(
        "app.platform.onboarding.preview_fixture.AuthenticationService.revoke_user_sessions",
        new=AsyncMock(),
    ) as sessions:
        result = await service.reset_identity(
            session,
            context=context,
            command=PreviewIdentityFixtureReset(FIXTURE_KEY, True, record.id),
        )
    assert result.status == "revoked"
    onboarding.revoke.assert_awaited_once()
    sessions.assert_awaited_once()
    assert sessions.await_args.kwargs["user_id"] == user_id
    company.set_membership_status.assert_awaited_once_with(
        session,
        context=context,
        membership_id=membership_id,
        status="revoked",
    )
