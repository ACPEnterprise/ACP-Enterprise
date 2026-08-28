"""Non-production identity and evidence foundations for HCP.MIGRATION.2."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.operational_migration.hcp_owner_disposition import NonProductionTarget
from app.operational_migration.models import UnlinkedEstimateEvidence
from app.platform.bootstrap.repository import BOOTSTRAP_ADVISORY_LOCK_ID
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership, MembershipBranchAccess
from app.platform.company.models import Company
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import MigrationPermission
from app.platform.permissions.models import (
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.users.models import User

ACTOR_EMAIL = "hcp-migration-rehearsal@service.invalid"
ACTOR_ROLE = "HCP_MIGRATION_REHEARSAL_SERVICE"
EVIDENCE_CONTRACT = "unlinked-non-operational-estimate/v1"


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


@dataclass(frozen=True)
class RehearsalActorIdentity:
    user_id: UUID
    membership_id: UUID
    role_id: UUID
    permission_id: UUID
    company_id: UUID
    branch_id: UUID
    credential_created: bool = False


@dataclass(frozen=True)
class Migration2ReleaseGate:
    owner_bindings_verified: bool
    source_package_verified: bool
    transformations_qualified: bool
    rehearsal_actor_qualified: bool
    unlinked_evidence_target_qualified: bool
    target_has_real_hcp_business_rows: bool

    @property
    def ready(self) -> bool:
        return all(
            (
                self.owner_bindings_verified,
                self.source_package_verified,
                self.transformations_qualified,
                self.rehearsal_actor_qualified,
                self.unlinked_evidence_target_qualified,
                not self.target_has_real_hcp_business_rows,
            )
        )

    @property
    def digest(self) -> str:
        return _canonical_digest(
            {"contract": "hcp-migration-2-release-gate/v1", **asdict(self)}
        )


async def initialize_rehearsal_actor(
    session: AsyncSession,
    *,
    target: NonProductionTarget,
    company_id: UUID,
    branch_id: UUID,
) -> RehearsalActorIdentity:
    """Create an idempotent, credential-less, least-privilege service actor."""
    target.validate()
    async with session.begin():
        await session.execute(
            select(func.pg_advisory_xact_lock(BOOTSTRAP_ADVISORY_LOCK_ID))
        )
        company = await session.get(Company, company_id)
        branch = await session.get(Branch, branch_id)
        if company is None or branch is None or branch.company_id != company_id:
            raise ValueError("approved rehearsal Company/Branch scope was not found")

        existing = await session.scalar(
            select(User).where(User.normalized_email == ACTOR_EMAIL)
        )
        if existing is not None:
            membership = await session.scalar(
                select(Membership).where(
                    Membership.user_id == existing.id,
                    Membership.company_id == company_id,
                )
            )
            role = await session.scalar(
                select(Role).where(
                    Role.company_id == company_id,
                    Role.code == ACTOR_ROLE,
                    Role.archived_at.is_(None),
                )
            )
            permission = await session.scalar(
                select(Permission).where(
                    Permission.code == MigrationPermission.EXECUTE_REHEARSAL
                )
            )
            if membership is None or role is None or permission is None:
                raise ValueError("existing rehearsal actor architecture is incomplete")
            return RehearsalActorIdentity(
                existing.id,
                membership.id,
                role.id,
                permission.id,
                company_id,
                branch_id,
            )

        now = datetime.now(timezone.utc)
        actor = User(
            normalized_email=ACTOR_EMAIL,
            first_name="HCP Migration",
            last_name="Service",
            display_name="HCP Migration Rehearsal Service",
            status="active",
            authorization_version=1,
            email_verified_at=None,
        )
        session.add(actor)
        await session.flush()
        membership = Membership(
            user_id=actor.id,
            company_id=company_id,
            status="active",
            default_branch_id=branch_id,
            has_all_branch_access=False,
            invited_at=now,
            accepted_at=now,
        )
        session.add(membership)
        permission = await session.scalar(
            select(Permission).where(
                Permission.code == MigrationPermission.EXECUTE_REHEARSAL
            )
        )
        if permission is None:
            permission = Permission(
                code=MigrationPermission.EXECUTE_REHEARSAL,
                name="Company Migration Rehearsal Execute",
                resource="migration_rehearsal",
                action="execute",
                status="active",
            )
            session.add(permission)
        role = Role(
            company_id=company_id,
            code=ACTOR_ROLE,
            name="HCP Migration Rehearsal Service",
            description="Credential-less actor restricted to isolated migration rehearsal.",
            status="active",
            is_system=True,
            created_by_user_id=actor.id,
            updated_by_user_id=actor.id,
        )
        session.add(role)
        await session.flush()
        session.add_all(
            (
                MembershipBranchAccess(
                    membership_id=membership.id,
                    branch_id=branch_id,
                    assigned_at=now,
                    assigned_by_user_id=actor.id,
                ),
                RolePermission(
                    role_id=role.id,
                    permission_id=permission.id,
                    assigned_at=now,
                    assigned_by_user_id=actor.id,
                ),
                MembershipRole(
                    company_id=company_id,
                    membership_id=membership.id,
                    role_id=role.id,
                    assigned_at=now,
                    assigned_by_user_id=actor.id,
                ),
            )
        )
        await session.flush()
        return RehearsalActorIdentity(
            actor.id,
            membership.id,
            role.id,
            permission.id,
            company_id,
            branch_id,
        )


@dataclass(frozen=True)
class UnlinkedEstimateEvidenceCommand:
    native_estimate_id: str
    source_digest: str
    package_digest: str
    owner_binding_digest: str
    native_customer_id: str | None
    native_service_location_id: str | None
    source_status: str
    option_evidence: tuple[dict[str, object], ...]
    source_timestamps: dict[str, object]
    source_context: dict[str, object]
    disposition: str = "UNLINKED_NON_OPERATIONAL_ESTIMATE"

    @property
    def evidence_digest(self) -> str:
        return _canonical_digest(
            {"contract": EVIDENCE_CONTRACT, "evidence": asdict(self)}
        )

    def validate(self) -> None:
        if not self.native_estimate_id.startswith("csr_"):
            raise ValueError("native HCP Estimate identity is required")
        for value in (
            self.source_digest,
            self.package_digest,
            self.owner_binding_digest,
        ):
            if len(value) != 64:
                raise ValueError("complete source and owner digests are required")
        if (
            self.native_customer_id is not None
            and not self.native_customer_id.startswith("cus_")
        ):
            raise ValueError("Customer relationship must use a native HCP identity")
        if self.native_service_location_id is not None and not (
            self.native_service_location_id.startswith("adr_")
        ):
            raise ValueError("Location relationship must use a native HCP identity")
        if self.disposition != "UNLINKED_NON_OPERATIONAL_ESTIMATE":
            raise ValueError("unsupported unlinked Estimate disposition")


async def persist_unlinked_estimate_evidence(
    session: AsyncSession,
    *,
    context: AuthorizationContext,
    command: UnlinkedEstimateEvidenceCommand,
) -> UnlinkedEstimateEvidence:
    command.validate()
    if context.active_branch is None or not context.can_access_branch(
        context.active_branch.id
    ):
        raise ValueError("authorized rehearsal Branch is required")
    if not context.has_permission(MigrationPermission.EXECUTE_REHEARSAL):
        raise ValueError("migration rehearsal permission is required")
    existing = await session.scalar(
        select(UnlinkedEstimateEvidence).where(
            UnlinkedEstimateEvidence.company_id == context.company.id,
            UnlinkedEstimateEvidence.source_system == "housecall_pro",
            UnlinkedEstimateEvidence.native_estimate_id == command.native_estimate_id,
        )
    )
    if existing is not None:
        if existing.evidence_digest != command.evidence_digest:
            raise ValueError("native Estimate identity has conflicting evidence")
        return existing
    evidence = UnlinkedEstimateEvidence(
        company_id=context.company.id,
        branch_id=context.active_branch.id,
        recorded_by_user_id=context.user.id,
        source_system="housecall_pro",
        native_estimate_id=command.native_estimate_id,
        source_digest=command.source_digest,
        package_digest=command.package_digest,
        owner_binding_digest=command.owner_binding_digest,
        evidence_digest=command.evidence_digest,
        native_customer_id=command.native_customer_id,
        native_service_location_id=command.native_service_location_id,
        source_status=command.source_status,
        option_evidence=list(command.option_evidence),
        source_timestamps=command.source_timestamps,
        source_context=command.source_context,
        disposition=command.disposition,
        job_relationship_state="ABSENT",
        reconciliation_state="PENDING_AUTHORITATIVE_JOB_LINK",
        operational_effects_enabled=False,
        accounting_truth_accepted=False,
    )
    session.add(evidence)
    await session.flush()
    return evidence
