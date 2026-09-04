"""Checkpointed SOURCE.4 admission into the sanctioned empty Preview scope."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.customer_migration.models import CustomerSourceIdentity
from app.database.session import AsyncSessionFactory
from app.estimates.models import Estimate
from app.financials.models import Invoice, Payment
from app.jobs.models import Job
from app.operational_migration.hcp_migration2_command import resolve_rehearsal_context
from app.operational_migration.hcp_migration2_plan import (
    HcpMigration2ExecutionPlanBuilder,
)
from app.operational_migration.hcp_migration2_runner import (
    HcpMigration2Runner,
    SafeEvidenceError,
)
from app.operational_migration.models import HcpMigrationMasterRun
from app.scheduling.models import Appointment

COMMAND_VERSION = "hcp-source4-preview-admission/v1"
PUBLIC_DIGEST = "9fc7ee89fbbdc956033607c5cd672f92fce1a3b192f61fc0ed68e6002eebcc87"
EMPTY_MANIFEST_DIGEST = (
    "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class PreviewAdmissionAuthority:
    expected_repository_sha: str
    expected_schema_head: str
    expected_database: str
    package_root: Path
    control_csv: Path
    migration1a_root: Path
    company_id: UUID
    branch_id: UUID
    actor_id: UUID
    backup_path: Path
    backup_sha256: str
    public_reconciliation_digest: str
    private_manifest_path: Path
    private_manifest_digest: str

    @classmethod
    def load(cls, path: Path) -> PreviewAdmissionAuthority:
        try:
            if stat.S_IMODE(path.stat().st_mode) & 0o077:
                raise SafeEvidenceError(
                    "preview_admission_authority_permissions", "0" * 64
                )
            value = json.loads(path.read_bytes())
            if value.get("contract") != COMMAND_VERSION:
                raise ValueError
            return cls(
                **{
                    **{
                        key: value[key]
                        for key in (
                            "expected_repository_sha",
                            "expected_schema_head",
                            "expected_database",
                            "backup_sha256",
                            "public_reconciliation_digest",
                            "private_manifest_digest",
                        )
                    },
                    **{
                        key: Path(value[key])
                        for key in (
                            "package_root",
                            "control_csv",
                            "migration1a_root",
                            "backup_path",
                            "private_manifest_path",
                        )
                    },
                    **{
                        key: UUID(value[key])
                        for key in ("company_id", "branch_id", "actor_id")
                    },
                }
            )
        except SafeEvidenceError:
            raise
        except Exception as error:
            raise SafeEvidenceError(
                "preview_admission_authority_invalid", "0" * 64
            ) from error

    def verify_files(self) -> None:
        if (
            self.public_reconciliation_digest != PUBLIC_DIGEST
            or self.private_manifest_digest != EMPTY_MANIFEST_DIGEST
        ):
            raise SafeEvidenceError(
                "preview_reconciliation_authority_mismatch", "0" * 64
            )
        if (
            not self.backup_path.is_file()
            or _sha256(self.backup_path) != self.backup_sha256
        ):
            raise SafeEvidenceError("preview_backup_authority_mismatch", "0" * 64)
        manifest = json.loads(self.private_manifest_path.read_bytes())
        if (
            manifest.get("digest") != EMPTY_MANIFEST_DIGEST
            or manifest.get("entries") != []
        ):
            raise SafeEvidenceError("preview_manifest_not_empty", "0" * 64)


@dataclass(frozen=True)
class PreviewAdmissionTarget:
    environment: str
    database_url: str
    expected_database: str
    production_access_enabled: bool = False
    preview_access_enabled: bool = True
    initially_empty_required: bool = False

    def validate(self) -> str:
        parsed = urlparse(self.database_url)
        if (
            self.environment != "preview"
            or parsed.path.removeprefix("/") != self.expected_database
            or self.production_access_enabled
            or not self.preview_access_enabled
        ):
            raise ValueError("sanctioned Preview target required")
        return hashlib.sha256(
            json.dumps(
                {"environment": self.environment, "database": self.expected_database},
                sort_keys=True,
            ).encode()
        ).hexdigest()


async def _count(
    session: AsyncSession, model: Any, company_id: UUID, branch_id: UUID
) -> int:
    query = select(func.count()).select_from(model)
    if hasattr(model, "branch_id"):
        query = query.where(
            model.company_id == company_id, model.branch_id == branch_id
        )
    return int(await session.scalar(query) or 0)


async def run(
    authority: PreviewAdmissionAuthority,
    *,
    execute: bool,
    factory: async_sessionmaker[AsyncSession] = AsyncSessionFactory,
) -> dict[str, object]:
    authority.verify_files()
    repository_sha = subprocess.run(  # noqa: ASYNC221
        ("git", "rev-parse", "HEAD"), check=True, capture_output=True, text=True
    ).stdout.strip()
    if repository_sha != authority.expected_repository_sha:
        raise SafeEvidenceError("preview_repository_authority_mismatch", "0" * 64)
    if (
        os.getenv("TARGET_ENVIRONMENT") != "preview"
        or os.getenv("PRODUCTION_ACCESS_ENABLED", "false") != "false"
    ):
        raise SafeEvidenceError("preview_runtime_boundary_invalid", "0" * 64)
    async with factory() as session:
        schema = await session.scalar(text("SELECT version_num FROM alembic_version"))
        context = await resolve_rehearsal_context(session, authority, credentialed=True)  # type: ignore[arg-type]
        scoped = {
            model.__tablename__: await _count(
                session, model, authority.company_id, authority.branch_id
            )
            for model in (
                Job,
                Appointment,
                Estimate,
                Invoice,
                Payment,
                HcpMigrationMasterRun,
                CustomerSourceIdentity,
            )
        }
    if schema != authority.expected_schema_head:
        raise SafeEvidenceError("preview_schema_authority_mismatch", "0" * 64)
    if any(scoped.values()):
        raise SafeEvidenceError(
            "preview_sanctioned_scope_not_pristine",
            hashlib.sha256(json.dumps(scoped, sort_keys=True).encode()).hexdigest(),
        )
    builder = HcpMigration2ExecutionPlanBuilder(
        package_root=authority.package_root,
        control_csv=authority.control_csv,
        migration1a_root=authority.migration1a_root,
        schema_head=authority.expected_schema_head,
    )
    plan, summary = builder.build(baseline_counts=scoped)
    packet: dict[str, object] = {
        "command": COMMAND_VERSION,
        "mode": "execute" if execute else "qualify",
        "plan_digest": summary.plan_digest,
        "schema_head": authority.expected_schema_head,
        "checkpointed": True,
        "atomic": False,
        "rollback": "full_database_restore",
        "backup_sha256": authority.backup_sha256,
    }
    if not execute:
        return packet
    target: Any = PreviewAdmissionTarget(
        "preview", settings.database_url, authority.expected_database
    )
    result = await HcpMigration2Runner().execute(
        factory,
        context=context,
        target=target,
        plan=plan,
    )
    return {**packet, "result": result}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("qualify", "execute"))
    parser.add_argument("--authority-file", required=True, type=Path)
    parser.add_argument("--authorize-execution", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "execute" and not args.authorize_execution:
        print(
            json.dumps(
                {
                    "status": "rejected",
                    "code": "explicit_execution_authorization_required",
                }
            )
        )
        return 2
    try:
        output = asyncio.run(
            run(
                PreviewAdmissionAuthority.load(args.authority_file),
                execute=args.mode == "execute",
            )
        )
    except Exception as error:  # noqa: BLE001
        code = (
            error.code
            if isinstance(error, SafeEvidenceError)
            else "preview_admission_failed"
        )
        print(json.dumps({"status": "rejected", "code": code}))
        return 2
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
