"""Guarded Preview-only execution of the explicit HCP v4 successor overlay."""

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

from app.core.config import settings
from app.database.session import AsyncSessionFactory
from app.operational_migration.hcp_current_overlay import CurrentOverlayExecutor
from app.operational_migration.hcp_current_overlay_adapter import (
    SqlAlchemyCurrentOverlayRepository,
)
from app.operational_migration.hcp_current_overlay_lineage import (
    CurrentOverlayLineageBinding,
    CurrentOverlayLineageBootstrap,
)
from app.operational_migration.hcp_current_overlay_native import (
    HcpCurrentOverlayNativeServices,
)
from app.operational_migration.hcp_current_overlay_v4 import (
    AUTHORITY_CONTRACT,
    V4ExecutableOverlay,
    preflight_v4,
    sha256,
)
from app.operational_migration.hcp_migration2_command import resolve_rehearsal_context
from app.platform.permissions.codes import MigrationPermission

EXECUTOR_VERSION = "migration.hcp.current.overlay.v4.executor.1"


@dataclass(frozen=True)
class V4ExecutionAuthority:
    protected_sha: str
    deployed_sha: str
    schema_head: str
    expected_database: str
    company_id: UUID
    branch_id: UUID
    actor_id: UUID
    overlay_path: Path
    overlay_file_sha256: str
    overlay_semantic_digest: str
    complete_current_graph_digest: str
    source4_package_path: Path
    source4_package_file_sha256: str
    source4_package_digest: str
    v3_predecessor_path: Path
    v3_predecessor_file_sha256: str
    v3_predecessor_digest: str
    original_overlay_path: Path
    original_overlay_file_sha256: str
    original_overlay_digest: str
    hold_packet_path: Path
    hold_packet_digest: str
    update_cohort_path: Path
    update_cohort_file_sha256: str
    update_cohort_digest: str
    runtime_inventory_path: Path
    runtime_inventory_digest: str
    preview_baseline_path: Path
    preview_baseline_sha256: str
    preview_baseline_semantic_digest: str
    backup_path: Path
    backup_digest: str
    restore_receipt_path: Path
    restore_receipt_digest: str
    idempotency_identity: str
    executor_version: str

    @classmethod
    def load(cls, path: Path) -> V4ExecutionAuthority:
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise ValueError("v4 execution authority permissions must be 0600")
        value = json.loads(path.read_bytes())
        if value.pop("contract", None) != AUTHORITY_CONTRACT:
            raise ValueError("v4 execution authority contract mismatch")
        for key in ("company_id", "branch_id", "actor_id"):
            value[key] = UUID(value[key])
        for key in (
            "overlay_path",
            "source4_package_path",
            "v3_predecessor_path",
            "original_overlay_path",
            "hold_packet_path",
            "update_cohort_path",
            "runtime_inventory_path",
            "preview_baseline_path",
            "backup_path",
            "restore_receipt_path",
        ):
            value[key] = Path(value[key])
        return cls(**value)

    def verify(self) -> V4ExecutableOverlay:
        failures: list[str] = []
        if (
            self.executor_version != EXECUTOR_VERSION
            or self.protected_sha != self.deployed_sha
        ):
            failures.append("v4_executor_or_deployed_authority_mismatch")
        for path, digest in (
            (self.overlay_path, self.overlay_file_sha256),
            (self.source4_package_path, self.source4_package_file_sha256),
            (self.v3_predecessor_path, self.v3_predecessor_file_sha256),
            (self.original_overlay_path, self.original_overlay_file_sha256),
            (self.hold_packet_path, self.hold_packet_digest),
            (self.update_cohort_path, self.update_cohort_file_sha256),
            (self.runtime_inventory_path, self.runtime_inventory_digest),
            (self.preview_baseline_path, self.preview_baseline_sha256),
            (self.backup_path, self.backup_digest),
            (self.restore_receipt_path, self.restore_receipt_digest),
        ):
            if not path.is_file() or sha256(path) != digest:
                failures.append(f"artifact_digest_mismatch:{path.name}")
                continue
            if stat.S_IMODE(path.stat().st_mode) & 0o077:
                failures.append(f"artifact_permissions_mismatch:{path.name}")
            if stat.S_IMODE(path.parent.stat().st_mode) & 0o077:
                failures.append(
                    f"artifact_directory_permissions_mismatch:{path.parent}"
                )
        if failures:
            raise ValueError(_failure_report(failures))
        overlay = V4ExecutableOverlay.load(self.overlay_path)
        raw_overlay = json.loads(self.overlay_path.read_bytes())
        if (
            overlay.semantic_digest != self.overlay_semantic_digest
            or overlay.complete_current_graph_digest
            != self.complete_current_graph_digest
            or overlay.base_source4_digest != self.source4_package_digest
            or overlay.company_id != self.company_id
            or overlay.branch_id != self.branch_id
        ):
            failures.append("v4_overlay_authority_binding_mismatch")
        lineage_bindings = {
            "v3_predecessor_digest": self.v3_predecessor_digest,
            "v3_predecessor_file_sha256": self.v3_predecessor_file_sha256,
            "original_overlay_manifest_digest": self.original_overlay_digest,
            "hold_packet_sha256": self.hold_packet_digest,
            "update_cohort_authority_digest": self.update_cohort_digest,
            "runtime_inventory_sha256": self.runtime_inventory_digest,
            "preview_baseline_sha256": self.preview_baseline_sha256,
            "preview_baseline_semantic_digest": self.preview_baseline_semantic_digest,
        }
        if any(
            raw_overlay.get(key) != expected
            for key, expected in lineage_bindings.items()
        ):
            failures.append("v4_predecessor_or_baseline_binding_mismatch")
        receipt = json.loads(self.restore_receipt_path.read_bytes())
        if (
            receipt.get("backup_digest") != self.backup_digest
            or receipt.get("restore_verified") is not True
            or receipt.get("schema_head") != self.schema_head
        ):
            failures.append("isolated_restore_receipt_not_qualified")
        expected = hashlib.sha256(
            json.dumps(
                {
                    "contract": AUTHORITY_CONTRACT,
                    "overlay": overlay.semantic_digest,
                    "backup": self.backup_digest,
                    "company": str(self.company_id),
                    "branch": str(self.branch_id),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if self.idempotency_identity != expected:
            failures.append("v4_idempotency_identity_mismatch")
        if failures:
            raise ValueError(_failure_report(failures))
        return overlay


def _failure_report(failures: list[str]) -> str:
    return json.dumps(
        {
            "contract": "hcp-current-overlay-v4-authority-preflight/v1",
            "failures": failures,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


async def run_authority_file(path: Path):
    authority = V4ExecutionAuthority.load(path)
    overlay = authority.verify()
    repository_sha = subprocess.run(  # noqa: ASYNC221
        ("git", "rev-parse", "HEAD"), check=True, capture_output=True, text=True
    ).stdout.strip()
    if (
        repository_sha != authority.protected_sha
        or os.getenv("TARGET_ENVIRONMENT") != "preview"
        or os.getenv("PREVIEW_ACCESS_ENABLED") != "true"
        or os.getenv("PRODUCTION_ACCESS_ENABLED", "false") != "false"
    ):
        raise ValueError("v4 protected Preview boundary mismatch")
    if (
        urlparse(settings.database_url).path.removeprefix("/")
        != authority.expected_database
    ):
        raise ValueError("v4 Preview database mismatch")
    async with AsyncSessionFactory() as session:
        context = await resolve_rehearsal_context(session, authority, credentialed=True)  # type: ignore[arg-type]
        await session.rollback()
        if (
            context.company.id != authority.company_id
            or context.active_branch is None
            or context.active_branch.id != authority.branch_id
            or not context.has_permission(MigrationPermission.EXECUTE_REHEARSAL)
        ):
            raise ValueError("v4 scope or execution permission mismatch")
        schemas = tuple(
            (
                await session.scalars(text("SELECT version_num FROM alembic_version"))
            ).all()
        )
        if schemas != (authority.schema_head,):
            raise ValueError("v4 schema is not current at one head")
        await session.rollback()
        services = HcpCurrentOverlayNativeServices(
            context=context,
            master_run_id=UUID(int=0),
            customer_run_id=UUID(int=0),
            operational_run_id=UUID(int=0),
            package_digest=authority.source4_package_digest,
            base_source_digests={
                record.key: (
                    record.source_digest
                    if overlay.successor_assertions[record.key] == "REUSE_EXISTING"
                    else record.prior_source_digest or record.source_digest
                )
                for record in overlay.manifest.records
            },
            qualified_targets=overlay.qualified_targets,
        )
        await session.execute(text("SET TRANSACTION READ ONLY"))
        report = await preflight_v4(session, overlay=overlay, services=services)
        await session.rollback()
        binding = CurrentOverlayLineageBinding(
            company_id=authority.company_id,
            branch_id=authority.branch_id,
            actor_id=authority.actor_id,
            source4_package_identity="hcp-source4-current-graph-v4",
            base_source4_digest=authority.source4_package_digest,
            overlay_manifest_digest=overlay.semantic_digest,
            overlay_file_digest=authority.overlay_file_sha256,
            hold_digest=authority.hold_packet_digest,
            canonical_hold_count=1389,
            authority_sha=repository_sha,
            schema_head=authority.schema_head,
        )
        services.master_run_id = binding.master_run_id
        bootstrap = CurrentOverlayLineageBootstrap(binding, overlay.manifest)
        repository = SqlAlchemyCurrentOverlayRepository(
            session,
            master_run_id=binding.master_run_id,
            services=services,
            lineage_bootstrap=bootstrap,
            overlay_records=overlay.manifest.records,
            advisory_lock_identity=f"hcp-current-overlay:{authority.company_id}",
            execution_context={
                "authority_contract": AUTHORITY_CONTRACT,
                "executor_version": EXECUTOR_VERSION,
                "v4_digest": overlay.semantic_digest,
                "v4_file_sha256": overlay.file_digest,
                "complete_current_graph_digest": overlay.complete_current_graph_digest,
                "predecessor_overlay_digest": authority.v3_predecessor_digest,
                "original_overlay_digest": authority.original_overlay_digest,
                "hold_packet_digest": authority.hold_packet_digest,
                "update_cohort_digest": authority.update_cohort_digest,
                "runtime_inventory_digest": authority.runtime_inventory_digest,
                "preview_baseline_sha256": authority.preview_baseline_sha256,
                "preview_baseline_semantic_digest": (
                    authority.preview_baseline_semantic_digest
                ),
                "record_count": 522,
                "current_graph": [
                    f"{key.domain}:{key.source_id}"
                    for key in sorted(overlay.current_keys)
                ],
                "records": overlay.execution_evidence,
                "preflight": report,
                "idempotency_identity": authority.idempotency_identity,
            },
        )
        return await CurrentOverlayExecutor().execute(
            repository,
            manifest=overlay.manifest,
            expected_base_source4_digest=authority.source4_package_digest,
            rollback_backup_digest=authority.backup_digest,
            require_non_mutating_parents=False,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority-file", required=True, type=Path)
    parser.add_argument("--authorize-preview-execution", action="store_true")
    args = parser.parse_args()
    if not args.authorize_preview_execution:
        raise SystemExit("explicit v4 Preview execution authorization is required")
    receipt = asyncio.run(run_authority_file(args.authority_file))
    print(json.dumps({"receipt": receipt.digest, "counts": receipt.counts}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
