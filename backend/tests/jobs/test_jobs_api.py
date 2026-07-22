from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.database.session import get_database_session
from app.jobs.router import router
from app.platform.permissions.authorization import (
    AuthorizationContext,
    AuthorizedPermission,
)
from app.platform.permissions.codes import JobPermission
from app.platform.permissions.dependencies import get_authorization_context
from tests.jobs.test_jobs_persistence import JobsFixture
from tests.jobs.test_jobs_query import _context_from_fixture

pytest_plugins = ("tests.jobs.test_jobs_persistence",)


@dataclass(frozen=True)
class JobsApiFixture:
    app: FastAPI
    denied_app: FastAPI
    fixture: JobsFixture
    app_for: Callable[[frozenset[str]], FastAPI]


def _context(
    fixture: JobsFixture, *, permission_codes: frozenset[str]
) -> AuthorizationContext:
    base = _context_from_fixture(fixture)
    now = base.user.created_at
    permissions = (
        tuple(
            AuthorizedPermission(
                id=uuid4(),
                code=code,
                name=code,
                description=None,
                resource="job",
                action=code.rsplit("_", 1)[-1].lower(),
                status="active",
                created_at=now,
                updated_at=now,
                retired_at=None,
            )
            for code in sorted(permission_codes)
        )
        if permission_codes
        else ()
    )
    return AuthorizationContext(
        user=base.user,
        company=base.company,
        membership=base.membership,
        authorized_branches=base.authorized_branches,
        active_branch=base.active_branch,
        effective_roles=(),
        effective_permissions=permissions,
        credential_version=1,
        authorization_version=1,
    )


@pytest_asyncio.fixture
async def jobs_api(
    jobs_database: tuple[AsyncEngine, async_sessionmaker[AsyncSession], JobsFixture],
) -> AsyncIterator[JobsApiFixture]:
    _, factory, fixture = jobs_database

    def build(permission_codes: frozenset[str]) -> FastAPI:
        app = FastAPI()
        app.include_router(router)

        async def session_override() -> AsyncIterator[AsyncSession]:
            async with factory() as session:
                yield session

        async def context_override() -> AuthorizationContext:
            return _context(fixture, permission_codes=permission_codes)

        app.dependency_overrides[get_database_session] = session_override
        app.dependency_overrides[get_authorization_context] = context_override
        return app

    yield JobsApiFixture(
        app=build(JobPermission.ALL),
        denied_app=build(frozenset()),
        fixture=fixture,
        app_for=build,
    )


def _payload(fixture: JobsFixture) -> dict[str, object]:
    return {
        "branch_id": str(fixture.branch_id),
        "customer_id": str(fixture.customer_id),
        "service_location_id": str(fixture.location_id),
        "job_type_code": "service_call",
        "priority": "high",
        "customer_reported_problem": "No heat",
        "internal_description": "Inspect equipment.",
    }


async def _request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    json: Mapping[str, object] | None = None,
    params: Mapping[str, str | int] | None = None,
    headers: Mapping[str, str] | None = None,
) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.request(
            method, path, json=json, params=params, headers=headers
        )


