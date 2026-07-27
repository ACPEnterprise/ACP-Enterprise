from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, replace
from datetime import timedelta

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.database.session import get_database_session
from app.engineering_control.mobile.router import router
from app.engineering_control.review.service import EngineeringReviewService
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EngineeringCommandPermission
from app.platform.permissions.dependencies import get_authorization_context
from tests.engineering_control.review.test_engineering_review import completed_command
from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    context_with_permissions,
    seed_service_fixture,
    utc_now,
)


@dataclass(frozen=True)
class MobileApiFixture:
    factory: async_sessionmaker[AsyncSession]
    service_fixture: ServiceFixture

    def app_for(
        self,
        permissions: tuple[str, ...],
        *,
        other_company: bool = False,
        membership_status: str = "active",
    ) -> FastAPI:
        source = (
            self.service_fixture.other_context
            if other_company
            else self.service_fixture.context
        )
        membership = replace(source.membership, status=membership_status)
        context = AuthorizationContext(
            user=source.user,
            company=source.company,
            membership=membership,
            authorized_branches=source.authorized_branches,
            active_branch=source.active_branch,
            effective_roles=(),
            effective_permissions=context_with_permissions(
                source.user, source.company, membership, permissions
            ).effective_permissions,
            credential_version=source.credential_version,
            authorization_version=source.authorization_version,
        )
        app = FastAPI()
        app.include_router(router)

        async def session_override() -> AsyncIterator[AsyncSession]:
            async with self.factory() as session:
                yield session

        async def context_override() -> AuthorizationContext:
            return context

        app.dependency_overrides[get_database_session] = session_override
        app.dependency_overrides[get_authorization_context] = context_override
        return app


@pytest_asyncio.fixture
async def mobile_api() -> AsyncIterator[MobileApiFixture]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    fixture = await seed_service_fixture(factory)
    try:
        yield MobileApiFixture(factory, fixture)
    finally:
        await engine.dispose()


async def request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    json: Mapping[str, object] | None = None,
    params: Mapping[str, str | int] | None = None,
) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.request(method, path, json=json, params=params)


def create_payload(*, suffix: str) -> dict[str, object]:
    return {
        "command_type": "owner_instruction",
        "owner_instruction": "Inspect the approved mobile API boundary.",
        "repository_key": "acp-enterprise",
        "expected_branch": "customer-management-v1",
        "expected_head": "a" * 40,
        "requested_code_changes": True,
        "expires_at": (utc_now() + timedelta(hours=2)).isoformat(),
        "idempotency_key": f"mobile-{suffix}",
    }


async def create_command(
    mobile_api: MobileApiFixture, *, suffix: str
) -> dict[str, object]:
    from app.engineering_control.commands import CreateEngineeringCommand
    from app.engineering_control.service import EngineeringControlService

    async with mobile_api.factory() as session:
        payload = create_payload(suffix=suffix)
        record = await EngineeringControlService().create_command(
            session,
            context=mobile_api.service_fixture.context,
            command=CreateEngineeringCommand(
                command_type=str(payload["command_type"]),
                owner_instruction=str(payload["owner_instruction"]),
                repository_key=str(payload["repository_key"]),
                expected_branch=str(payload["expected_branch"]),
                expected_head=str(payload["expected_head"]),
                requested_code_changes=bool(payload["requested_code_changes"]),
                expires_at=utc_now() + timedelta(hours=2),
                idempotency_key=str(payload["idempotency_key"]),
            ),
        )
    return {
        "id": str(record.id),
        "version": record.version,
        "instruction_digest": record.instruction_digest,
        "request_digest": record.request_digest,
        "repository_key": record.repository_key,
        "expected_branch": record.expected_branch,
        "expected_head": record.expected_head,
        "requested_code_changes": record.requested_code_changes,
    }


