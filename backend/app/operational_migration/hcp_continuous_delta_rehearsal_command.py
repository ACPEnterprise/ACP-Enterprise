"""Guarded isolated-clone execution for a sealed HCP continuous delta."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select, text

from app.core.config import settings
from app.customer_migration.models import CustomerMigrationRun
from app.database.session import AsyncSessionFactory, engine
from app.operational_migration.hcp_current_overlay import (
    CurrentOverlayExecutor,
    CurrentOverlayManifest,
)
from app.operational_migration.hcp_current_overlay_adapter import (
    STATE_KEY,
    SqlAlchemyCurrentOverlayRepository,
)
from app.operational_migration.hcp_current_overlay_lineage import MASTER_STATUS
from app.operational_migration.hcp_current_overlay_native import (
    HcpCurrentOverlayNativeServices,
)
from app.operational_migration.hcp_migration2_command import resolve_rehearsal_context
from app.operational_migration.hcp_operational_gate import (
    canonical_digest,
    file_sha256,
    load_object,
    require_private_file,
    verify_document_digest,
)
from app.operational_migration.models import (
    HcpMigrationMasterRun,
    OperationalMigrationRun,
)
from app.platform.permissions.codes import MigrationPermission

CONTRACT = "hcp-isolated-clone-continuous-delta-execution/v1"
RESTORE_CONTRACT = "hcp-isolated-clone-restore-receipt/v1"
EXPECTED_DATABASE = "acp_hcp_rehearsal_import"


@dataclass(frozen=True)
class CloneDeltaAuthority:
    expected_repository_sha: str
    expected_schema_head: str
    expected_database: str
    company_id: UUID
    branch_id: UUID
    actor_id: UUID
    base_source4_digest: str
    overlay_path: Path
    overlay_file_sha256: str
    overlay_manifest_digest: str
    gate_validation_path: Path
    gate_validation_digest: str
    native_observations_path: Path
    native_observations_digest: str
    final_policy_path: Path
    final_policy_digest: str
    rehearsal_manifest_path: Path
    rehearsal_manifest_digest: str
    backup_path: Path
    backup_digest: str
    restore_receipt_path: Path
    restore_receipt_digest: str
    idempotency_identity: str

    @classmethod
    def load(cls, path: Path) -> CloneDeltaAuthority:
        require_private_file(path)
        value = load_object(path)
        if value.pop("contract", None) != CONTRACT:
            raise ValueError("continuous-delta clone authority contract mismatch")
        for key in ("company_id", "branch_id", "actor_id"):
            value[key] = UUID(value[key])
        for key in (
            "overlay_path",
            "gate_validation_path",
            "native_observations_path",
            "final_policy_path",
            "rehearsal_manifest_path",
            "backup_path",
            "restore_receipt_path",
        ):
            value[key] = Path(value[key])
        authority = cls(**value)
        authority.verify()
        return authority

    def verify(self) -> CurrentOverlayManifest:
        if (
            self.expected_database != EXPECTED_DATABASE
            or len(self.expected_repository_sha) != 40
            or not self.expected_schema_head
        ):
            raise ValueError("continuous-delta clone authority boundary mismatch")
        expected_files = {
            self.overlay_path: self.overlay_file_sha256,
            self.backup_path: self.backup_digest,
            self.restore_receipt_path: self.restore_receipt_digest,
        }
        for path, digest in expected_files.items():
            require_private_file(path)
            if file_sha256(path) != digest:
                raise ValueError(f"clone authority file digest mismatch: {path.name}")
        for path in (
            self.gate_validation_path,
            self.native_observations_path,
            self.final_policy_path,
            self.rehearsal_manifest_path,
        ):
            require_private_file(path)

        gate = load_object(self.gate_validation_path)
        rehearsal = load_object(self.rehearsal_manifest_path)
        native = load_object(self.native_observations_path)
        final_policy = load_object(self.final_policy_path)
        if (
            verify_document_digest(gate, "gate validation")
            != self.gate_validation_digest
        ):
            raise ValueError("gate validation authority mismatch")
        if (
            verify_document_digest(rehearsal, "rehearsal manifest")
            != self.rehearsal_manifest_digest
        ):
            raise ValueError("rehearsal manifest authority mismatch")
        native_digest = (
            verify_document_digest(native, "native observations")
            if native.get("digest")
            else canonical_digest(native)
        )
        if native_digest != self.native_observations_digest:
            raise ValueError("native observation authority mismatch")
        if (
            verify_document_digest(final_policy, "final operational policy")
            != self.final_policy_digest
        ):
            raise ValueError("final operational policy authority mismatch")

        overlay = CurrentOverlayManifest.load(self.overlay_path)
        if (
            overlay.digest != self.overlay_manifest_digest
            or overlay.base_source4_digest != self.base_source4_digest
            or overlay.company_id != str(self.company_id)
            or overlay.branch_id != str(self.branch_id)
            or rehearsal.get("overlay_manifest_digest") != overlay.digest
            or rehearsal.get("native_observations_digest") != native_digest
            or rehearsal.get("final_policy_digest") != self.final_policy_digest
            or rehearsal.get("gate_digest") != gate.get("gate_digest")
            or final_policy.get("source_gate_digest") != gate.get("gate_digest")
        ):
            raise ValueError("continuous-delta clone artifact lineage mismatch")
        restore = load_object(self.restore_receipt_path)
        if (
            restore.get("contract") != RESTORE_CONTRACT
            or restore.get("restore_verified") is not True
            or restore.get("backup_digest") != self.backup_digest
            or restore.get("database") != self.expected_database
            or restore.get("schema_head") != self.expected_schema_head
        ):
            raise ValueError("isolated-clone restore receipt is not qualified")
        expected_idempotency = canonical_digest(
            {
                "contract": CONTRACT,
                "overlay": overlay.digest,
                "backup": self.backup_digest,
                "company": str(self.company_id),
                "branch": str(self.branch_id),
            }
        )
        if self.idempotency_identity != expected_idempotency:
            raise ValueError("continuous-delta idempotency identity mismatch")
        return overlay


def _runtime_guard(authority: CloneDeltaAuthority) -> None:
    parsed = urlparse(settings.database_url)
    repository_sha = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if (
        repository_sha != authority.expected_repository_sha
        or os.getenv("TARGET_ENVIRONMENT") != "migration_rehearsal"
        or os.getenv("PREVIEW_ACCESS_ENABLED", "true").lower() != "false"
        or os.getenv("PRODUCTION_ACCESS_ENABLED", "true").lower() != "false"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.path.removeprefix("/") != EXPECTED_DATABASE
    ):
        raise ValueError("isolated-clone runtime boundary mismatch")


async def _lineage(
    authority: CloneDeltaAuthority,
) -> tuple[UUID, UUID, UUID, dict[str, Any]]:
    async with AsyncSessionFactory() as session:
        masters = tuple(
            (
                await session.scalars(
                    select(HcpMigrationMasterRun).where(
                        HcpMigrationMasterRun.company_id == authority.company_id,
                        HcpMigrationMasterRun.branch_id == authority.branch_id,
                        HcpMigrationMasterRun.package_digest
                        == authority.base_source4_digest,
                        HcpMigrationMasterRun.status.in_(("completed", MASTER_STATUS)),
                    )
                )
            ).all()
        )
        if len(masters) != 1:
            raise ValueError(
                "isolated clone must contain exactly one admitted SOURCE.4 master"
            )
        master = masters[0]
        customer = await session.scalar(
            select(CustomerMigrationRun).where(
                CustomerMigrationRun.master_run_id == master.id
            )
        )
        operational = await session.scalar(
            select(OperationalMigrationRun).where(
                OperationalMigrationRun.master_run_id == master.id,
                OperationalMigrationRun.master_domain == "operational",
                OperationalMigrationRun.repair_generation == 0,
            )
        )
        if customer is None or operational is None:
            raise ValueError("isolated clone SOURCE.4 child lineage is incomplete")
        result = (
            master.id,
            customer.id,
            operational.id,
            dict(master.replay_state),
        )
        await session.rollback()
        return result


async def run(
    *, authority_path: Path, mode: str, authorize_execution: bool
) -> dict[str, Any]:
    authority = CloneDeltaAuthority.load(authority_path)
    overlay = authority.verify()
    _runtime_guard(authority)
    async with AsyncSessionFactory() as session:
        context = await resolve_rehearsal_context(session, authority, credentialed=True)
        heads = tuple(
            (
                await session.scalars(text("SELECT version_num FROM alembic_version"))
            ).all()
        )
        await session.rollback()
    if (
        heads != (authority.expected_schema_head,)
        or context.company.id != authority.company_id
        or context.active_branch is None
        or context.active_branch.id != authority.branch_id
        or not context.has_permission(MigrationPermission.EXECUTE_REHEARSAL)
    ):
        raise ValueError("isolated clone schema/scope authority mismatch")
    master_id, customer_id, operational_id, master_replay_state = await _lineage(
        authority
    )
    replay_state = master_replay_state.get(STATE_KEY)
    receipts = replay_state.get("receipts") if isinstance(replay_state, dict) else None
    has_receipt = isinstance(receipts, dict) and overlay.digest in receipts
    if mode == "execute" and has_receipt:
        raise ValueError("execute mode rejects an already-receipted overlay")
    if mode == "replay" and not has_receipt:
        raise ValueError("replay mode requires the prior durable receipt")
    services = HcpCurrentOverlayNativeServices(
        context=context,
        master_run_id=master_id,
        customer_run_id=customer_id,
        operational_run_id=operational_id,
        package_digest=authority.base_source4_digest,
        base_source_digests={
            record.key: record.prior_source_digest or record.source_digest
            for record in overlay.records
        },
    )
    services.bind_lineage(
        master_run_id=master_id,
        customer_run_id=customer_id,
        operational_run_id=operational_id,
    )
    async with AsyncSessionFactory() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        inventory = await services.prepare_update_bindings(session, overlay.records)
        await session.rollback()
    if mode == "qualify":
        return {
            "contract": CONTRACT,
            "mode": mode,
            "status": "QUALIFIED",
            "overlay_manifest_digest": overlay.digest,
            "record_count": len(overlay.records),
            "update_binding_inventory": inventory,
            "mutation_count": 0,
        }
    if not authorize_execution:
        raise ValueError("explicit isolated-clone execution authorization is required")
    async with AsyncSessionFactory() as session:
        repository = SqlAlchemyCurrentOverlayRepository(
            session,
            master_run_id=master_id,
            services=services,
            advisory_lock_identity=f"hcp-continuous-delta:{authority.company_id}",
            overlay_records=overlay.records,
            execution_context={
                "authority_contract": CONTRACT,
                "gate_validation_digest": authority.gate_validation_digest,
                "native_observations_digest": authority.native_observations_digest,
                "final_policy_digest": authority.final_policy_digest,
                "rehearsal_manifest_digest": authority.rehearsal_manifest_digest,
                "idempotency_identity": authority.idempotency_identity,
                "mode": mode,
            },
        )
        receipt = await CurrentOverlayExecutor().execute(
            repository,
            manifest=overlay,
            expected_base_source4_digest=authority.base_source4_digest,
            rollback_backup_digest=authority.backup_digest,
            require_non_mutating_parents=False,
        )
    return {
        "contract": CONTRACT,
        "mode": mode,
        "status": "EXECUTED" if mode == "execute" else "REPLAYED",
        "receipt": receipt.digest,
        "manifest_digest": receipt.manifest_digest,
        "counts": receipt.counts,
        "journal_count": len(receipt.journal),
        "idempotency_identity": authority.idempotency_identity,
        "receipt_payload": asdict(receipt),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("mode", choices=("qualify", "execute", "replay"))
    result.add_argument("--authority-file", required=True, type=Path)
    result.add_argument("--authorize-execution", action="store_true")
    return result


async def _main() -> int:
    try:
        args = parser().parse_args()
        value = await run(
            authority_path=args.authority_file,
            mode=args.mode,
            authorize_execution=args.authorize_execution,
        )
        print(json.dumps(value, sort_keys=True))
        return 0
    finally:
        await engine.dispose()


def main() -> None:
    try:
        code = asyncio.run(_main())
    except Exception:  # noqa: BLE001 - never emit protected evidence in CLI errors
        print(
            '{"status":"rejected","code":"isolated_clone_delta_rehearsal_failed"}',
            file=sys.stderr,
        )
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
