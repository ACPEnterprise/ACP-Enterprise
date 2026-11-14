"""Checkpointed SOURCE.4 admission into the sanctioned empty Preview scope."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import stat
import subprocess
from collections import Counter
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
from app.operational_migration.hcp_november_bundle import (
    AUTHORITY_CONTRACT as NOVEMBER_AUTHORITY_CONTRACT,
    NovemberQualificationAuthority,
    qualification_digest,
)
from app.operational_migration.hcp_november_executor import (
    NovemberBoundedExecutor,
    NovemberExecutionEnvelope,
    _packet_inventory,
    run_november_execution,
    validate_supplemental_current_state_authority,
    validate_runtime_boundary,
)
from app.operational_migration.hcp_discrepancy_quarantine import (
    CONTRACT as DISCREPANCY_AUTHORITY_CONTRACT,
    DiscrepancyQuarantineAuthority,
)
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
from app.platform.permissions.codes import MigrationPermission
from app.operational_migration.hcp_successor_reuse import (
    AdmissionGuardEvidence,
    QualifiedSuccessorManifest,
    qualify_reuse_graph,
    qualify_successor_admission,
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
    successor_manifest_path: Path | None = None
    successor_manifest_digest: str | None = None
    customer_control_sha256: str | None = None
    zero_migration_drift: bool = False
    rollback_verified: bool = False
    security_baseline_verified: bool = False

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
                    "successor_manifest_path": (
                        Path(value["successor_manifest_path"])
                        if value.get("successor_manifest_path")
                        else None
                    ),
                    "successor_manifest_digest": value.get("successor_manifest_digest"),
                    "customer_control_sha256": value.get("customer_control_sha256"),
                    "zero_migration_drift": value.get("zero_migration_drift", False),
                    "rollback_verified": value.get("rollback_verified", False),
                    "security_baseline_verified": value.get(
                        "security_baseline_verified", False
                    ),
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
            self.successor_manifest_path is None
            and self.public_reconciliation_digest != PUBLIC_DIGEST
        ):
            raise SafeEvidenceError(
                "preview_reconciliation_authority_mismatch", "0" * 64
            )
        if (
            not self.backup_path.is_file()
            or _sha256(self.backup_path) != self.backup_sha256
        ):
            raise SafeEvidenceError("preview_backup_authority_mismatch", "0" * 64)
        if self.successor_manifest_path is None:
            manifest = json.loads(self.private_manifest_path.read_bytes())
            if (
                self.private_manifest_digest != EMPTY_MANIFEST_DIGEST
                or manifest.get("digest") != EMPTY_MANIFEST_DIGEST
                or manifest.get("entries") != []
            ):
                raise SafeEvidenceError("preview_manifest_not_empty", "0" * 64)
            return
        if (
            self.customer_control_sha256 is None
            or _sha256(self.control_csv) != self.customer_control_sha256
            or not self.successor_manifest_path.is_file()
            or stat.S_IMODE(self.successor_manifest_path.stat().st_mode) != 0o600
        ):
            raise SafeEvidenceError("successor_artifact_authority_mismatch", "0" * 64)
        successor = QualifiedSuccessorManifest.load(self.successor_manifest_path)
        if successor.digest != self.successor_manifest_digest:
            raise SafeEvidenceError("successor_manifest_authority_mismatch", "0" * 64)


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
        or os.getenv("PREVIEW_ACCESS_ENABLED", "false") != "true"
    ):
        raise SafeEvidenceError("preview_runtime_boundary_invalid", "0" * 64)
    async with factory() as session:
        schemas = tuple(
            (
                await session.scalars(text("SELECT version_num FROM alembic_version"))
            ).all()
        )
        schema = schemas[0] if len(schemas) == 1 else None
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
    successor_manifest = (
        QualifiedSuccessorManifest.load(authority.successor_manifest_path)
        if authority.successor_manifest_path is not None
        else None
    )
    if successor_manifest is None and any(scoped.values()):
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
    plan, summary = builder.build(
        baseline_counts=scoped,
        company_id=authority.company_id,
        branch_id=authority.branch_id,
        actor_id=authority.actor_id,
    )
    preflight = None
    if successor_manifest is not None:
        preflight = qualify_successor_admission(
            successor_manifest,
            AdmissionGuardEvidence(
                hybrid_digest=plan.customers.admission.digest,
                customer_control_digest=_sha256(authority.control_csv),
                protected_authority=repository_sha,
                expected_protected_authority=authority.expected_repository_sha,
                schema_current=str(schema or ""),
                schema_head=authority.expected_schema_head,
                backup_verified=True,
                authorization_verified=True,
                zero_prior_master_admissions=(
                    scoped[HcpMigrationMasterRun.__tablename__] == 0
                ),
                zero_migration_drift=authority.zero_migration_drift,
                rollback_verified=authority.rollback_verified,
                security_baseline_verified=authority.security_baseline_verified,
            ),
        )
        if not preflight.admission_allowed:
            raise SafeEvidenceError(
                "successor_admission_preflight_rejected", preflight.digest
            )
        async with factory() as graph_session:
            await graph_session.execute(text("SET TRANSACTION READ ONLY"))
            await qualify_reuse_graph(
                graph_session,
                company_id=str(authority.company_id),
                branch_id=str(authority.branch_id),
                plan=plan,
                manifest=successor_manifest,
            )
            await graph_session.rollback()
    packet: dict[str, object] = {
        "command": COMMAND_VERSION,
        "mode": "execute" if execute else "qualify",
        "plan_digest": summary.plan_digest,
        "schema_head": authority.expected_schema_head,
        "checkpointed": True,
        "atomic": False,
        "rollback": "full_database_restore",
        "backup_sha256": authority.backup_sha256,
        "successor_preflight": (
            {
                "digest": preflight.digest,
                "manifest_digest": preflight.manifest_digest,
                "domain_counts": {
                    key: value.__dict__
                    for key, value in preflight.domain_counts.items()
                },
                "existing_preview_overlap_count": preflight.existing_preview_overlap_count,
                "duplicate_risk_count": preflight.duplicate_risk_count,
                "orphan_risk_count": preflight.orphan_risk_count,
                "financial_overlap_count": preflight.financial_overlap_count,
                "unresolved_owner_decision_count": preflight.unresolved_owner_decision_count,
            }
            if preflight is not None
            else None
        ),
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
        successor_manifest=successor_manifest,
    )
    return {**packet, "result": result}


async def run_november_bundle(
    authority: NovemberQualificationAuthority,
    *,
    execute: bool,
) -> dict[str, object]:
    """Qualify or execute the bounded November Preview handoff."""
    if execute:
        return await run_november_execution(authority, factory=AsyncSessionFactory)
    validate_runtime_boundary(
        os.getenv("TARGET_ENVIRONMENT", ""),
        os.getenv("PRODUCTION_ACCESS_ENABLED", "false").lower() == "true",
        os.getenv("PREVIEW_ACCESS_ENABLED", "false").lower() == "true",
        {
            name: os.getenv(name, "false")
            for name in (
                "HCP_PROVIDER_WRITE_ENABLED",
                "HCP_LIVE_ACCESS_ENABLED",
                "QBO_PRODUCTION_ENABLED",
                "PAYROLL_EXECUTION_ENABLED",
            )
        },
    )
    packet = authority.verify()
    packet["qualification_status"] = "PASS"
    packet["qualification_digest"] = qualification_digest(authority.verify())
    target = PreviewAdmissionTarget(
        "preview", settings.database_url, "acp_enterprise_preview"
    )
    try:
        packet["target_digest"] = target.validate()
    except ValueError as error:
        raise SafeEvidenceError("preview_database_target_invalid", "0" * 64) from error
    async with AsyncSessionFactory() as session:
        schemas = tuple(
            (await session.scalars(text("SELECT version_num FROM alembic_version"))).all()
        )
    if schemas != (authority.expected_schema_head,):
        raise SafeEvidenceError("preview_schema_authority_mismatch", "0" * 64)
    packet["schema_current"] = authority.expected_schema_head
    packet["schema_head"] = authority.expected_schema_head
    if (
        authority.execution_packet_path is not None
        and authority.execution_packet_sha256
        and authority.execution_packet_digest
    ):
        if _sha256(authority.execution_packet_path) != authority.execution_packet_sha256:
            raise SafeEvidenceError("hcp_november_execution_packet_sha256_mismatch", "0" * 64)
        envelope = NovemberExecutionEnvelope.load(authority.execution_packet_path)
        envelope.verify_against(authority)
        envelope.packet.verify_against(authority, None)
        packet["execution_envelope"] = {
            "contract": "hcp-november-preview-execution-envelope/v1",
            "authority_digest": envelope.authority_digest,
            "source_packet_sha256": envelope.source_packet_sha256,
            "source_packet_digest": envelope.source_packet_digest,
            "packet_counts": envelope.packet_counts,
            "total_held": envelope.total_held,
            "executable_count": envelope.executable_count,
            "unexplained_omissions": envelope.unexplained_omissions,
            "lineage_gaps": envelope.lineage_gaps,
            "ambiguous_lineage": envelope.ambiguous_lineage,
            "held_parent_executable_edges": envelope.held_parent_executable_edges,
            "operational_hold_policy": envelope.operational_hold_policy,
            "operational_hold_source_ids": envelope.operational_hold_source_ids,
        }
    packet["mode"] = "qualify"
    return packet


async def run_supplemental_current_state_qualification(
    authority_path: Path,
    *,
    dry_run: bool = False,
    execute: bool = False,
) -> dict[str, object]:
    """Validate a current-state authority and the live Preview boundary read-only."""
    validate_runtime_boundary(
        os.getenv("TARGET_ENVIRONMENT", ""),
        os.getenv("PRODUCTION_ACCESS_ENABLED", "false").lower() == "true",
        os.getenv("PREVIEW_ACCESS_ENABLED", "false").lower() == "true",
        {
            name: os.getenv(name, "false")
            for name in (
                "HCP_PROVIDER_WRITE_ENABLED",
                "HCP_LIVE_ACCESS_ENABLED",
                "QBO_PRODUCTION_ENABLED",
                "PAYROLL_EXECUTION_ENABLED",
            )
        },
    )
    authority = validate_supplemental_current_state_authority(authority_path)
    if os.getenv("APP_VERSION", "") != authority.repository_sha:
        raise SafeEvidenceError("hcp_november_supplemental_repository_authority_mismatch", "0" * 64)
    async with AsyncSessionFactory() as session:
        schema = tuple((await session.scalars(text("SELECT version_num FROM alembic_version"))).all())
        database = str(await session.scalar(text("SELECT current_database()")))
    if schema != (authority.schema_head,) or database != "acp_enterprise_preview":
        raise SafeEvidenceError("hcp_november_supplemental_database_authority_mismatch", "0" * 64)
    inventory = _packet_inventory(authority.packet.records)
    result: dict[str, object] = {
        "contract": "hcp-november-supplemental-current-state-authority/v1",
        "status": "PASS",
        "mode": "qualify",
        "authority_digest": authority.authority_digest,
        "packet_digest": authority.packet_digest,
        "counts": inventory["counts"],
        "executable_count": inventory["executable"],
        "total_held": inventory["total_held"],
        "unexplained_omissions": authority.unexplained_omissions,
        "lineage_gaps": authority.lineage_gaps,
        "held_parent_executable_edges": inventory["held_parent_executable_edges"],
    }
    if not dry_run and not execute:
        return result

    runtime_authority = NovemberQualificationAuthority(
        bundle_path=Path("/run/hcp-admission/immutable-november-bundle.tar.gz"),
        bundle_sha256=authority.bundle_sha256,
        expected_repository_sha=authority.repository_sha,
        expected_schema_head=authority.schema_head,
        expected_company_id=authority.company_id,
        expected_branch_id=authority.branch_id,
        expected_actor_id=authority.actor_id,
        expected_hcp_provider_company_id=authority.provider_company_id,
        expected_environment=authority.target,
        expected_acquisition_digest=authority.immutable_source_packet_digest,
        expected_reconciliation_digest=authority.reconciliation_digest,
        expected_attachment_custody_digest=authority.supplemental_manifest_digest,
        expected_policy_digest=authority.policy_digest,
        qualification_status="PASS",
        qualification_digest=authority.packet.qualification_digest,
        rollback_backup_digest=authority.rollback_backup_digest,
    )
    async with AsyncSessionFactory() as session:
        context = await resolve_rehearsal_context(session, runtime_authority, credentialed=True)
        if (
            context.company.id != runtime_authority.company_id
            or context.active_branch is None
            or context.active_branch.id != runtime_authority.branch_id
            or context.user.id != runtime_authority.actor_id
            or not context.has_permission(MigrationPermission.EXECUTE_REHEARSAL)
        ):
            raise SafeEvidenceError("hcp_november_supplemental_execution_scope_invalid", "0" * 64)
        database_identity = str(
            await session.scalar(text("SELECT current_database() || ':' || current_user"))
        )
        await session.rollback()
        binding = CurrentOverlayLineageBinding(
            company_id=runtime_authority.company_id,
            branch_id=runtime_authority.branch_id,
            actor_id=runtime_authority.actor_id,
            source4_package_identity="hcp-clean-beta-november-supplemental-current-state",
            base_source4_digest=runtime_authority.bundle_sha256,
            overlay_manifest_digest=authority.packet.overlay_manifest.digest,
            overlay_file_digest=authority.packet_digest,
            hold_digest=runtime_authority.expected_policy_digest or "",
            canonical_hold_count=authority.held_count,
            authority_sha=runtime_authority.expected_repository_sha,
            schema_head=runtime_authority.expected_schema_head,
        )
        services = HcpCurrentOverlayNativeServices(
            context=context,
            master_run_id=binding.master_run_id,
            customer_run_id=binding.master_run_id,
            operational_run_id=binding.master_run_id,
            package_digest=runtime_authority.bundle_sha256,
            base_source_digests={
                record.key: record.prior_source_digest or record.source_digest
                for record in authority.packet.overlay_manifest.records
            },
            allow_clean_baseline_bootstrap=True,
        )
        bootstrap = CurrentOverlayLineageBootstrap(binding, authority.packet.overlay_manifest)
        repository = SqlAlchemyCurrentOverlayRepository(
            session,
            master_run_id=binding.master_run_id,
            services=services,
            lineage_bootstrap=bootstrap,
            overlay_records=authority.packet.overlay_manifest.records,
            advisory_lock_identity=f"hcp-november:{runtime_authority.company_id}:{runtime_authority.branch_id}",
            execution_context={
                "execution_packet_digest": authority.packet_digest,
                "execution_packet_sha256": authority.packet_sha256,
            },
            dry_run=dry_run,
        )
        receipt = await NovemberBoundedExecutor().execute(
            repository,
            authority=runtime_authority,
            packet=authority.packet,
            # The supplemental authority is the qualified boundary. Its
            # packet carries the immutable qualification digest, not the
            # legacy small-dictionary qualification projection.
            qualified_packet=None,
            database_identity=database_identity,
            schema_head=authority.schema_head,
            clean_baseline_bootstrap=True,
        )
    result["execution"] = {
        "status": "PASS" if execute else "DRY_RUN_PASS",
        "receipt_digest": receipt.digest,
        "journal_count": len(receipt.journal),
        "outcomes": receipt.counts,
        "native_actions": dict(
            Counter(
                item.native_action
                for item in receipt.journal
                if item.native_action is not None
            )
        ),
        "transaction_rolled_back": dry_run,
        "held_records_mutated": receipt.counts.get("held", 0) != inventory["total_held"],
    }
    result["mode"] = "execute" if execute else "qualify"
    return result


async def run_discrepancy_quarantine_qualification(
    authority_path: Path,
    *,
    dry_run: bool = False,
    execute: bool = False,
) -> dict[str, object]:
    """Qualify or execute the policy's non-authoritative discrepancy subset."""
    validate_runtime_boundary(
        os.getenv("TARGET_ENVIRONMENT", ""),
        os.getenv("PRODUCTION_ACCESS_ENABLED", "false").lower() == "true",
        os.getenv("PREVIEW_ACCESS_ENABLED", "false").lower() == "true",
        {
            name: os.getenv(name, "false")
            for name in (
                "HCP_PROVIDER_WRITE_ENABLED",
                "HCP_LIVE_ACCESS_ENABLED",
                "QBO_PRODUCTION_ENABLED",
                "PAYROLL_EXECUTION_ENABLED",
            )
        },
    )
    authority = DiscrepancyQuarantineAuthority.load(authority_path)
    if os.getenv("APP_VERSION", "") != authority.repository_sha:
        raise SafeEvidenceError("hcp_discrepancy_repository_authority_mismatch", "0" * 64)
    async with AsyncSessionFactory() as session:
        schema = tuple((await session.scalars(text("SELECT version_num FROM alembic_version"))).all())
        database = str(await session.scalar(text("SELECT current_database()")))
    if schema != (authority.schema_head,) or database != "acp_enterprise_preview":
        raise SafeEvidenceError("hcp_discrepancy_database_authority_mismatch", "0" * 64)
    inventory = _packet_inventory(authority.packet.records)
    result: dict[str, object] = {
        "contract": DISCREPANCY_AUTHORITY_CONTRACT,
        "status": "PASS",
        "mode": "qualify",
        "authority_digest": authority.authority_digest,
        "packet_digest": authority.packet_digest,
        "counts": inventory["counts"],
        "executable_count": inventory["executable"],
        "total_held": inventory["total_held"],
        "quarantined_records": len(authority.quarantined_records),
        "unexplained_omissions": authority.unexplained_omissions,
        "lineage_gaps": authority.lineage_gaps,
        "held_parent_executable_edges": inventory["held_parent_executable_edges"],
    }
    if not dry_run and not execute:
        return result

    from app.operational_migration.hcp_november_supplemental_authority import SupplementalCurrentStateAuthority

    base = SupplementalCurrentStateAuthority.load(authority.base_authority_path)
    runtime_authority = NovemberQualificationAuthority(
        bundle_path=Path("/run/hcp-admission/immutable-november-bundle.tar.gz"),
        bundle_sha256=authority.bundle_sha256,
        expected_repository_sha=authority.repository_sha,
        expected_schema_head=authority.schema_head,
        expected_company_id=authority.company_id,
        expected_branch_id=authority.branch_id,
        expected_actor_id=authority.actor_id,
        expected_hcp_provider_company_id=authority.provider_company_id,
        expected_environment=authority.target,
        expected_acquisition_digest=authority.source_packet_digest,
        expected_reconciliation_digest=authority.reconciliation_digest,
        expected_attachment_custody_digest=base.supplemental_manifest_digest,
        expected_policy_digest=authority.policy_digest,
        qualification_status="PASS",
        qualification_digest=authority.packet.qualification_digest,
        rollback_backup_digest=authority.rollback_backup_digest,
    )
    async with AsyncSessionFactory() as session:
        context = await resolve_rehearsal_context(session, runtime_authority, credentialed=True)
        if (
            context.company.id != runtime_authority.company_id
            or context.active_branch is None
            or context.active_branch.id != runtime_authority.branch_id
            or context.user.id != runtime_authority.actor_id
            or not context.has_permission(MigrationPermission.EXECUTE_REHEARSAL)
        ):
            raise SafeEvidenceError("hcp_discrepancy_execution_scope_invalid", "0" * 64)
        database_identity = str(await session.scalar(text("SELECT current_database() || ':' || current_user")))
        await session.rollback()
        binding = CurrentOverlayLineageBinding(
            company_id=runtime_authority.company_id,
            branch_id=runtime_authority.branch_id,
            actor_id=runtime_authority.actor_id,
            source4_package_identity="hcp-clean-beta-november-discrepancy-quarantine",
            base_source4_digest=runtime_authority.bundle_sha256,
            overlay_manifest_digest=authority.packet.overlay_manifest.digest,
            overlay_file_digest=authority.packet_sha256,
            hold_digest=authority.policy_digest,
            canonical_hold_count=authority.held_count,
            authority_sha=authority.repository_sha,
            schema_head=authority.schema_head,
        )
        services = HcpCurrentOverlayNativeServices(
            context=context,
            master_run_id=binding.master_run_id,
            customer_run_id=binding.master_run_id,
            operational_run_id=binding.master_run_id,
            package_digest=runtime_authority.bundle_sha256,
            base_source_digests={
                record.key: record.prior_source_digest or record.source_digest
                for record in authority.packet.overlay_manifest.records
            },
            allow_clean_baseline_bootstrap=True,
        )
        bootstrap = CurrentOverlayLineageBootstrap(binding, authority.packet.overlay_manifest)
        repository = SqlAlchemyCurrentOverlayRepository(
            session,
            master_run_id=binding.master_run_id,
            services=services,
            lineage_bootstrap=bootstrap,
            overlay_records=authority.packet.overlay_manifest.records,
            advisory_lock_identity=f"hcp-november:{authority.company_id}:{authority.branch_id}",
            execution_context={
                "execution_packet_digest": authority.packet_digest,
                "execution_packet_sha256": authority.packet_sha256,
                "quarantine_policy": "preserve-quarantine-surface-resolve-later/v1",
            },
            dry_run=dry_run,
        )
        receipt = await NovemberBoundedExecutor().execute(
            repository,
            authority=runtime_authority,
            packet=authority.packet,
            qualified_packet={
                "unexplained_omissions": authority.unexplained_omissions,
                "missing_lineage": authority.lineage_gaps,
                "ambiguous_lineage": authority.ambiguous_lineage,
            },
            database_identity=database_identity,
            schema_head=authority.schema_head,
            clean_baseline_bootstrap=True,
        )
    result["execution"] = {
        "status": "PASS" if execute else "DRY_RUN_PASS",
        "receipt_digest": receipt.digest,
        "journal_count": len(receipt.journal),
        "outcomes": receipt.counts,
        "native_actions": dict(Counter(item.native_action for item in receipt.journal if item.native_action is not None)),
        "transaction_rolled_back": dry_run,
        "held_records_mutated": False,
    }
    result["mode"] = "execute" if execute else "qualify"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("qualify", "execute"))
    parser.add_argument("--authority-file", required=True, type=Path)
    parser.add_argument("--authorize-execution", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    authority_path = args.authority_file
    try:
        authority_contract = json.loads(authority_path.read_bytes()).get("contract")
    except (OSError, json.JSONDecodeError, AttributeError):
        authority_contract = None
    if authority_contract == "hcp-november-supplemental-current-state-authority/v1":
        if args.mode == "execute" and not args.authorize_execution:
            print(json.dumps({
                "status": "rejected",
                "code": "explicit_execution_authorization_required",
            }))
            return 2
        try:
            output = asyncio.run(
                run_supplemental_current_state_qualification(
                    authority_path,
                    dry_run=args.dry_run,
                    execute=args.mode == "execute",
                )
            )
        except Exception as error:  # noqa: BLE001
            code = (
                error.code
                if isinstance(error, SafeEvidenceError)
                else "hcp_november_supplemental_qualification_failed"
            )
            print(json.dumps({"status": "rejected", "code": code}))
            return 2
        print(json.dumps(output, sort_keys=True))
        return 0
    if authority_contract == DISCREPANCY_AUTHORITY_CONTRACT:
        if args.mode == "execute" and not args.authorize_execution:
            print(json.dumps({"status": "rejected", "code": "explicit_execution_authorization_required"}))
            return 2
        try:
            output = asyncio.run(
                run_discrepancy_quarantine_qualification(
                    authority_path,
                    dry_run=args.dry_run,
                    execute=args.mode == "execute",
                )
            )
        except Exception as error:  # noqa: BLE001
            code = error.code if isinstance(error, SafeEvidenceError) else "hcp_discrepancy_qualification_failed"
            print(json.dumps({"status": "rejected", "code": code}))
            return 2
        print(json.dumps(output, sort_keys=True))
        return 0
    if authority_contract == NOVEMBER_AUTHORITY_CONTRACT:
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
                run_november_bundle(
                    NovemberQualificationAuthority.load(authority_path),
                    execute=args.mode == "execute",
                )
            )
        except Exception as error:  # noqa: BLE001
            code = (
                error.code
                if isinstance(error, SafeEvidenceError)
                else "hcp_november_qualification_failed"
            )
            print(json.dumps({"status": "rejected", "code": code}))
            return 2
        print(json.dumps(output, sort_keys=True))
        return 0
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
