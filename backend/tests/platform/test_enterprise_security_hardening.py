import logging
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import jwt
import pytest
from fastapi import FastAPI, Response
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings
from app.platform.audit.models import AuditRecord
from app.platform.audit.service import AuditEntry, AuditService
from app.platform.auth.access_tokens import AccessTokenService
from app.platform.auth.errors import InvalidTokenError
from app.platform.contracts.manifest import platform_contract_manifest
from app.platform.permissions.catalog import (
    PermissionCatalog,
    PermissionCatalogError,
    PermissionDefinition,
    PermissionScope,
    permission_catalog,
)
from app.platform.reliability.correlation import CorrelationMiddleware
from app.platform.security.decisions import (
    AuthorizationDecisionLogger,
    AuthorizationDenial,
)
from app.platform.security.metrics import SecurityMetrics, security_metrics
from app.platform.security.middleware import (
    SecurityHeadersMiddleware,
    TrustedProxyMiddleware,
)


def build_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "access_token_signing_key": "test-signing-key-with-at-least-32-characters",
        "security_token_hmac_key": "test-hmac-key-with-at-least-32-characters",
    }
    values.update(overrides)
    return Settings.model_validate(values)


@pytest.mark.asyncio
async def test_audit_generation_rejects_secrets_and_is_database_immutable() -> None:
    configuration = build_settings()
    engine = create_async_engine(configuration.database_url)
    record_id = uuid4()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            async with session.begin():
                record = AuditService.stage(
                    session,
                    AuditEntry(
                        action="company.membership_created",
                        resource_type="membership",
                        resource_id=record_id,
                        details={"status": "active"},
                    ),
                )
            audit_id = record.id
        async with AsyncSession(engine) as session:
            stored = await session.scalar(
                select(AuditRecord).where(AuditRecord.id == audit_id)
            )
            assert stored is not None
            assert stored.resource_id == record_id
            with pytest.raises(DBAPIError):
                await session.execute(
                    update(AuditRecord)
                    .where(AuditRecord.id == audit_id)
                    .values(outcome="failure")
                )
    finally:
        await engine.dispose()

    with pytest.raises(ValueError):
        AuditService.stage(
            object(),  # type: ignore[arg-type]
            AuditEntry(
                action="authentication.login",
                resource_type="user",
                details={"refresh_token": "prohibited"},
            ),
        )
    for entry in (
        AuditEntry(
            action="authentication.login",
            resource_type="user",
            details={"message": "Bearer audit-canary.secret"},
        ),
        AuditEntry(
            action="authentication.login",
            resource_type="user",
            user_agent="client token=audit-canary",
        ),
        AuditEntry(
            action="authentication.login",
            resource_type="user",
            reason_code="postgresql://user:audit-canary@example.invalid/acp",
        ),
    ):
        with pytest.raises(ValueError, match="Sensitive values"):
            AuditService.stage(object(), entry)  # type: ignore[arg-type]


def test_security_metrics_are_centralized_and_failure_tolerant() -> None:
    metrics = SecurityMetrics()
    metrics.increment("authorization_denials_total", reason="missing_permission")
    metrics.increment("authorization_denials_total", reason="missing_permission")
    assert (
        metrics.value("authorization_denials_total", reason="missing_permission") == 2
    )
    assert metrics.snapshot()


@pytest.mark.asyncio
async def test_security_headers_and_trusted_proxy_validation() -> None:
    configuration = build_settings(
        trust_forwarded_headers=True,
        trusted_proxy_cidrs=["10.0.0.0/8"],
        hsts_enabled=True,
    )
    app = FastAPI()
    app.add_middleware(TrustedProxyMiddleware, configuration=configuration)
    app.add_middleware(SecurityHeadersMiddleware, configuration=configuration)
    app.add_middleware(CorrelationMiddleware)

    @app.get("/client")
    async def client_endpoint() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/api/protected")
    async def protected_endpoint() -> dict[str, str]:
        return {"classification": "protected"}

    @app.get("/api/revalidated")
    async def revalidated_endpoint() -> Response:
        return Response(headers={"Cache-Control": "no-cache"})

    @app.get("/api/unsafe-cache")
    async def unsafe_cache_endpoint() -> Response:
        return Response(headers={"Cache-Control": "public, max-age=3600"})

    @app.get("/api/no-transform")
    async def no_transform_endpoint() -> Response:
        return Response(headers={"Cache-Control": "no-cache, no-transform"})

    trusted_transport = httpx.ASGITransport(app=app, client=("10.0.0.8", 443))
    async with httpx.AsyncClient(
        transport=trusted_transport, base_url="https://test"
    ) as trusted_client:
        response = await trusted_client.get(
            "/client",
            headers={"X-Forwarded-For": "203.0.113.8", "X-Forwarded-Proto": "https"},
        )
        protected = await trusted_client.get("/api/protected")
        revalidated = await trusted_client.get("/api/revalidated")
        unsafe_cache = await trusted_client.get("/api/unsafe-cache")
        no_transform = await trusted_client.get("/api/no-transform")
    assert response.status_code == 200
    assert response.headers["strict-transport-security"].startswith("max-age=")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "content-security-policy" in response.headers
    assert "permissions-policy" in response.headers
    assert "cache-control" not in response.headers
    assert protected.headers["cache-control"] == "private, no-store"
    assert revalidated.headers["cache-control"] == "private, no-store"
    assert unsafe_cache.headers["cache-control"] == "private, no-store"
    assert no_transform.headers["cache-control"] == (
        "private, no-store, no-transform"
    )

    untrusted_transport = httpx.ASGITransport(app=app, client=("198.51.100.9", 80))
    async with httpx.AsyncClient(
        transport=untrusted_transport, base_url="http://test"
    ) as untrusted_client:
        rejected = await untrusted_client.get(
            "/client", headers={"X-Forwarded-For": "203.0.113.9"}
        )
    assert rejected.status_code == 400
    assert rejected.json()["detail"]["code"] == "validation"
    assert rejected.json()["detail"]["recovery"] == "USER_CORRECTION_REQUIRED"
    assert rejected.json()["detail"]["correlation_id"] == rejected.headers[
        "x-request-id"
    ]
    assert "203.0.113.9" not in rejected.text

    malformed_transport = httpx.ASGITransport(app=app, client=("10.0.0.8", 443))
    async with httpx.AsyncClient(
        transport=malformed_transport, base_url="https://test"
    ) as malformed_client:
        malformed = await malformed_client.get(
            "/client",
            headers={"X-Forwarded-For": "protected-source-canary"},
        )
    assert malformed.status_code == 400
    assert malformed.json()["detail"]["code"] == "validation"
    assert malformed.json()["detail"]["correlation_id"] == malformed.headers[
        "x-request-id"
    ]
    assert "protected-source-canary" not in malformed.text


