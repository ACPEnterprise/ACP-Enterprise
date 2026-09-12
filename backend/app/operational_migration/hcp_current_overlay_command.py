"""Fail-closed Preview command for a native HCP current-overlay admission."""

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
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.customer_migration.models import CustomerMigrationRun
from app.database.session import AsyncSessionFactory
from app.operational_migration.hcp_current_overlay import (
    CurrentOverlayExecutor,
    CurrentOverlayManifest,
    OverlayExecutionReceipt,
)
from app.operational_migration.hcp_current_overlay_adapter import (
    SqlAlchemyCurrentOverlayRepository,
)
from app.operational_migration.hcp_current_overlay_native import (
    HcpCurrentOverlayNativeServices,
)
from app.operational_migration.hcp_migration2_command import resolve_rehearsal_context
from app.operational_migration.models import (
    HcpMigrationMasterRun,
    OperationalMigrationRun,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import MigrationPermission

COMMAND_CONTRACT = "hcp-current-overlay-native-execution/v1"
RESTORE_RECEIPT_CONTRACT = "preview-isolated-restore-receipt/v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_digest(value: str) -> bool:
    return len(value) == 64 and value == value.lower() and all(
        char in "0123456789abcdef" for char in value
    )


@dataclass(frozen=True)
class CurrentOverlayExecutionAuthority:
    expected_repository_sha: str
    expected_schema_head: str
    expected_database: str
    company_id: UUID
    branch_id: UUID
    actor_id: UUID
    master_run_id: UUID
    customer_run_id: UUID
    operational_run_id: UUID
    overlay_path: Path
    overlay_file_digest: str
    overlay_manifest_digest: str
    hold_path: Path
    hold_digest: str
    classification_path: Path
    classification_digest: str
    classification_result_digest: str
    expected_base_source4_digest: str
    backup_path: Path
    backup_digest: str
    restore_receipt_path: Path
    restore_receipt_digest: str
    idempotency_identity: str
    zero_migration_drift: bool
    expected_classification_admission_allowed: bool
    current_operational_admission_allowed: bool

    @classmethod
    def load(cls, path: Path) -> CurrentOverlayExecutionAuthority:
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise ValueError("overlay authority file permissions must be 0600")
        value = json.loads(path.read_bytes())
        if value.pop("contract", None) != COMMAND_CONTRACT:
            raise ValueError("overlay execution authority contract mismatch")
        for key in (
            "company_id",
            "branch_id",
            "actor_id",
            "master_run_id",
            "customer_run_id",
            "operational_run_id",
        ):
            value[key] = UUID(value[key])
        for key in (
            "overlay_path",
            "hold_path",
            "classification_path",
            "backup_path",
            "restore_receipt_path",
        ):
            value[key] = Path(value[key])
        return cls(**value)

    def verify_artifacts(self) -> CurrentOverlayManifest:
        expected = {
            self.overlay_path: self.overlay_file_digest,
            self.hold_path: self.hold_digest,
            self.classification_path: self.classification_digest,
            self.backup_path: self.backup_digest,
            self.restore_receipt_path: self.restore_receipt_digest,
        }
        if any(not _is_digest(digest) for digest in expected.values()):
            raise ValueError("overlay authority contains an invalid digest")
        for path, digest in expected.items():
            if not path.is_file() or _sha256(path) != digest:
                raise ValueError(f"overlay authority artifact mismatch: {path.name}")
        manifest = CurrentOverlayManifest.load(self.overlay_path)
        if (
            manifest.digest != self.overlay_manifest_digest
            or manifest.base_source4_digest != self.expected_base_source4_digest
            or manifest.company_id != str(self.company_id)
            or manifest.branch_id != str(self.branch_id)
        ):
            raise ValueError("overlay manifest authority mismatch")
        restore = json.loads(self.restore_receipt_path.read_bytes())
        if (
            restore.get("contract") != RESTORE_RECEIPT_CONTRACT
            or restore.get("backup_digest") != self.backup_digest
            or restore.get("restore_verified") is not True
            or restore.get("schema_head") != self.expected_schema_head
        ):
            raise ValueError("isolated restore receipt is not qualified")
        classification = json.loads(self.classification_path.read_bytes())
        report = classification.get("report")
        if (
            classification.get("digest") != self.classification_result_digest
            or not isinstance(report, dict)
            or report.get("canonical_admission_allowed")
            is not self.expected_classification_admission_allowed
        ):
            raise ValueError("overlay canonical classification result mismatch")
        if not self.zero_migration_drift or not self.current_operational_admission_allowed:
            raise ValueError("overlay operational or migration-drift gate failed")
        expected_idempotency = hashlib.sha256(
            json.dumps(
                {
                    "contract": COMMAND_CONTRACT,
                    "manifest_digest": manifest.digest,
                    "backup_digest": self.backup_digest,
                    "company_id": str(self.company_id),
                    "branch_id": str(self.branch_id),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if self.idempotency_identity != expected_idempotency:
            raise ValueError("overlay idempotency identity mismatch")
        return manifest


async def execute_current_overlay(
    authority: CurrentOverlayExecutionAuthority,
    *,
    context: AuthorizationContext,
    factory: async_sessionmaker[AsyncSession],
) -> OverlayExecutionReceipt:
    """Validate all guards, then apply one packet in its migration-owned transaction."""
    manifest = authority.verify_artifacts()
    repository_sha = subprocess.run(  # noqa: ASYNC221
        ("git", "rev-parse", "HEAD"), check=True, capture_output=True, text=True
    ).stdout.strip()
    if repository_sha != authority.expected_repository_sha:
        raise ValueError("overlay protected authority mismatch")
    if (
        os.getenv("TARGET_ENVIRONMENT") != "preview"
        or os.getenv("PRODUCTION_ACCESS_ENABLED", "false") != "false"
        or os.getenv("PREVIEW_ACCESS_ENABLED", "false") != "true"
    ):
        raise ValueError("overlay requires the sanctioned Preview boundary")
    if urlparse(settings.database_url).path.removeprefix("/") != authority.expected_database:
        raise ValueError("overlay Preview database authority mismatch")
    if (
        context.company.id != authority.company_id
        or context.active_branch is None
        or context.active_branch.id != authority.branch_id
        or not context.can_access_branch(authority.branch_id)
        or not context.has_permission(MigrationPermission.EXECUTE_REHEARSAL)
    ):
        raise ValueError("overlay Company, Branch, or migration permission mismatch")

    async with factory() as session:
        schemas = tuple(
            (await session.scalars(text("SELECT version_num FROM alembic_version"))).all()
        )
        if schemas != (authority.expected_schema_head,):
            raise ValueError("overlay schema is not current at exactly one head")
        master = await session.get(HcpMigrationMasterRun, authority.master_run_id)
        customer_run = await session.get(CustomerMigrationRun, authority.customer_run_id)
        operational_run = await session.get(
            OperationalMigrationRun, authority.operational_run_id
        )
        if (
            master is None
            or master.status != "completed"
            or master.company_id != authority.company_id
            or master.branch_id != authority.branch_id
            or master.package_digest != authority.expected_base_source4_digest
            or customer_run is None
            or customer_run.master_run_id != master.id
            or operational_run is None
            or operational_run.master_run_id != master.id
        ):
            raise ValueError("overlay SOURCE.4 run lineage mismatch")
        master_id = master.id
        customer_run_id = customer_run.id
        operational_run_id = operational_run.id
        package_digest = master.package_digest
        await session.rollback()

        services = HcpCurrentOverlayNativeServices(
            context=context,
            master_run_id=master_id,
            customer_run_id=customer_run_id,
            operational_run_id=operational_run_id,
            package_digest=package_digest,
            base_source_digests={
                record.key: record.prior_source_digest or record.source_digest
                for record in manifest.records
            },
        )
        repository = SqlAlchemyCurrentOverlayRepository(
            session,
            master_run_id=master_id,
            services=services,
            advisory_lock_identity=f"hcp-current-overlay:{authority.company_id}",
            execution_context={
                "authority_sha": repository_sha,
                "schema_head": authority.expected_schema_head,
                "backup_digest": authority.backup_digest,
                "overlay_digest": manifest.digest,
                "hold_digest": authority.hold_digest,
                "classification_digest": authority.classification_digest,
                "company_id": str(authority.company_id),
                "branch_id": str(authority.branch_id),
                "counts_attempted": len(manifest.records),
                "source_identities": [
                    f"{record.domain}:{record.source_id}"
                    for record in manifest.records
                ],
                "execution_timestamp": manifest.acquired_at,
                "idempotency_identity": authority.idempotency_identity,
                "state": "success",
            },
        )
        return await CurrentOverlayExecutor().execute(
            repository,
            manifest=manifest,
            expected_base_source4_digest=authority.expected_base_source4_digest,
            rollback_backup_digest=authority.backup_digest,
        )


async def run_authority_file(path: Path) -> OverlayExecutionReceipt:
    authority = CurrentOverlayExecutionAuthority.load(path)
    async with AsyncSessionFactory() as session:
        context = await resolve_rehearsal_context(
            session, authority, credentialed=True  # type: ignore[arg-type]
        )
        await session.rollback()
    return await execute_current_overlay(
        authority, context=context, factory=AsyncSessionFactory
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority-file", required=True, type=Path)
    parser.add_argument("--authorize-preview-execution", action="store_true")
    args = parser.parse_args(argv)
    if not args.authorize_preview_execution:
        raise SystemExit("explicit Preview overlay execution authorization is required")
    receipt = asyncio.run(run_authority_file(args.authority_file))
    print(json.dumps({"receipt": receipt.digest, "counts": receipt.counts}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
