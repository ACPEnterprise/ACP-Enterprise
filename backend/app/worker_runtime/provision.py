import asyncio
import base64
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionFactory, engine
from app.execution_nodes.models import EngineeringExecutionNode
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership, MembershipBranchAccess
from app.platform.company.models import Company
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import (
    WorkerControlPermission,
    WorkerIdentityPermission,
)
from app.platform.permissions.models import (
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.users.models import User, UserCredential
from app.worker_control.contracts import WorkerCapability, WorkerLifecycleState
from app.worker_control.models import EngineeringWorker
from app.worker_control.service import RegisterWorkerCommand, WorkerControlService
from app.worker_identity.contracts import (
    IssuedCredentialMetadata,
    WorkerCredentialState,
    WorkerIdentityState,
)
from app.worker_identity.models import WorkerCredential, WorkerIdentity
from app.worker_identity.service import WorkerIdentityService

SAFE_CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,49}$")
SAFE_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@dataclass(frozen=True)
class ProvisioningConfig:
    company_code: str
    administrator_email: str
    worker_name: str
    private_key_file: Path
    provider_identifier: str = "connectivity"
    capabilities: tuple[WorkerCapability, ...] = (WorkerCapability.CONNECTIVITY,)
    credential_days: int = 30

    @classmethod
    def from_environment(cls) -> "ProvisioningConfig":
        config = cls(
            company_code=os.environ["ACP_WORKER_COMPANY_CODE"].strip().upper(),
            administrator_email=os.environ["ACP_WORKER_ADMINISTRATOR_EMAIL"]
            .strip()
            .lower(),
            worker_name=os.environ.get(
                "ACP_WORKER_NAME", "ACP Preview Connectivity Worker"
            ).strip(),
            private_key_file=Path(os.environ["ACP_WORKER_PRIVATE_KEY_FILE"]),
            provider_identifier=os.environ.get(
                "ACP_WORKER_PROVIDER_IDENTIFIER", "connectivity"
            ).strip(),
            capabilities=tuple(
                WorkerCapability(value.strip())
                for value in os.environ.get(
                    "ACP_WORKER_CAPABILITIES", WorkerCapability.CONNECTIVITY.value
                ).split(",")
                if value.strip()
            ),
            credential_days=int(os.environ.get("ACP_WORKER_CREDENTIAL_DAYS", "30")),
        )
        if (
            not SAFE_CODE.fullmatch(config.company_code)
            or not SAFE_EMAIL.fullmatch(config.administrator_email)
            or not config.worker_name
            or not config.provider_identifier
            or len(config.provider_identifier) > 100
            or not config.capabilities
            or len(config.worker_name) > 100
            or not 1 <= config.credential_days <= 90
            or not config.private_key_file.is_absolute()
        ):
            raise ValueError("Worker provisioning configuration is invalid.")
        return config


@dataclass(frozen=True)
class ProvisioningResult:
    worker_id: UUID
    identity_id: UUID
    credential_id: UUID


