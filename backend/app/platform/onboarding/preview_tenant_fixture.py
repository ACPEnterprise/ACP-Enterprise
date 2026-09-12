"""Preview-only, deterministic tenant boundary for operator acceptance fixtures."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.branch.models import Branch
from app.platform.company.models import Company
from app.platform.onboarding.service import OnboardingConflictError
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AdministrationPermission

FIXTURE_VERSION = "preview.synthetic.tenant.v1"
FIXTURE_COMPANY_ID = UUID("31ba6867-2d8a-55dd-9e34-d67c684ee41c")
FIXTURE_BRANCH_ID = UUID("95bf7a14-09b0-51b6-b3cb-7946523ec093")
FIXTURE_COMPANY_NAME = "ACP Synthetic Acceptance — Non-Production"
FIXTURE_COMPANY_CODE = "ACP_ACCEPTANCE"
FIXTURE_BRANCH_NAME = "Synthetic Acceptance Branch"
FIXTURE_BRANCH_CODE = "ACCEPTANCE"
FIXTURE_ADVISORY_LOCK_ID = 7_056_984_111_269_341
REQUIRED_PERMISSIONS = frozenset(
    {
        AdministrationPermission.COMPANY_ADMINISTER,
        AdministrationPermission.IDENTITY_ONBOARDING_MANAGE,
    }
)


@dataclass(frozen=True)
class PreviewSyntheticTenantCommand:
    fixture_version: str
    authorized: bool


@dataclass(frozen=True)
class PreviewSyntheticTenantResult:
    company_id: UUID
    branch_id: UUID
    action: str
    audit_record_id: UUID


class PreviewSyntheticTenantFixtureService:
    """Create or reuse exactly one isolated Preview acceptance tenant."""

    def __init__(
        self,
        *,
        configuration: Settings = settings,
        auditing: AuditService = audit_service,
    ) -> None:
        self.configuration = configuration
        self.auditing = auditing

    def _authorize(
        self,
        context: AuthorizationContext,
        command: PreviewSyntheticTenantCommand,
    ) -> None:
        if (
            self.configuration.environment != "preview"
            or not self.configuration.preview_acceptance_fixture_enabled
            or not command.authorized
            or command.fixture_version != FIXTURE_VERSION
        ):
            raise OnboardingConflictError(
                "Synthetic tenant fixture requires explicit Preview acceptance authority."
            )
        if not REQUIRED_PERMISSIONS.issubset(context.permission_codes):
            raise OnboardingConflictError(
                "Synthetic tenant fixture administrator permission is missing."
            )

    async def create_or_reuse(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: PreviewSyntheticTenantCommand,
    ) -> PreviewSyntheticTenantResult:
        self._authorize(context, command)
        async with session.begin():
            await session.execute(
                select(func.pg_advisory_xact_lock(FIXTURE_ADVISORY_LOCK_ID))
            )
            company = await session.get(Company, FIXTURE_COMPANY_ID)
            branch = await session.get(Branch, FIXTURE_BRANCH_ID)
            if company is None and branch is not None:
                raise OnboardingConflictError("Synthetic tenant fixture is inconsistent.")
            action = "reused"
            if company is None:
                company = Company(
                    id=FIXTURE_COMPANY_ID,
                    name=FIXTURE_COMPANY_NAME,
                    code=FIXTURE_COMPANY_CODE,
                    status="active",
                    timezone="America/New_York",
                )
                session.add(company)
                await session.flush()
                branch = Branch(
                    id=FIXTURE_BRANCH_ID,
                    company_id=FIXTURE_COMPANY_ID,
                    name=FIXTURE_BRANCH_NAME,
                    code=FIXTURE_BRANCH_CODE,
                    status="active",
                    timezone="America/New_York",
                    is_primary=True,
                )
                session.add(branch)
                await session.flush()
                action = "created"
            self._validate_existing(company, branch)
            audit = self.auditing.stage(
                session,
                AuditEntry(
                    action="preview.acceptance_tenant_fixture",
                    actor_user_id=context.user.id,
                    company_id=FIXTURE_COMPANY_ID,
                    branch_id=FIXTURE_BRANCH_ID,
                    resource_type="preview_acceptance_tenant",
                    resource_id=FIXTURE_COMPANY_ID,
                    reason_code="operator_acceptance",
                    details={
                        "environment": "preview",
                        "fixture_version": FIXTURE_VERSION,
                        "action": action,
                        "result": "success",
                    },
                ),
            )
            await session.flush()
            return PreviewSyntheticTenantResult(
                company_id=FIXTURE_COMPANY_ID,
                branch_id=FIXTURE_BRANCH_ID,
                action=action,
                audit_record_id=audit.id,
            )

    @staticmethod
    def _validate_existing(company: Company, branch: Branch | None) -> None:
        if (
            company.name != FIXTURE_COMPANY_NAME
            or company.code != FIXTURE_COMPANY_CODE
            or company.status != "active"
            or branch is None
            or branch.company_id != FIXTURE_COMPANY_ID
            or branch.name != FIXTURE_BRANCH_NAME
            or branch.code != FIXTURE_BRANCH_CODE
            or branch.status != "active"
            or not branch.is_primary
        ):
            raise OnboardingConflictError(
                "Synthetic tenant fixture identity collides with existing state."
            )

    async def record_reset(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: PreviewSyntheticTenantCommand,
    ) -> UUID:
        self._authorize(context, command)
        async with session.begin():
            company = await session.get(Company, FIXTURE_COMPANY_ID)
            branch = await session.get(Branch, FIXTURE_BRANCH_ID)
            if company is None or branch is None:
                raise OnboardingConflictError("Synthetic tenant fixture does not exist.")
            self._validate_existing(company, branch)
            audit = self.auditing.stage(
                session,
                AuditEntry(
                    action="preview.acceptance_tenant_fixture_reset",
                    actor_user_id=context.user.id,
                    company_id=FIXTURE_COMPANY_ID,
                    branch_id=FIXTURE_BRANCH_ID,
                    resource_type="preview_acceptance_tenant",
                    resource_id=FIXTURE_COMPANY_ID,
                    reason_code="operator_acceptance_reset",
                    details={
                        "environment": "preview",
                        "fixture_version": FIXTURE_VERSION,
                        "action": "reset_in_place",
                        "result": "success",
                    },
                ),
            )
            await session.flush()
            return audit.id


preview_synthetic_tenant_fixture_service = PreviewSyntheticTenantFixtureService()
