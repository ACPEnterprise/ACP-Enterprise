"""Atomic SOURCE.4 lineage for bounded current-operational overlay admission."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_migration.models import CustomerMigrationRun
from app.operational_migration.hcp_current_overlay import (
    CurrentOverlayManifest,
    OverlayExecutionReceipt,
    OverlayJournalEntry,
)
from app.operational_migration.hcp_migration2b import canonical_sha256
from app.operational_migration.models import (
    HcpMigrationMasterRun,
    OperationalMigrationRun,
)

LINEAGE_CONTRACT = "hcp-current-overlay-lineage-bootstrap/v1"
LINEAGE_NAMESPACE = UUID("a17961b8-3aa9-5fbd-8b62-531660452bf4")
MASTER_STATUS = "completed_current_operational"


@dataclass(frozen=True)
class CurrentOverlayLineageBinding:
    company_id: UUID
    branch_id: UUID
    actor_id: UUID
    source4_package_identity: str
    base_source4_digest: str
    overlay_manifest_digest: str
    overlay_file_digest: str
    hold_digest: str
    canonical_hold_count: int
    authority_sha: str
    schema_head: str

    @property
    def payload(self) -> dict[str, object]:
        return {
            "contract": LINEAGE_CONTRACT,
            "company_id": str(self.company_id),
            "branch_id": str(self.branch_id),
            "actor_id": str(self.actor_id),
            "source4_package_identity": self.source4_package_identity,
            "base_source4_digest": self.base_source4_digest,
            "overlay_manifest_digest": self.overlay_manifest_digest,
            "overlay_file_digest": self.overlay_file_digest,
            "hold_digest": self.hold_digest,
            "canonical_hold_count": self.canonical_hold_count,
            "authority_sha": self.authority_sha,
            "schema_head": self.schema_head,
        }

    @property
    def input_digest(self) -> str:
        return canonical_sha256(self.payload)

    @property
    def master_run_id(self) -> UUID:
        # Repository-standard deterministic run creation; callers never supply UUIDs.
        return uuid5(LINEAGE_NAMESPACE, self.input_digest)


class CurrentOverlayLineageBootstrap:
    """Create/resolve bounded lineage inside the overlay-owned transaction."""

    def __init__(
        self, binding: CurrentOverlayLineageBinding, manifest: CurrentOverlayManifest
    ) -> None:
        self.binding = binding
        self.manifest = manifest
        self.master: HcpMigrationMasterRun | None = None
        self.customer_run: CustomerMigrationRun | None = None
        self.operational_run: OperationalMigrationRun | None = None

    async def establish(self, session: AsyncSession) -> HcpMigrationMasterRun:
        binding = self.binding
        existing = await session.scalar(
            select(HcpMigrationMasterRun)
            .where(
                HcpMigrationMasterRun.company_id == binding.company_id,
                HcpMigrationMasterRun.branch_id == binding.branch_id,
                HcpMigrationMasterRun.package_digest == binding.base_source4_digest,
            )
            .with_for_update()
        )
        if existing is None:
            existing = HcpMigrationMasterRun(
                id=binding.master_run_id,
                company_id=binding.company_id,
                branch_id=binding.branch_id,
                actor_user_id=binding.actor_id,
                package_digest=binding.base_source4_digest,
                collection_digests={
                    "current_overlay_file": binding.overlay_file_digest,
                    "canonical_hold_packet": binding.hold_digest,
                },
                transformation_contracts={
                    "contract": LINEAGE_CONTRACT,
                    "source4_package_identity": binding.source4_package_identity,
                    "overlay_manifest_digest": binding.overlay_manifest_digest,
                    "admission_scope": "current_operational_only",
                    "canonical_admission_allowed": False,
                },
                owner_receipts={
                    "execution_authority_sha": binding.authority_sha,
                    "bounded_overlay_authorized": True,
                },
                schema_head=binding.schema_head,
                implementation_version=LINEAGE_CONTRACT,
                supported_entities=[
                    "customer",
                    "service_location",
                    "job",
                    "appointment",
                ],
                baseline_counts={},
                source_counts=_domain_counts(self.manifest),
                transformed_counts={},
                persisted_counts={},
                hold_counts={"canonical_ambiguous": binding.canonical_hold_count},
                exception_counts={},
                rejection_counts={},
                unresolved_counts={},
                non_applicable_counts={},
                child_run_ids={},
                reconciliation_digest=None,
                replay_state={
                    "state": "running",
                    "admission_scope": "current_operational_only",
                },
                resume_state={"state": "running"},
                rollback_state={
                    "state": "backup_qualified",
                    "audit_evidence": "retained",
                },
                input_digest=binding.input_digest,
                attestation_digest=canonical_sha256(
                    {"input": binding.payload, "status": "running"}
                ),
                status="running",
                started_at=datetime.now(timezone.utc),
                completed_at=None,
            )
            session.add(existing)
            await session.flush()
        self._validate_master(existing)
        self.master = existing
        self.customer_run = await self._customer_child(session, existing)
        self.operational_run = await self._operational_child(session, existing)
        return existing

    def _validate_master(self, run: HcpMigrationMasterRun) -> None:
        b = self.binding
        if (
            run.id != b.master_run_id
            or run.input_digest != b.input_digest
            or run.actor_user_id != b.actor_id
            or run.schema_head != b.schema_head
            or run.collection_digests.get("current_overlay_file")
            != b.overlay_file_digest
            or run.collection_digests.get("canonical_hold_packet") != b.hold_digest
            or run.transformation_contracts.get("overlay_manifest_digest")
            != b.overlay_manifest_digest
            or run.transformation_contracts.get("source4_package_identity")
            != b.source4_package_identity
            or run.transformation_contracts.get("admission_scope")
            != "current_operational_only"
            or run.transformation_contracts.get("canonical_admission_allowed")
            is not False
            or run.owner_receipts.get("execution_authority_sha") != b.authority_sha
            or run.owner_receipts.get("bounded_overlay_authorized") is not True
            or run.hold_counts.get("canonical_ambiguous") != b.canonical_hold_count
            or run.status not in {"running", MASTER_STATUS}
        ):
            raise ValueError("overlay SOURCE.4 lineage binding conflict")

    async def _customer_child(
        self, session: AsyncSession, master: HcpMigrationMasterRun
    ) -> CustomerMigrationRun:
        run = await session.scalar(
            select(CustomerMigrationRun)
            .where(CustomerMigrationRun.master_run_id == master.id)
            .with_for_update()
        )
        count = _domain_counts(self.manifest).get("customer", 0)
        if run is None:
            run = CustomerMigrationRun(
                company_id=self.binding.company_id,
                branch_id=self.binding.branch_id,
                initiated_by_user_id=self.binding.actor_id,
                master_run_id=master.id,
                source_system="housecall_pro_source4",
                source_sha256=self.binding.overlay_manifest_digest,
                mode="import",
                status="running",
                source_count=count,
                accepted_count=0,
                rejected_count=0,
                duplicate_count=0,
                unresolved_count=count,
            )
            session.add(run)
            await session.flush()
        if (
            run.source_sha256 != self.binding.overlay_manifest_digest
            or run.source_count != count
            or run.status not in {"running", "completed"}
        ):
            raise ValueError("overlay Customer child lineage conflict")
        return run

    async def _operational_child(
        self, session: AsyncSession, master: HcpMigrationMasterRun
    ) -> OperationalMigrationRun:
        run = await session.scalar(
            select(OperationalMigrationRun)
            .where(
                OperationalMigrationRun.master_run_id == master.id,
                OperationalMigrationRun.master_domain == "operational",
                OperationalMigrationRun.repair_generation == 0,
            )
            .with_for_update()
        )
        count = sum(
            v for k, v in _domain_counts(self.manifest).items() if k != "customer"
        )
        if run is None:
            run = OperationalMigrationRun(
                company_id=self.binding.company_id,
                branch_id=self.binding.branch_id,
                initiated_by_user_id=self.binding.actor_id,
                master_run_id=master.id,
                master_domain="operational",
                repair_generation=0,
                source_system="housecall_pro_source4",
                source_digest=self.binding.overlay_manifest_digest,
                mode="import",
                status="running",
                source_count=count,
                accepted_count=0,
                rejected_count=0,
                duplicate_count=0,
                unresolved_count=count,
            )
            session.add(run)
            await session.flush()
        if (
            run.source_digest != self.binding.overlay_manifest_digest
            or run.source_count != count
            or run.status not in {"running", "completed", "completed_with_exceptions"}
        ):
            raise ValueError("overlay Operational child lineage conflict")
        return run

    async def finalize(self, receipt: OverlayExecutionReceipt) -> None:
        if (
            self.master is None
            or self.customer_run is None
            or self.operational_run is None
        ):
            raise ValueError("overlay lineage was not established")
        accepted = {"created", "updated", "idempotent_replay"}
        customer_items = [x for x in receipt.journal if x.key.domain == "customer"]
        operational_items = [x for x in receipt.journal if x.key.domain != "customer"]
        _finish_child(self.customer_run, customer_items, customer=True)
        _finish_child(self.operational_run, operational_items, customer=False)
        now = datetime.now(timezone.utc)
        self.master.persisted_counts = {
            domain: sum(
                x.key.domain == domain and x.outcome in accepted
                for x in receipt.journal
            )
            for domain in _domain_counts(self.manifest)
        }
        self.master.child_run_ids = {
            "customer": str(self.customer_run.id),
            "operational": str(self.operational_run.id),
        }
        self.master.reconciliation_digest = receipt.digest
        replay_state = dict(self.master.replay_state)
        replay_state.update(
            {
                "state": "completed_current_operational",
                "receipt_digest": receipt.digest,
                "canonical_admission_allowed": False,
            }
        )
        self.master.replay_state = replay_state
        self.master.resume_state = {"state": "bounded_current_operational_complete"}
        self.master.status = MASTER_STATUS
        self.master.completed_at = now
        self.master.attestation_digest = canonical_sha256(
            {
                "input_digest": self.master.input_digest,
                "receipt_digest": receipt.digest,
                "status": MASTER_STATUS,
            }
        )


def _domain_counts(manifest: CurrentOverlayManifest) -> dict[str, int]:
    return {
        domain: sum(r.domain == domain for r in manifest.records)
        for domain in ("customer", "service_location", "job", "appointment")
    }


def _finish_child(
    run: CustomerMigrationRun | OperationalMigrationRun,
    items: list[OverlayJournalEntry],
    *,
    customer: bool,
) -> None:
    accepted = sum(
        x.outcome in {"created", "updated", "idempotent_replay"} for x in items
    )
    held = len(items) - accepted
    run.accepted_count = accepted
    run.unresolved_count = held
    run.status = "completed" if customer or not held else "completed_with_exceptions"
    run.completed_at = datetime.now(timezone.utc)