@pytest.mark.asyncio
async def test_create_list_detail_and_query_mapping(jobs_api: JobsApiFixture) -> None:
    created = await _request(
        jobs_api.app, "POST", "/api/v1/jobs", json=_payload(jobs_api.fixture)
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "draft" and body["concurrency_version"] == 1
    listed = await _request(
        jobs_api.app,
        "GET",
        "/api/v1/jobs",
        params={
            "status": "draft",
            "priority": "high",
            "search_text": body["job_number"].lower(),
            "page_size": 1,
        },
    )
    assert listed.status_code == 200
    assert listed.json()["total_count"] == 1
    detail = await _request(jobs_api.app, "GET", f"/api/v1/jobs/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["customer"]["id"] == str(jobs_api.fixture.customer_id)


@pytest.mark.asyncio
async def test_execute_lifecycle_endpoints_delegate_to_job_service(
    jobs_api: JobsApiFixture,
) -> None:
    created = (
        await _request(
            jobs_api.app, "POST", "/api/v1/jobs", json=_payload(jobs_api.fixture)
        )
    ).json()
    job_id, version = created["id"], created["concurrency_version"]
    operations: tuple[tuple[str, dict[str, str]], ...] = (
        ("activate", {}),
        ("start", {}),
        ("pause", {"reason_code": "awaiting_material"}),
        ("resume", {}),
        ("complete", {}),
        ("reopen", {"reason_code": "correction_required"}),
    )
    expected = ("ready", "in_progress", "paused", "in_progress", "completed", "ready")
    for (operation, extra), state in zip(operations, expected, strict=True):
        response = await _request(
            jobs_api.app,
            "POST",
            f"/api/v1/jobs/{job_id}/{operation}",
            json={"expected_version": version, **extra},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == state
        version = result["concurrency_version"]


@pytest.mark.asyncio
async def test_cancel_and_reopen_are_exposed(jobs_api: JobsApiFixture) -> None:
    created = (
        await _request(
            jobs_api.app, "POST", "/api/v1/jobs", json=_payload(jobs_api.fixture)
        )
    ).json()
    cancelled = await _request(
        jobs_api.app,
        "POST",
        f"/api/v1/jobs/{created['id']}/cancel",
        json={"expected_version": 1, "reason_code": "customer_cancelled"},
    )
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    reopened = await _request(
        jobs_api.app,
        "POST",
        f"/api/v1/jobs/{created['id']}/reopen",
        json={"expected_version": 2, "reason_code": "customer_callback"},
    )
    assert reopened.status_code == 200 and reopened.json()["status"] == "ready"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/api/v1/jobs/not-a-uuid", None),
        ("/api/v1/jobs", {"page": 0}),
        ("/api/v1/jobs", {"priority": "invalid"}),
        ("/api/v1/jobs", {"created_start_at": "2025-01-01T00:00:00Z"}),
    ],
)
async def test_transport_validation_is_422(
    jobs_api: JobsApiFixture, path: str, params: dict[str, str | int] | None
) -> None:
    response = await _request(jobs_api.app, "GET", path, params=params)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_permission_denial_and_concealment(jobs_api: JobsApiFixture) -> None:
    denied = await _request(jobs_api.denied_app, "GET", "/api/v1/jobs")
    assert denied.status_code == 403
    concealed = await _request(jobs_api.app, "GET", f"/api/v1/jobs/{uuid4()}")
    assert concealed.status_code == 404
    wrong_branch = _payload(jobs_api.fixture)
    wrong_branch["branch_id"] = str(jobs_api.fixture.other_branch_id)
    response = await _request(jobs_api.app, "POST", "/api/v1/jobs", json=wrong_branch)
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/jobs", f"/api/v1/jobs/{uuid4()}"])
@pytest.mark.parametrize(
    ("permission_codes", "expected"),
    [
        (frozenset({JobPermission.READ}), {200, 404}),
        (frozenset({JobPermission.MANAGE}), {403}),
        (frozenset({JobPermission.EXECUTE}), {403}),
        (frozenset(), {403}),
    ],
)
async def test_read_endpoint_permission_matrix(
    jobs_api: JobsApiFixture,
    path: str,
    permission_codes: frozenset[str],
    expected: set[int],
) -> None:
    response = await _request(jobs_api.app_for(permission_codes), "GET", path)
    assert response.status_code in expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v1/jobs", None),
        (f"/api/v1/jobs/{uuid4()}/activate", {"expected_version": 1}),
        (
            f"/api/v1/jobs/{uuid4()}/cancel",
            {"expected_version": 1, "reason_code": "customer_cancelled"},
        ),
        (
            f"/api/v1/jobs/{uuid4()}/reopen",
            {"expected_version": 1, "reason_code": "customer_callback"},
        ),
    ],
)
@pytest.mark.parametrize(
    ("permission_codes", "expected"),
    [
        (frozenset({JobPermission.MANAGE}), {201, 404}),
        (frozenset({JobPermission.READ}), {403}),
        (frozenset({JobPermission.EXECUTE}), {403}),
        (frozenset(), {403}),
    ],
)
async def test_management_endpoint_permission_matrix(
    jobs_api: JobsApiFixture,
    path: str,
    payload: dict[str, object] | None,
    permission_codes: frozenset[str],
    expected: set[int],
) -> None:
    response = await _request(
        jobs_api.app_for(permission_codes),
        "POST",
        path,
        json=payload or _payload(jobs_api.fixture),
    )
    assert response.status_code in expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "extra"),
    [
        ("start", {}),
        ("pause", {"reason_code": "awaiting_material"}),
        ("resume", {}),
        ("complete", {}),
    ],
)
@pytest.mark.parametrize(
    ("permission_codes", "expected"),
    [
        (frozenset({JobPermission.EXECUTE}), 404),
        (frozenset({JobPermission.READ}), 403),
        (frozenset({JobPermission.MANAGE}), 403),
        (frozenset(), 403),
    ],
)
async def test_execution_endpoint_permission_matrix(
    jobs_api: JobsApiFixture,
    action: str,
    extra: dict[str, str],
    permission_codes: frozenset[str],
    expected: int,
) -> None:
    response = await _request(
        jobs_api.app_for(permission_codes),
        "POST",
        f"/api/v1/jobs/{uuid4()}/{action}",
        json={"expected_version": 1, **extra},
    )
    assert response.status_code == expected


def test_openapi_registers_all_authenticated_jobs_operations() -> None:
    app = FastAPI()
    app.include_router(router)
    paths = app.openapi()["paths"]
    assert "/api/v1/jobs" in paths and "/api/v1/jobs/{job_id}" in paths
    for action in (
        "activate",
        "start",
        "pause",
        "resume",
        "complete",
        "cancel",
        "reopen",
    ):
        assert f"/api/v1/jobs/{{job_id}}/{action}" in paths


@pytest.mark.asyncio
async def test_unauthenticated_request_is_401() -> None:
    app = FastAPI()
    app.include_router(router)
    response = await _request(
        app, "GET", "/api/v1/jobs", headers={"X-Company-ID": str(uuid4())}
    )
    assert response.status_code == 401
