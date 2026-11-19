import inspect
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.platform.factory_control.authority import (
    get_factory_controller_identity,
    require_platform_factory_reader,
    worker_transport_service,
)
from app.platform.factory_control.router import router
from app.platform.launch_controls import LAUNCH_ROLE_MATRIX
from app.platform.permissions.catalog import permission_catalog
from app.platform.permissions.codes import LaunchPlatformPermission
from app.worker_control.transport.errors import TransportSessionError
from fastapi import FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials


def test_factory_control_permissions_are_not_granted_to_tenant_roles():
    factory_permissions = {
        LaunchPlatformPermission.FACTORY_CONTROL_READ,
        LaunchPlatformPermission.FACTORY_CONTROL_INGEST,
        LaunchPlatformPermission.FACTORY_CONTROL_SNAPSHOT,
    }
    assert all(
        not (factory_permissions & definition.permission_codes)
        for definition in LAUNCH_ROLE_MATRIX
    )


def test_human_read_and_controller_mutation_dependencies_are_split():
    by_path_method = {
        (route.path, method): route
        for route in router.routes
        for method in route.methods
    }
    for path in (
        "/api/v1/platform/factory-control/overview",
        "/api/v1/platform/factory-control/lanes/{lane_code}",
    ):
        route = by_path_method[(path, "GET")]
        assert any(
            dependency.call is require_platform_factory_reader
            for dependency in route.dependant.dependencies
        )
    for path in (
        "/api/v1/platform/factory-control/internal/events",
        "/api/v1/platform/factory-control/internal/sync",
        "/api/v1/platform/factory-control/internal/live-sync",
        "/api/v1/platform/factory-control/internal/snapshots",
    ):
        route = by_path_method[(path, "POST")]
        calls = [dependency.call for dependency in route.dependant.dependencies]
        assert require_platform_factory_reader not in calls
        assert any(
            inspect.iscoroutinefunction(call) and call.__name__ == "dependency"
            for call in calls
        )


def test_factory_control_openapi_declares_exact_bearer_boundaries():
    app = FastAPI()
    app.include_router(router)
    schema = app.openapi()
    expected_security = {
        ("GET", "/api/v1/platform/factory-control/overview"): [{"HTTPBearer": []}],
        ("GET", "/api/v1/platform/factory-control/lanes/{lane_code}"): [
            {"HTTPBearer": []}
        ],
        ("POST", "/api/v1/platform/factory-control/internal/events"): [
            {"FactoryControllerBearer": []}
        ],
        ("POST", "/api/v1/platform/factory-control/internal/sync"): [
            {"FactoryControllerBearer": []}
        ],
        ("POST", "/api/v1/platform/factory-control/internal/live-sync"): [
            {"FactoryControllerBearer": []}
        ],
        ("POST", "/api/v1/platform/factory-control/internal/snapshots"): [
            {"FactoryControllerBearer": []}
        ],
    }
    for (method, path), security in expected_security.items():
        assert schema["paths"][path][method.lower()]["security"] == security
    assert schema["components"]["securitySchemes"]["FactoryControllerBearer"] == {
        "type": "http",
        "description": "Challenge-established Factory Controller session identifier.",
        "scheme": "bearer",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "credentials",
    [
        None,
        HTTPAuthorizationCredentials(scheme="Basic", credentials="opaque"),
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-session"),
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="human.access.token"),
    ],
)
async def test_factory_controller_rejects_missing_malformed_and_wrong_principal_bearers(
    credentials: HTTPAuthorizationCredentials | None,
):
    with pytest.raises(HTTPException) as rejected:
        await get_factory_controller_identity(object(), credentials)  # type: ignore[arg-type]
    assert rejected.value.status_code == 401
    assert rejected.value.headers == {"WWW-Authenticate": "Bearer"}


@pytest.mark.asyncio
async def test_factory_controller_rejects_expired_worker_session(monkeypatch):
    async def reject_expired_session(database, *, session_id):
        del database, session_id
        raise TransportSessionError("expired")

    monkeypatch.setattr(
        worker_transport_service,
        "authenticate_http_session",
        reject_expired_session,
    )
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=str(uuid4())
    )
    with pytest.raises(HTTPException) as rejected:
        await get_factory_controller_identity(object(), credentials)  # type: ignore[arg-type]
    assert rejected.value.status_code == 401
    assert rejected.value.detail == "Factory controller authentication required."


@pytest.mark.asyncio
async def test_factory_controller_accepts_challenge_established_session_bearer(
    monkeypatch,
):
    session_id = uuid4()
    expected_context = object()

    async def authenticate_session(database, *, session_id):
        del database
        return SimpleNamespace(context=expected_context, session_id=session_id)

    monkeypatch.setattr(
        worker_transport_service,
        "authenticate_http_session",
        authenticate_session,
    )
    identity = await get_factory_controller_identity(
        object(),  # type: ignore[arg-type]
        HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=str(session_id)
        ),
    )
    assert identity.session_id == session_id
    assert identity.context is expected_context


def test_factory_control_permission_catalog_has_distinct_platform_actions():
    definitions = {
        item.code: item
        for item in permission_catalog.definitions
        if item.resource == "factory_control"
    }
    assert {code: definition.action for code, definition in definitions.items()} == {
        LaunchPlatformPermission.FACTORY_CONTROL_READ: "read",
        LaunchPlatformPermission.FACTORY_CONTROL_INGEST: "ingest",
        LaunchPlatformPermission.FACTORY_CONTROL_SNAPSHOT: "snapshot",
    }
    assert all(
        definition.scope.value == "platform" for definition in definitions.values()
    )


def test_factory_control_migration_does_not_auto_assign_platform_authority():
    migration = (
        Path(__file__).resolve().parents[3]
        / "alembic/versions/p2r4t6v8x1z3_create_factory_control_telemetry.py"
    ).read_text()
    assert "INSERT INTO platform_authority_assignments" not in migration
