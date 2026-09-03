"""Preview-only binding for the sanctioned ACP Employee identity fixture."""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.platform.auth.services import AuthenticationService
from app.platform.company.admin_service import (
    CompanyAdministrationService,
    company_administration_service,
)
from app.platform.onboarding.models import IdentityOnboardingRequest
from app.platform.onboarding.service import (
    IdentityOnboardingService,
    OnboardingCommand,
    OnboardingConflictError,
    identity_onboarding_service,
)
from app.platform.permissions.authorization import AuthorizationContext

FIXTURE_KEY = "acp-employee-beta-v1"


@dataclass(frozen=True)
class PreviewIdentityFixtureCommand:
    fixture_key: str
    authorized: bool
    branch_id: UUID
    synthetic_login: str
    role_ids: tuple[UUID, ...]
    additional_permission_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class PreviewIdentityFixtureReset:
    fixture_key: str
    authorized: bool
    onboarding_request_id: UUID


class PreviewIdentityFixtureService:
    """Compose existing identity APIs without exposing a live transport or SQL path."""

    def __init__(
        self,
        *,
        configuration: Settings = settings,
        onboarding: IdentityOnboardingService = identity_onboarding_service,
        company_administration: CompanyAdministrationService = company_administration_service,
    ) -> None:
        self.configuration = configuration
        self.onboarding = onboarding
        self.company_administration = company_administration

    def _authorize(self, fixture_key: str, authorized: bool) -> None:
        if self.configuration.environment != "preview" or not authorized:
            raise OnboardingConflictError(
                "Synthetic fixture mutation requires explicit Preview authorization."
            )
        if fixture_key != FIXTURE_KEY:
            raise OnboardingConflictError("Synthetic fixture authority does not match.")

    @staticmethod
    def _login(value: str) -> str:
        login = value.strip().lower()
        if not login.endswith(".invalid") or "@allcounty" in login:
            raise OnboardingConflictError(
                "Synthetic fixture login must use a non-routable .invalid identity."
            )
        return login

    async def provision_identity(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: PreviewIdentityFixtureCommand,
    ) -> IdentityOnboardingRequest:
        self._authorize(command.fixture_key, command.authorized)
        login = self._login(command.synthetic_login)
        return await self.onboarding.initiate(
            session,
            context=context,
            command=OnboardingCommand(
                request_key=FIXTURE_KEY,
                branch_id=command.branch_id,
                first_name="Synthetic",
                last_name="Technician",
                display_name="Synthetic Beta Technician",
                employee_type="employee",
                employee_number_prefix="BETA",
                employee_number_width=4,
                role_ids=command.role_ids,
                additional_permission_ids=command.additional_permission_ids,
                login_email=login,
            ),
        )

    async def reset_identity(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: PreviewIdentityFixtureReset,
    ) -> IdentityOnboardingRequest:
        self._authorize(command.fixture_key, command.authorized)
        record = await self.onboarding.get(
            session, context=context, request_id=command.onboarding_request_id
        )
        if record.request_key != FIXTURE_KEY:
            raise OnboardingConflictError("Refusing to reset a non-fixture identity.")
        if record.status != "activated":
            record = await self.onboarding.revoke(
                session, context=context, request_id=record.id
            )
        async with session.begin():
            await AuthenticationService.revoke_user_sessions(
                session,
                user_id=record.user_id,
                reason="synthetic_preview_fixture_reset",
                now=datetime.now(timezone.utc),
            )
        await self.company_administration.set_membership_status(
            session,
            context=context,
            membership_id=record.membership_id,
            status="revoked",
        )
        return record


preview_identity_fixture_service = PreviewIdentityFixtureService()