class Ed25519FileCredentialIssuer:
    """Create one owner-only private key and return public verifier metadata."""

    def __init__(self, path: Path) -> None:
        self.path = path

    async def issue(
        self, *, identity_id: UUID, credential_version: int
    ) -> IssuedCredentialMetadata:
        del identity_id, credential_version
        private_key = Ed25519PrivateKey.generate()
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_bytes = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(
            self.path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        try:
            os.write(
                descriptor,
                base64.urlsafe_b64encode(private_bytes).rstrip(b"="),
            )
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if self.path.stat().st_mode & 0o777 != 0o600:
            raise PermissionError("Worker private key permissions must be 600.")
        return IssuedCredentialMetadata(
            verifier=base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode(),
            verifier_algorithm="ed25519",
            public_key_id=f"preview-worker-{uuid4()}",
        )


class PreviewWorkerProvisioningService:
    """Explicit, permission-checked operational provisioning boundary."""

    async def provision(
        self,
        session: AsyncSession,
        *,
        config: ProvisioningConfig,
    ) -> ProvisioningResult:
        context = await self._authorization_context(session, config=config)
        required = {
            WorkerControlPermission.MANAGE,
            WorkerIdentityPermission.MANAGE,
        }
        if not required.issubset(context.permission_codes):
            raise PermissionError(
                "Provisioning administrator lacks required permission."
            )
        # Context resolution is read-only but SQLAlchemy has opened a transaction.
        # End it before invoking application services that own their transactions.
        await session.rollback()

        worker_control = WorkerControlService()
        identity_service = WorkerIdentityService(
            issuer=Ed25519FileCredentialIssuer(config.private_key_file)
        )
        existing_worker = await session.scalar(
            select(EngineeringWorker).where(
                EngineeringWorker.company_id == context.company.id,
                EngineeringWorker.provider_identifier == config.provider_identifier,
                EngineeringWorker.name == config.worker_name,
            )
        )
        if existing_worker is None:
            created_worker = await worker_control.register_worker(
                session,
                context=context,
                command=RegisterWorkerCommand(
                    provider_identifier=config.provider_identifier,
                    name=config.worker_name,
                    worker_version="1",
                    capabilities=config.capabilities,
                ),
            )
            worker_id = created_worker.id
        elif set(existing_worker.capabilities) != {
            item.value for item in config.capabilities
        }:
            raise PermissionError(
                "Existing worker capabilities do not match enrollment."
            )
        else:
            worker_id = existing_worker.id

        existing_identity = await session.scalar(
            select(WorkerIdentity).where(
                WorkerIdentity.company_id == context.company.id,
                WorkerIdentity.name == config.worker_name,
            )
        )
        if existing_identity is None:
            created_identity = await identity_service.register(
                session,
                context=context,
                name=config.worker_name,
            )
            activated_identity = await identity_service.transition_identity(
                session,
                context=context,
                identity_id=created_identity.id,
                expected_version=created_identity.version,
                state=WorkerIdentityState.ACTIVE,
            )
            bound_identity = await identity_service.bind_orchestration_worker(
                session,
                context=context,
                identity_id=activated_identity.id,
                worker_id=worker_id,
                expected_version=activated_identity.version,
            )
            identity_id = bound_identity.id
        elif (
            existing_identity.state != WorkerIdentityState.ACTIVE.value
            or existing_identity.orchestration_worker_id != worker_id
        ):
            raise PermissionError("Existing worker identity binding is inconsistent.")
        else:
            identity_id = existing_identity.id

        existing_credential = await session.scalar(
            select(WorkerCredential).where(
                WorkerCredential.company_id == context.company.id,
                WorkerCredential.identity_id == identity_id,
                WorkerCredential.state.in_(("pending", "active")),
            )
        )
        if existing_credential is not None:
            raise PermissionError(
                "Existing credential requires explicit reconciliation."
            )
        # The matching-state reconciliation queries opened a read transaction.
        # Service methods below own their write transactions.
        await session.rollback()
        credential = await identity_service.issue_credential(
            session,
            context=context,
            identity_id=identity_id,
            lifetime=timedelta(days=config.credential_days),
        )
        credential = await identity_service.activate_credential(
            session,
            context=context,
            credential_id=credential.id,
        )
        if credential.state is not WorkerCredentialState.ACTIVE:
            raise RuntimeError("Worker credential activation failed.")
        await worker_control.set_worker_lifecycle(
            session,
            context=context,
            worker_id=worker_id,
            lifecycle_state=WorkerLifecycleState.OFFLINE,
        )
        if config.provider_identifier == "controlled-code-execution":
            if WorkerCapability.ENGINEERING_EXECUTE not in config.capabilities:
                raise ValueError("Execution node must declare engineering.execute.")
            existing_node = await session.scalar(
                select(EngineeringExecutionNode).where(
                    EngineeringExecutionNode.company_id == context.company.id,
                    EngineeringExecutionNode.worker_id == worker_id,
                )
            )
            if existing_node is not None:
                raise PermissionError("Execution node already exists.")
            await session.rollback()
            async with session.begin():
                session.add(
                    EngineeringExecutionNode(
                        company_id=context.company.id,
                        worker_id=worker_id,
                        name=config.worker_name,
                        provider_identifier=config.provider_identifier,
                        credential_fingerprint=hashlib.sha256(
                            credential.verifier.encode()
                        ).hexdigest(),
                        capabilities=[item.value for item in config.capabilities],
                        status="active",
                        enrolled_at=credential.issued_at,
                        expires_at=credential.expires_at,
                        version=1,
                    )
                )
        return ProvisioningResult(
            worker_id=worker_id,
            identity_id=identity_id,
            credential_id=credential.id,
        )

    @staticmethod
    async def _authorization_context(
        session: AsyncSession,
        *,
        config: ProvisioningConfig,
    ) -> AuthorizationContext:
        company = await session.scalar(
            select(Company).where(
                Company.code == config.company_code,
                Company.status == "active",
                Company.archived_at.is_(None),
            )
        )
        user = await session.scalar(
            select(User).where(
                User.normalized_email == config.administrator_email,
                User.status == "active",
                User.archived_at.is_(None),
            )
        )
        if company is None or user is None:
            raise PermissionError("Provisioning administrator is unavailable.")
        membership = await session.scalar(
            select(Membership).where(
                Membership.company_id == company.id,
                Membership.user_id == user.id,
                Membership.status == "active",
            )
        )
        credential = await session.scalar(
            select(UserCredential).where(UserCredential.user_id == user.id)
        )
        if membership is None or credential is None:
            raise PermissionError("Provisioning administrator is unavailable.")
        roles = tuple(
            (
                await session.scalars(
                    select(Role)
                    .join(MembershipRole, MembershipRole.role_id == Role.id)
                    .where(
                        MembershipRole.membership_id == membership.id,
                        MembershipRole.company_id == company.id,
                        MembershipRole.revoked_at.is_(None),
                        Role.company_id == company.id,
                        Role.status == "active",
                        Role.archived_at.is_(None),
                    )
                )
            )
            .unique()
            .all()
        )
        permissions = tuple(
            (
                await session.scalars(
                    select(Permission)
                    .join(RolePermission, RolePermission.permission_id == Permission.id)
                    .join(Role, Role.id == RolePermission.role_id)
                    .join(MembershipRole, MembershipRole.role_id == Role.id)
                    .where(
                        MembershipRole.membership_id == membership.id,
                        MembershipRole.company_id == company.id,
                        MembershipRole.revoked_at.is_(None),
                        Role.company_id == company.id,
                        Role.status == "active",
                        Permission.status == "active",
                        Permission.retired_at.is_(None),
                    )
                )
            )
            .unique()
            .all()
        )
        branches_statement = select(Branch).where(
            Branch.company_id == company.id,
            Branch.status == "active",
            Branch.archived_at.is_(None),
        )
        if not membership.has_all_branch_access:
            branches_statement = branches_statement.join(
                MembershipBranchAccess,
                MembershipBranchAccess.branch_id == Branch.id,
            ).where(MembershipBranchAccess.membership_id == membership.id)
        branches = tuple((await session.scalars(branches_statement)).unique().all())
        return AuthorizationContext(
            user=user,
            company=company,
            membership=membership,
            authorized_branches=branches,
            active_branch=None,
            effective_roles=roles,
            effective_permissions=permissions,
            credential_version=credential.credential_version,
            authorization_version=user.authorization_version,
        )


async def run() -> int:
    try:
        config = ProvisioningConfig.from_environment()
        async with AsyncSessionFactory() as session:
            result = await PreviewWorkerProvisioningService().provision(
                session, config=config
            )
    except Exception:  # noqa: BLE001 - CLI boundary intentionally redacts all failures.
        print(
            "Worker provisioning failed; review restricted application logs.",
            file=sys.stderr,
        )
        return 1
    finally:
        await engine.dispose()
    print(f"worker_id={result.worker_id}")
    print(f"identity_id={result.identity_id}")
    print(f"credential_id={result.credential_id}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
