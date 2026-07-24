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
from app.engineering_control.router import router
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EngineeringCommandPermission
from app.platform.permissions.dependencies import get_authorization_context
from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    context_with_permissions,
    seed_service_fixture,
    utc_now,
)


@dataclass(frozen=True)
class EngineeringApiFixture:
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
async def engineering_api() -> AsyncIterator[EngineeringApiFixture]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    fixture = await seed_service_fixture(factory)
    try:
        yield EngineeringApiFixture(factory, fixture)
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


def create_payload(
    *, instruction: str = "Inspect the approved API boundary."
) -> dict[str, object]:
    return {
        "command_type": "owner_instruction",
        "owner_instruction": instruction,
        "repository_key": "acp-enterprise",
        "expected_branch": "customer-management-v1",
        "expected_head": "a" * 40,
        "requested_code_changes": True,
        "expires_at": (utc_now() + timedelta(hours=2)).isoformat(),
        "idempotency_key": f"http-{utc_now().timestamp()}",
    }


@pytest.mark.asyncio
async def test_create_list_filter_page_detail_approve_and_cancel(
    engineering_api: EngineeringApiFixture,
) -> None:
    app = engineering_api.app_for(tuple(EngineeringCommandPermission.ALL))
    payload = create_payload()
    created = await request(app, "POST", "/api/v1/engineering-commands", json=payload)
    assert created.status_code == 201
    command = created.json()
    assert command["execution_state"] == "execution_not_connected"

    replay = await request(app, "POST", "/api/v1/engineering-commands", json=payload)
    assert replay.status_code == 201
    assert replay.json()["id"] == command["id"]
    conflict_payload = {**payload, "owner_instruction": "Inspect a different boundary."}
    conflict = await request(
        app, "POST", "/api/v1/engineering-commands", json=conflict_payload
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"].endswith("idempotency_conflict")

    listed = await request(
        app,
        "GET",
        "/api/v1/engineering-commands",
        params={"approval_state": "awaiting_approval", "page": 1, "page_size": 1},
    )
    assert listed.status_code == 200
    page = listed.json()
    assert page["total_count"] == page["total_pages"] == 1
    assert "owner_instruction" not in page["items"][0]
    beyond = await request(
        app,
        "GET",
        "/api/v1/engineering-commands",
        params={"page": 2, "page_size": 1},
    )
    assert beyond.json()["items"] == []
    assert beyond.json()["total_count"] == 1

    detail = await request(app, "GET", f"/api/v1/engineering-commands/{command['id']}")
    assert detail.status_code == 200
    assert detail.json()["owner_instruction"] == payload["owner_instruction"]

    approval = {
        "expected_version": command["version"],
        "instruction_digest": command["instruction_digest"],
        "request_digest": command["request_digest"],
        "repository_key": command["repository_key"],
        "expected_branch": command["expected_branch"],
        "expected_head": command["expected_head"],
        "requested_code_changes": command["requested_code_changes"],
    }
    mismatch = await request(
        app,
        "POST",
        f"/api/v1/engineering-commands/{command['id']}/approve",
        json={**approval, "request_digest": "b" * 64},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "engineering_command_approval_mismatch"
    mismatch = await request(
        app,
        "POST",
        f"/api/v1/engineering-commands/{command['id']}/approve",
        json={**approval, "repository_key": "other"},
    )
    assert mismatch.status_code == 409

    approved = await request(
        app,
        "POST",
        f"/api/v1/engineering-commands/{command['id']}/approve",
        json=approval,
    )
    assert approved.status_code == 200
    assert approved.json()["approval_state"] == "approved"
    assert approved.json()["execution_state"] == "execution_not_connected"

    stale = await request(
        app,
        "POST",
        f"/api/v1/engineering-commands/{command['id']}/cancel",
        json={"expected_version": 1, "reason_code": "owner_requested"},
    )
    assert stale.status_code == 409
    canceled = await request(
        app,
        "POST",
        f"/api/v1/engineering-commands/{command['id']}/cancel",
        json={"expected_version": 2, "reason_code": "scope_changed"},
    )
    assert canceled.status_code == 200
    assert canceled.json()["approval_state"] == "canceled"
    terminal = await request(
        app,
        "POST",
        f"/api/v1/engineering-commands/{command['id']}/cancel",
        json={"expected_version": 3, "reason_code": "owner_requested"},
    )
    assert terminal.status_code == 409


@pytest.mark.asyncio
async def test_permission_inactive_membership_and_cross_company_concealment(
    engineering_api: EngineeringApiFixture,
) -> None:
    all_app = engineering_api.app_for(tuple(EngineeringCommandPermission.ALL))
    created = (
        await request(
            all_app,
            "POST",
            "/api/v1/engineering-commands",
            json=create_payload(),
        )
    ).json()
    cases = (
        (
            engineering_api.app_for((EngineeringCommandPermission.MANAGE,)),
            "GET",
            "/api/v1/engineering-commands",
            None,
        ),
        (
            engineering_api.app_for((EngineeringCommandPermission.READ,)),
            "POST",
            "/api/v1/engineering-commands",
            create_payload(),
        ),
        (
            engineering_api.app_for((EngineeringCommandPermission.MANAGE,)),
            "POST",
            f"/api/v1/engineering-commands/{created['id']}/approve",
            {
                "expected_version": 1,
                "instruction_digest": created["instruction_digest"],
                "request_digest": created["request_digest"],
                "repository_key": created["repository_key"],
                "expected_branch": created["expected_branch"],
                "expected_head": created["expected_head"],
                "requested_code_changes": True,
            },
        ),
    )
    for app, method, path, body in cases:
        response = await request(app, method, path, json=body)
        assert response.status_code == 403

    inactive = engineering_api.app_for(
        (EngineeringCommandPermission.READ,), membership_status="revoked"
    )
    assert (
        await request(inactive, "GET", "/api/v1/engineering-commands")
    ).status_code == 403
    other = engineering_api.app_for(
        tuple(EngineeringCommandPermission.ALL), other_company=True
    )
    concealed = await request(
        other, "GET", f"/api/v1/engineering-commands/{created['id']}"
    )
    assert concealed.status_code == 404


@pytest.mark.asyncio
async def test_schema_errors_are_safe_and_unknown_fields_are_rejected(
    engineering_api: EngineeringApiFixture,
) -> None:
    app = engineering_api.app_for(tuple(EngineeringCommandPermission.ALL))
    invalid_uuid = await request(app, "GET", "/api/v1/engineering-commands/not-a-uuid")
    assert invalid_uuid.status_code == 422
    invalid = await request(
        app,
        "POST",
        "/api/v1/engineering-commands",
        json={**create_payload(), "company_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert invalid.status_code == 422
    assert "traceback" not in invalid.text.lower()


def test_openapi_documents_owner_review_without_execution() -> None:
    app = FastAPI()
    app.include_router(router)
    schema = app.openapi()
    paths = schema["paths"]
    assert "/api/v1/engineering-commands" in paths
    approve = paths["/api/v1/engineering-commands/{command_id}/approve"]["post"]
    assert "does not start" in approve["description"]
    assert "execution_not_connected" in approve["description"]
    assert not any(path.endswith("/expire") for path in paths)
