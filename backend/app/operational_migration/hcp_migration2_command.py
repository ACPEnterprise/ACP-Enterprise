"""Sanctioned executable boundary for the sealed HCP.MIGRATION.2 lifecycle."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.database.session import AsyncSessionFactory, engine
from app.operational_migration.hcp_migration2_plan import (
    HcpMigration2Application,
    HcpMigration2ExecutionPlanBuilder,
    HcpMigration2FinancialSupersedingAuthority,
    HcpMigration2SupersedingRepairAuthority,
)
from app.operational_migration.hcp_migration2_runner import SafeEvidenceError
from app.operational_migration.hcp_owner_disposition import NonProductionTarget
from app.operational_migration.hcp_rehearsal_authority import (
    ACTOR_ID,
    BRANCH_ID,
    COMPANY_ID,
    require_sanctioned_context,
    require_sanctioned_target,
)
from app.operational_migration.models import HcpMigrationMasterRun
from app.platform.branch.models import Branch
from app.platform.company.membership_models import (
    Membership,
    MembershipBranchAccess,
)
from app.platform.company.models import Company
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.models import (
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.platform.users.models import User, UserCredential

COMMAND_VERSION = "hcp-migration-2m-command/v1"
EXIT_SUCCESS = 0
EXIT_PREFLIGHT_REJECTED = 2
EXIT_AUTHORITY_REJECTED = 3
EXIT_APPLICATION_FAILED = 4


@dataclass(frozen=True)
class ProtectedExecutionAuthority:
    expected_repository_sha: str
    package_root: Path
    control_csv: Path
    migration1a_root: Path
    master_run_id: UUID
    original_plan_id: UUID
    original_plan_digest: str
    generation1_repair_id: UUID
    generation1_repair_plan_digest: str
    failed_operational_child_run_id: UUID
    superseding_plan_id: UUID
    superseding_plan_digest: str
    sequence_contract_version: str
    sequence_digest: str
    checkpoint_digest: str
    customer_child_run_id: UUID
    original_operational_child_run_id: UUID
    original_financial_child_run_id: UUID
    history_child_run_id: UUID
    financial_repair_id: UUID
    nonconforming_financial_child_run_id: UUID
    financial_successor_plan_id: UUID
    financial_successor_plan_digest: str
    empty_invoice_identity_digest: str
    invoice_evidence_count: int
    company_id: UUID
    branch_id: UUID
    actor_id: UUID
    package_digest: str
    builder_version: str
    expected_schema_head: str

    @classmethod
    def load(cls, path: Path) -> ProtectedExecutionAuthority:
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise SafeEvidenceError("protected_authority_permissions_unsafe", "0" * 64)
        try:
            payload = json.loads(path.read_text())
            if not isinstance(payload, dict):
                raise TypeError
            uuid_fields = {
                "master_run_id",
                "original_plan_id",
                "generation1_repair_id",
                "failed_operational_child_run_id",
                "superseding_plan_id",
                "customer_child_run_id",
                "original_operational_child_run_id",
                "original_financial_child_run_id",
                "history_child_run_id",
                "financial_repair_id",
                "nonconforming_financial_child_run_id",
                "financial_successor_plan_id",
                "company_id",
                "branch_id",
                "actor_id",
            }
            path_fields = {"package_root", "control_csv", "migration1a_root"}
            values: dict[str, Any] = dict(payload)
            for name in uuid_fields:
                values[name] = UUID(str(values[name]))
            for name in path_fields:
                values[name] = Path(str(values[name])).expanduser().resolve()
            authority = cls(**values)
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise SafeEvidenceError("protected_authority_invalid", "1" * 64) from error
        authority.validate()
        return authority

    def validate(self) -> None:
        digests = (
            self.original_plan_digest,
            self.generation1_repair_plan_digest,
            self.superseding_plan_digest,
            self.sequence_digest,
            self.checkpoint_digest,
            self.financial_successor_plan_digest,
            self.empty_invoice_identity_digest,
            self.package_digest,
        )
        if (
            any(len(value) != 64 for value in digests)
            or len(self.expected_repository_sha) != 40
            or not self.expected_schema_head
            or self.invoice_evidence_count < 1
            or (self.company_id, self.branch_id, self.actor_id)
            != (COMPANY_ID, BRANCH_ID, ACTOR_ID)
        ):
            raise SafeEvidenceError("protected_authority_mismatch", "2" * 64)
        if not all(
            path.exists()
            for path in (self.package_root, self.control_csv, self.migration1a_root)
        ):
            raise SafeEvidenceError("protected_authority_source_missing", "3" * 64)

    def application_authority(self) -> HcpMigration2FinancialSupersedingAuthority:
        operational = HcpMigration2SupersedingRepairAuthority(
            master_run_id=self.master_run_id,
            original_plan_id=self.original_plan_id,
            original_plan_digest=self.original_plan_digest,
            generation1_repair_id=self.generation1_repair_id,
            generation1_repair_plan_digest=self.generation1_repair_plan_digest,
            failed_operational_child_run_id=self.failed_operational_child_run_id,
            superseding_plan_id=self.superseding_plan_id,
            superseding_plan_digest=self.superseding_plan_digest,
            repair_generation=2,
            sequencing_contract_version=self.sequence_contract_version,
            sequence_digest=self.sequence_digest,
            checkpoint_digest=self.checkpoint_digest,
            customer_child_run_id=self.customer_child_run_id,
            original_operational_child_run_id=self.original_operational_child_run_id,
            original_financial_child_run_id=self.original_financial_child_run_id,
            history_child_run_id=self.history_child_run_id,
            company_id=self.company_id,
            branch_id=self.branch_id,
            actor_id=self.actor_id,
            package_digest=self.package_digest,
            builder_version=self.builder_version,
        )
        return HcpMigration2FinancialSupersedingAuthority(
            operational_authority=operational,
            financial_repair_id=self.financial_repair_id,
            nonconforming_financial_child_run_id=(
                self.nonconforming_financial_child_run_id
            ),
            successor_plan_id=self.financial_successor_plan_id,
            successor_plan_digest=self.financial_successor_plan_digest,
            empty_invoice_identity_digest=self.empty_invoice_identity_digest,
            invoice_evidence_count=self.invoice_evidence_count,
        )


async def resolve_rehearsal_context(
    session: AsyncSession, authority: ProtectedExecutionAuthority
) -> AuthorizationContext:
    user = await session.get(User, authority.actor_id)
    company = await session.get(Company, authority.company_id)
    branch = await session.get(Branch, authority.branch_id)
    membership = await session.scalar(
        select(Membership).where(
            Membership.user_id == authority.actor_id,
            Membership.company_id == authority.company_id,
            Membership.status == "active",
        )
    )
    credential = await session.scalar(
        select(UserCredential).where(UserCredential.user_id == authority.actor_id)
    )
    branch_access = None
    if membership is not None:
        branch_access = await session.scalar(
            select(MembershipBranchAccess).where(
                MembershipBranchAccess.membership_id == membership.id,
                MembershipBranchAccess.branch_id == authority.branch_id,
            )
        )
    roles: tuple[Role, ...] = ()
    permissions: tuple[Permission, ...] = ()
    if membership is not None:
        roles = tuple(
            (
                await session.scalars(
                    select(Role)
                    .join(MembershipRole, MembershipRole.role_id == Role.id)
                    .where(
                        MembershipRole.membership_id == membership.id,
                        MembershipRole.revoked_at.is_(None),
                        Role.status == "active",
                        Role.archived_at.is_(None),
                    )
                )
            ).all()
        )
        permissions = tuple(
            (
                await session.scalars(
                    select(Permission)
                    .join(RolePermission, RolePermission.permission_id == Permission.id)
                    .join(MembershipRole, MembershipRole.role_id == RolePermission.role_id)
                    .where(
                        MembershipRole.membership_id == membership.id,
                        MembershipRole.revoked_at.is_(None),
                        Permission.status == "active",
                        Permission.retired_at.is_(None),
                    )
                )
            ).unique().all()
        )
    if (
        user is None
        or company is None
        or branch is None
        or membership is None
        or branch_access is None
        or credential is not None
        or user.status != "active"
        or company.status != "active"
        or branch.status != "active"
        or branch.company_id != company.id
    ):
        raise SafeEvidenceError("rehearsal_actor_context_invalid", "4" * 64)
    context = AuthorizationContext(
        user=user,
        company=company,
        membership=membership,
        authorized_branches=(branch,),
        active_branch=branch,
        effective_roles=roles,
        effective_permissions=permissions,
        credential_version=0,
        authorization_version=user.authorization_version,
    )
    require_sanctioned_context(context)
    return context


def _target() -> NonProductionTarget:
    target = NonProductionTarget(
        environment=os.environ.get("TARGET_ENVIRONMENT", ""),
        database_url=settings.database_url,
        expected_database="acp_hcp_rehearsal_import",
        production_access_enabled=os.environ.get("PRODUCTION_ACCESS_ENABLED", "true").lower()
        != "false",
        preview_access_enabled=os.environ.get("PREVIEW_ACCESS_ENABLED", "true").lower()
        != "false",
        initially_empty_required=True,
    )
    require_sanctioned_target(target)
    return target


def _repository_sha() -> str:
    result = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=Path(__file__).resolve().parents[3],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


async def run_command(
    *,
    mode: str,
    authority_file: Path,
    authorize_execution: bool,
    factory: async_sessionmaker[AsyncSession] = AsyncSessionFactory,
) -> dict[str, object]:
    authority = ProtectedExecutionAuthority.load(authority_file)
    if _repository_sha() != authority.expected_repository_sha:
        raise SafeEvidenceError("repository_authority_mismatch", "5" * 64)
    target = _target()
    async with factory() as session:
        context = await resolve_rehearsal_context(session, authority)
        schema_head = await session.scalar(text("SELECT version_num FROM alembic_version"))
    if schema_head != authority.expected_schema_head:
        raise SafeEvidenceError("schema_authority_mismatch", "9" * 64)
    builder = HcpMigration2ExecutionPlanBuilder(
        package_root=authority.package_root,
        control_csv=authority.control_csv,
        migration1a_root=authority.migration1a_root,
    )
    application = HcpMigration2Application(builder=builder)
    application_authority = authority.application_authority()
    async with factory() as session:
        master = await session.get(HcpMigrationMasterRun, authority.master_run_id)
    if master is None:
        raise SafeEvidenceError("authorized_master_missing", "7" * 64)
    if mode == "qualify":
        result = await application.qualify_financial_superseding_repair(
            factory, context=context, target=target, authority=application_authority
        )
    else:
        if not authorize_execution:
            raise SafeEvidenceError("explicit_execution_authorization_required", "6" * 64)
        if mode == "execute" and master.status == "completed":
            raise SafeEvidenceError("execution_mode_master_state_mismatch", "7" * 64)
        if mode == "replay" and master.status != "completed":
            raise SafeEvidenceError("replay_mode_master_state_mismatch", "8" * 64)
        result = await application.execute(
            factory,
            context=context,
            target=target,
            repair_authority=application_authority,
        )
    return {"command": COMMAND_VERSION, "mode": mode, **result}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("mode", choices=("qualify", "execute", "replay"))
    result.add_argument("--authority-file", required=True, type=Path)
    result.add_argument("--authorize-execution", action="store_true")
    return result


async def _main(args: argparse.Namespace) -> int:
    try:
        output = await run_command(
            mode=args.mode,
            authority_file=args.authority_file,
            authorize_execution=args.authorize_execution,
        )
        print(json.dumps(output, sort_keys=True, separators=(",", ":")))
        return EXIT_SUCCESS
    finally:
        await engine.dispose()


def main() -> None:
    try:
        code = asyncio.run(_main(parser().parse_args()))
    except SafeEvidenceError as error:
        print(
            json.dumps(
                {"status": "rejected", "code": error.code},
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        if error.code.startswith(("repository_", "schema_", "protected_authority_source_")):
            code = EXIT_PREFLIGHT_REJECTED
        elif "authority" in error.code or "scope" in error.code:
            code = EXIT_AUTHORITY_REJECTED
        else:
            code = EXIT_APPLICATION_FAILED
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        print(
            '{"status":"failed","code":"hcp_migration_command_failed"}',
            file=sys.stderr,
        )
        code = EXIT_APPLICATION_FAILED
    raise SystemExit(code)


if __name__ == "__main__":
    main()