@pytest.mark.asyncio
async def test_pending_review_detail_approval_status_and_cancel(
    mobile_api: MobileApiFixture,
) -> None:
    command = await create_command(mobile_api, suffix="workflow")
    app = mobile_api.app_for(tuple(EngineeringCommandPermission.ALL))

    listed = await request(
        app,
        "GET",
        "/api/v1/engineering/mobile/reviews",
        params={"page": 1, "page_size": 10},
    )
    assert listed.status_code == 200
    assert listed.json()["total_count"] == 1
    assert listed.json()["items"][0]["approval_state"] == "awaiting_approval"
    assert "owner_instruction" not in listed.json()["items"][0]

    detail = await request(
        app, "GET", f"/api/v1/engineering/mobile/reviews/{command['id']}"
    )
    assert detail.status_code == 200
    assert detail.json()["can_approve"] is True
    assert detail.json()["execution_connected"] is False

    approval = {
        **{
            key: value for key, value in command.items() if key not in {"id", "version"}
        },
        "expected_version": command["version"],
    }
    mismatch = await request(
        app,
        "POST",
        f"/api/v1/engineering/mobile/reviews/{command['id']}/approve",
        json={**approval, "request_digest": "b" * 64},
    )
    assert mismatch.status_code == 409

    approved = await request(
        app,
        "POST",
        f"/api/v1/engineering/mobile/reviews/{command['id']}/approve",
        json=approval,
    )
    assert approved.status_code == 200
    assert approved.json()["approval_state"] == "approved"
    assert approved.json()["execution_state"] == "execution_not_connected"
    assert approved.json()["execution_connected"] is False

    status_response = await request(
        app,
        "GET",
        f"/api/v1/engineering/mobile/commands/{command['id']}/status",
    )
    assert status_response.status_code == 200
    assert status_response.json()["can_approve"] is False

    canceled = await request(
        app,
        "POST",
        f"/api/v1/engineering/mobile/reviews/{command['id']}/cancel",
        json={"expected_version": 2, "reason_code": "owner_requested"},
    )
    assert canceled.status_code == 200
    assert canceled.json()["approval_state"] == "canceled"
    assert canceled.json()["can_cancel"] is False


@pytest.mark.asyncio
async def test_permissions_inactive_membership_and_company_concealment(
    mobile_api: MobileApiFixture,
) -> None:
    command = await create_command(mobile_api, suffix="auth")
    no_read = mobile_api.app_for((EngineeringCommandPermission.MANAGE,))
    denied = await request(no_read, "GET", "/api/v1/engineering/mobile/reviews")
    assert denied.status_code == 403

    inactive = mobile_api.app_for(
        tuple(EngineeringCommandPermission.ALL), membership_status="suspended"
    )
    denied = await request(inactive, "GET", "/api/v1/engineering/mobile/reviews")
    assert denied.status_code == 403

    other_company = mobile_api.app_for(
        tuple(EngineeringCommandPermission.ALL), other_company=True
    )
    concealed = await request(
        other_company,
        "GET",
        f"/api/v1/engineering/mobile/reviews/{command['id']}",
    )
    assert concealed.status_code == 404


@pytest.mark.asyncio
async def test_owner_review_projection_uses_immutable_review_packages(
    mobile_api: MobileApiFixture,
) -> None:
    command = await completed_command(mobile_api.service_fixture)
    owner = mobile_api.app_for(tuple(EngineeringCommandPermission.ALL))
    async with mobile_api.factory() as session:
        package = await EngineeringReviewService().prepare(
            session,
            context=context_with_permissions(
                mobile_api.service_fixture.context.user,
                mobile_api.service_fixture.context.company,
                mobile_api.service_fixture.context.membership,
                tuple(EngineeringCommandPermission.ALL),
            ),
            command_id=command.id,
        )

    listed = await request(
        owner,
        "GET",
        "/api/v1/engineering/mobile/owner-reviews",
        params={"page": 1, "page_size": 10},
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["total_count"] == 1
    assert body["connectivity"]["state"] == "disconnected"
    assert body["connectivity"]["session_id"] is None
    item = body["items"][0]
    assert item["id"] == str(package.review.id)
    assert item["command_id"] == str(command.id)
    assert item["execution_id"] == str(package.review.execution_id)
    assert item["provider_identifier"] == package.review.provider_identifier
    assert item["result_disposition"] == package.result_disposition
    assert item["validation_summary"] == package.validation_summary
    assert item["file_boundary"] == package.validation_summary.get("file_boundary", [])
    assert item["state"] == "pending"
    assert item["decision"] is None
    assert "review_digest" not in item
    assert "credential" not in str(body).lower()

    other_company = mobile_api.app_for(
        tuple(EngineeringCommandPermission.ALL), other_company=True
    )
    concealed = await request(
        other_company,
        "GET",
        "/api/v1/engineering/mobile/owner-reviews",
    )
    assert concealed.status_code == 200
    assert concealed.json()["items"] == []


def test_mobile_openapi_exposes_no_rejection_or_execution_operation() -> None:
    app = FastAPI()
    app.include_router(router)
    paths = app.openapi()["paths"]
    assert "/api/v1/engineering/mobile/reviews" in paths
    assert "/api/v1/engineering/mobile/reviews/{command_id}/approve" in paths
    assert all("reject" not in path and "execute" not in path for path in paths)
