from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.customers import models as customer_models  # noqa: F401
from app.payroll.permissions import PayrollPermission
from app.platform.audit.access_service import AuditAccessService
from app.platform.audit.models import AuditRecord
from app.platform.audit.repository import AuditReadRepository
from app.platform.audit.router import audit_access_service, list_audit_records
from app.platform.audit.service import AuditEntry, AuditService
from app.platform.launch_controls import (
    COMPANY_ADMINISTRATOR_OWNER_READ_PERMISSIONS,
    LAUNCH_ROLE_MATRIX,
    LaunchRoleCode,
    validate_launch_role_matrix,
)
from app.platform.permissions.authorization import (
    PermissionDeniedError,
    TenantAccessDeniedError,
    authorization_service,
)
from app.platform.permissions.catalog import permission_catalog
from app.platform.permissions.codes import (
    EconomicsPolicyPermission,
    LaunchPlatformPermission,
)
from app.scheduling import models as scheduling_models  # noqa: F401


@pytest_asyncio.fixture
async def audit_database():
    engine = create_async_engine(settings.database_url)
    connection = await engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(connection, expire_on_commit=False)
    try:
        yield factory
    finally:
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


def _context(company_id, branches, *, all_branches=False, audit_permission=True):
    return SimpleNamespace(
        user=SimpleNamespace(id=uuid4()),
        company=SimpleNamespace(id=company_id),
        membership=SimpleNamespace(has_all_branch_access=all_branches),
        active_branch=None,
        authorized_branch_ids=frozenset(branches),
        can_access_branch=lambda branch_id: all_branches or branch_id in branches,
        has_permission=lambda code: (
            audit_permission and code == LaunchPlatformPermission.AUDIT_READ
        ),
    )


def test_launch_role_matrix_uses_only_canonical_least_privilege_permissions() -> None:
    validate_launch_role_matrix(permission_catalog)
    roles = {role.code: role for role in LAUNCH_ROLE_MATRIX}
    assert (
        LaunchPlatformPermission.AUDIT_READ
        in roles[LaunchRoleCode.COMPANY_ADMINISTRATOR].permission_codes
    )
    assert (
        LaunchPlatformPermission.AUDIT_READ
        in roles[LaunchRoleCode.AUDITOR].permission_codes
    )
    assert (
        LaunchPlatformPermission.AUDIT_READ
        not in roles[LaunchRoleCode.DISPATCHER].permission_codes
    )
    assert roles[LaunchRoleCode.SUPPORT].permission_codes == frozenset()
    assert all(not role.tenant_impersonation_allowed for role in roles.values())
    administrator = roles[LaunchRoleCode.COMPANY_ADMINISTRATOR].permission_codes
    assert administrator == COMPANY_ADMINISTRATOR_OWNER_READ_PERMISSIONS
    assert PayrollPermission.REPORTING_READ in administrator
    assert EconomicsPolicyPermission.MEASUREMENT_READ in administrator
    assert EconomicsPolicyPermission.MEASUREMENT_EXECUTE not in administrator
    assert PayrollPermission.REPORTING_MANAGE not in administrator


def test_audit_permission_fails_closed_without_explicit_grant() -> None:
    permitted = _context(uuid4(), set(), audit_permission=True)
    denied = _context(uuid4(), set(), audit_permission=False)
    authorization_service.require_permission(  # type: ignore[arg-type]
        permitted, LaunchPlatformPermission.AUDIT_READ
    )
    with pytest.raises(PermissionDeniedError, match="Permission denied"):
        authorization_service.require_permission(  # type: ignore[arg-type]
            denied, LaunchPlatformPermission.AUDIT_READ
        )


@pytest.mark.parametrize(
    "sensitive_key",
    [
        "password",
        "api-key",
        "Authorization",
        "session cookie",
        "private_key_pem",
        "nested_token_hash",
        "social-security-number",
        "taxpayer_identification_number",
        "worker_credential_id",
    ],
)
def test_audit_details_reject_launch_secret_boundaries(sensitive_key: str) -> None:
    with pytest.raises(ValueError, match="Sensitive values"):
        AuditService._validate(
            AuditEntry(
                action="support.reviewed",
                resource_type="support_case",
                details={"nested": {sensitive_key: "must-not-be-recorded"}},
            )
        )


@pytest.mark.asyncio
async def test_audit_read_is_company_and_branch_scoped(audit_database) -> None:
    factory = audit_database
    company_id = uuid4()
    other_company_id = uuid4()
    allowed_branch = uuid4()
    denied_branch = uuid4()
    now = datetime.now(timezone.utc)
    async with factory() as session, session.begin():
        session.add_all(
            [
                AuditRecord(
                    action="company.reviewed",
                    outcome="success",
                    company_id=company_id,
                    branch_id=None,
                    resource_type="company",
                    details={"classification": "safe"},
                    occurred_at=now,
                ),
                AuditRecord(
                    action="allowed.reviewed",
                    outcome="success",
                    company_id=company_id,
                    branch_id=allowed_branch,
                    resource_type="job",
                    details={},
                    occurred_at=now,
                ),
                AuditRecord(
                    action="denied.reviewed",
                    outcome="success",
                    company_id=company_id,
                    branch_id=denied_branch,
                    resource_type="job",
                    details={},
                    occurred_at=now,
                ),
                AuditRecord(
                    action="foreign.reviewed",
                    outcome="success",
                    company_id=other_company_id,
                    branch_id=allowed_branch,
                    resource_type="job",
                    details={},
                    occurred_at=now,
                ),
            ]
        )
    service = AuditAccessService(AuditReadRepository())
    context = _context(company_id, {allowed_branch})
    async with factory() as session:
        records = await service.list_records(
            session,
            context=context,
            branch_id=None,
            limit=50,  # type: ignore[arg-type]
        )
    assert {record.action for record in records} == {"allowed.reviewed"}
    assert all(record.company_id == company_id for record in records)


@pytest.mark.asyncio
async def test_explicit_unauthorized_audit_branch_fails_closed(audit_database) -> None:
    company_id = uuid4()
    allowed_branch = uuid4()
    denied_branch = uuid4()
    service = AuditAccessService(AuditReadRepository())
    context = _context(company_id, {allowed_branch})
    async with audit_database() as session:
        with pytest.raises(TenantAccessDeniedError, match="Branch access denied"):
            await service.list_records(
                session,
                context=context,  # type: ignore[arg-type]
                branch_id=denied_branch,
                limit=50,
            )


@pytest.mark.asyncio
async def test_audit_branch_denial_has_owner_admin_recovery_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def denied(*_args, **_kwargs):
        raise TenantAccessDeniedError("protected branch identity")

    monkeypatch.setattr(audit_access_service, "list_records", denied)

    with pytest.raises(HTTPException) as raised:
        await list_audit_records(
            _context(uuid4(), {uuid4()}),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            branch_id=uuid4(),
        )

    assert raised.value.status_code == 403
    assert raised.value.detail["code"] == "forbidden"
    assert raised.value.detail["recovery"] == "OWNER_ADMIN_ACTION_REQUIRED"
    assert "protected branch identity" not in str(raised.value.detail)


def test_audit_api_schema_excludes_support_sensitive_transport_metadata() -> None:
    from app.platform.audit.schemas import AuditRecordResponse

    assert "ip_address" not in AuditRecordResponse.model_fields
    assert "user_agent" not in AuditRecordResponse.model_fields