def test_jwt_key_identifiers_support_rotation_and_reject_unknown_keys() -> None:
    old_key = "old-signing-key-with-at-least-32-characters"
    new_key = "new-signing-key-with-at-least-32-characters"
    configuration = build_settings(
        access_token_keys={"old": old_key, "new": new_key},
        access_token_active_kid="new",
    )
    service = AccessTokenService(configuration)
    user_id = uuid4()
    session_id = uuid4()
    token, _ = service.issue(
        user_id=user_id,
        session_id=session_id,
        credential_version=1,
        authorization_version=1,
    )
    assert jwt.get_unverified_header(token)["kid"] == "new"
    assert service.decode(token).user_id == user_id

    now = datetime.now(timezone.utc)
    claims = jwt.decode(
        token, new_key, algorithms=["HS256"], options={"verify_aud": False}
    )
    old_token = jwt.encode(claims, old_key, algorithm="HS256", headers={"kid": "old"})
    assert service.decode(old_token).session_id == session_id
    unknown = jwt.encode(claims, old_key, algorithm="HS256", headers={"kid": "unknown"})
    with pytest.raises(InvalidTokenError):
        service.decode(unknown)
    assert now.tzinfo is not None


def test_permission_catalog_rejects_duplicates_invalid_scope_and_redefinitions() -> (
    None
):
    permission_catalog.validate()
    definition = PermissionDefinition(
        code="COMPANY_TEST_READ",
        name="Test Read",
        resource="test",
        action="read",
        scope=PermissionScope.COMPANY,
    )
    with pytest.raises(PermissionCatalogError):
        PermissionCatalog((definition, definition)).validate()
    with pytest.raises(PermissionCatalogError):
        PermissionCatalog(
            (
                PermissionDefinition(
                    code="PLATFORM_TEST_READ",
                    name="Test Read",
                    resource="test",
                    action="read",
                    scope=PermissionScope.COMPANY,
                ),
            )
        ).validate()


def test_production_configuration_fails_closed() -> None:
    with pytest.raises(ValueError):
        Settings(
            environment="production",
            access_token_signing_key="local-development-signing-key-change-before-use",
            security_token_hmac_key="local-development-hmac-key-change-before-use",
            hsts_enabled=False,
        )
    production = Settings(
        environment="production",
        access_token_keys={"2026-07": "a-secure-production-signing-key-value-0001"},
        access_token_active_kid="2026-07",
        security_token_hmac_key="a-secure-production-hmac-key-value-00000001",
        security_headers_enabled=True,
        hsts_enabled=True,
        cors_allowed_origins=["https://app.acp.example"],
        trust_forwarded_headers=True,
        trusted_proxy_cidrs=["10.0.0.0/8"],
        platform_contract_expected_fingerprint=platform_contract_manifest.fingerprint,
    )
    assert production.hsts_enabled


def test_authorization_decision_logging_is_structured_and_generic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    security_metrics.reset_for_testing()
    with caplog.at_level(logging.WARNING, logger="acp.security.authorization"):
        AuthorizationDecisionLogger.denied(
            AuthorizationDenial(
                reason="missing_permission",
                actor_user_id=uuid4(),
                company_id=uuid4(),
                permission_code="COMPANY_ROLE_MANAGE",
                resource="permission_dependency",
            )
        )
    record = caplog.records[-1]
    decision = record.security_decision  # type: ignore[attr-defined]
    assert decision["reason"] == "missing_permission"
    assert decision["permission"] == "COMPANY_ROLE_MANAGE"
    assert (
        security_metrics.value(
            "authorization_denials_total", reason="missing_permission"
        )
        == 1
    )


def test_audit_service_failure_is_fail_closed() -> None:
    class FailingSession:
        def add(self, value: object) -> None:
            raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        AuditService.stage(
            FailingSession(),  # type: ignore[arg-type]
            AuditEntry(action="company.role_created", resource_type="role"),
        )
