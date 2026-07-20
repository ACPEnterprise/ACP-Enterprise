from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.auth.passwords import PasswordService
from app.platform.bootstrap.config import BootstrapConfiguration
from app.platform.bootstrap.repository import BootstrapRepository
from app.platform.permissions.catalog import permission_catalog


@dataclass(frozen=True)
class BootstrapResult:
    initialized: bool
    company_id: UUID | None = None
    branch_id: UUID | None = None
    administrator_user_id: UUID | None = None


class BootstrapService:
    def __init__(
        self,
        *,
        repository: BootstrapRepository,
        password_service: PasswordService,
    ) -> None:
        self.repository = repository
        self.password_service = password_service

    async def initialize(
        self,
        session: AsyncSession,
        configuration: BootstrapConfiguration,
    ) -> BootstrapResult:
        plaintext_password = configuration.administrator_password.get_secret_value()
        self.password_service.validate_policy(plaintext_password)
        permission_catalog.validate()
        now = datetime.now(timezone.utc)

        async with session.begin():
            await self.repository.acquire_initialization_lock(session)
            if await self.repository.is_initialized(session):
                return BootstrapResult(initialized=False)

            password_hash = self.password_service.hash_password(plaintext_password)

            company = self.repository.create_company(
                session,
                name=configuration.company_name,
                code=configuration.company_code,
                timezone=configuration.company_timezone,
            )
            await session.flush()
            branch = self.repository.create_branch(
                session,
                company_id=company.id,
                name=configuration.branch_name,
                code=configuration.branch_code,
                timezone=configuration.company_timezone,
            )
            administrator = self.repository.create_administrator(
                session,
                email=str(configuration.administrator_email),
                first_name=configuration.administrator_first_name,
                last_name=configuration.administrator_last_name,
                display_name=configuration.administrator_display_name
                or f"{configuration.administrator_first_name} "
                f"{configuration.administrator_last_name}",
                password_hash=password_hash,
                now=now,
            )
            await session.flush()
            membership = self.repository.create_membership(
                session,
                user_id=administrator.id,
                company_id=company.id,
                branch_id=branch.id,
                now=now,
            )
            permissions = self.repository.create_permissions(
                session, permission_catalog.definitions
            )
            roles = self.repository.create_system_roles(
                session,
                company_id=company.id,
                actor_user_id=administrator.id,
            )
            await session.flush()
            administrator_role = roles["COMPANY_ADMINISTRATOR"]
            self.repository.assign_permissions(
                session,
                role=administrator_role,
                permissions=permissions.values(),
                actor_user_id=administrator.id,
                now=now,
            )
            self.repository.assign_role(
                session,
                company_id=company.id,
                membership_id=membership.id,
                role_id=administrator_role.id,
                actor_user_id=administrator.id,
                now=now,
            )
            await session.flush()

            return BootstrapResult(
                initialized=True,
                company_id=company.id,
                branch_id=branch.id,
                administrator_user_id=administrator.id,
            )
