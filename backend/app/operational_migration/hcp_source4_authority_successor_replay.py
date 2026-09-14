"""Read-only authority-successor verification for a committed SOURCE.4 overlay."""

from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_migration.models import CustomerMigrationRun
from app.events.models import BusinessEvent
from app.operational_migration.hcp_current_overlay import _verify_receipt
from app.operational_migration.hcp_current_overlay_adapter import STATE_KEY, _receipt
from app.operational_migration.hcp_current_overlay_lineage import MASTER_STATUS
from app.operational_migration.hcp_current_overlay_native import (
    HcpCurrentOverlayNativeServices,
)
from app.operational_migration.hcp_current_overlay_v4 import (
    V4ExecutableOverlay,
    sha256,
)
from app.operational_migration.hcp_migration2b import canonical_sha256
from app.operational_migration.models import (
    HcpMigrationHold,
    HcpMigrationMasterRun,
    OperationalMigrationRun,
)

CONTRACT = "hcp-source4-authority-successor-replay/v1"
PURPOSE = "EXACT_REPLAY_VERIFICATION"
VERIFIER_VERSION = "migration.hcp.source4.authority.successor.replay.1"
RESULT = "EXACT_REPLAY_VERIFIED_EXISTING_EXECUTION"
EXPECTED_COUNTS = {"created": 174, "idempotent_replay": 4, "updated": 5, "held": 339}


@dataclass(frozen=True)
class ReplaySuccessorAuthority:
    purpose: str
    original_protected_sha: str
    original_deployed_sha: str
    original_executor_version: str
    original_schema_head: str
    original_execution_authority_path: Path
    original_execution_authority_sha256: str
    original_backup_digest: str
    original_restore_receipt_digest: str
    original_execution_timestamp: str
    original_receipt_digest: str
    successor_protected_sha: str
    successor_deployed_sha: str
    successor_executor_version: str
    current_schema_head: str
    schema_semantic_digest: str
    expected_database: str
    company_id: UUID
    branch_id: UUID
    actor_id: UUID
    v4_path: Path
    v4_file_sha256: str
    v4_semantic_digest: str
    complete_current_graph_digest: str
    source4_package_digest: str
    predecessor_overlay_digest: str
    original_overlay_digest: str
    hold_digest: str
    cohort_digest: str
    runtime_inventory_digest: str
    preview_baseline_digest: str
    idempotency_identity: str
    source_binding_digest: str
    native_post_state_digest: str
    hold_state_digest: str
    business_event_digest: str
    business_event_count: int
    child_lineage_digest: str

    @classmethod
    def load(cls, path: Path) -> ReplaySuccessorAuthority:
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise ValueError("replay successor authority must be mode 0600")
        value = json.loads(path.read_bytes())
        if value.pop("contract", None) != CONTRACT:
            raise ValueError("replay successor authority contract mismatch")
        for key in ("company_id", "branch_id", "actor_id"):
            value[key] = UUID(value[key])
        for key in ("original_execution_authority_path", "v4_path"):
            value[key] = Path(value[key])
        return cls(**value)

    def verify_files(self) -> V4ExecutableOverlay:
        failures: list[dict[str, str]] = []
        if self.purpose != PURPOSE:
            failures.append({"scope": "authority", "reason": "purpose_mismatch"})
        if self.successor_protected_sha != self.successor_deployed_sha:
            failures.append(
                {"scope": "authority", "reason": "successor_deployment_mismatch"}
            )
        if self.successor_executor_version != VERIFIER_VERSION:
            failures.append(
                {"scope": "authority", "reason": "successor_executor_mismatch"}
            )
        for path, digest, label in (
            (
                self.original_execution_authority_path,
                self.original_execution_authority_sha256,
                "original_execution_authority",
            ),
            (self.v4_path, self.v4_file_sha256, "v4"),
        ):
            if not path.is_file() or sha256(path) != digest:
                failures.append({"scope": label, "reason": "file_digest_mismatch"})
            elif stat.S_IMODE(path.stat().st_mode) & 0o077:
                failures.append({"scope": label, "reason": "file_mode_mismatch"})
        if failures:
            raise ReplayVerificationError(failures)
        original = json.loads(self.original_execution_authority_path.read_bytes())
        original_bindings = {
            "protected_sha": self.original_protected_sha,
            "deployed_sha": self.original_deployed_sha,
            "executor_version": self.original_executor_version,
            "schema_head": self.original_schema_head,
            "overlay_file_sha256": self.v4_file_sha256,
            "overlay_semantic_digest": self.v4_semantic_digest,
            "complete_current_graph_digest": self.complete_current_graph_digest,
            "source4_package_digest": self.source4_package_digest,
            "v3_predecessor_digest": self.predecessor_overlay_digest,
            "original_overlay_digest": self.original_overlay_digest,
            "hold_packet_digest": self.hold_digest,
            "update_cohort_digest": self.cohort_digest,
            "runtime_inventory_digest": self.runtime_inventory_digest,
            "preview_baseline_semantic_digest": self.preview_baseline_digest,
            "company_id": str(self.company_id),
            "branch_id": str(self.branch_id),
            "idempotency_identity": self.idempotency_identity,
            "backup_digest": self.original_backup_digest,
            "restore_receipt_digest": self.original_restore_receipt_digest,
        }
        for key, expected in original_bindings.items():
            if original.get(key) != expected:
                failures.append(
                    {"scope": "original_authority", "reason": f"{key}_mismatch"}
                )
        if failures:
            raise ReplayVerificationError(failures)
        overlay = V4ExecutableOverlay.load(self.v4_path)
        if (
            overlay.semantic_digest != self.v4_semantic_digest
            or overlay.complete_current_graph_digest
            != self.complete_current_graph_digest
            or overlay.base_source4_digest != self.source4_package_digest
            or overlay.company_id != self.company_id
            or overlay.branch_id != self.branch_id
        ):
            raise ReplayVerificationError(
                [{"scope": "v4", "reason": "semantic_authority_mismatch"}]
            )
        raw = json.loads(self.v4_path.read_bytes())
        bindings = {
            "v3_predecessor_digest": self.predecessor_overlay_digest,
            "original_overlay_manifest_digest": self.original_overlay_digest,
            "hold_packet_sha256": self.hold_digest,
            "update_cohort_authority_digest": self.cohort_digest,
            "runtime_inventory_sha256": self.runtime_inventory_digest,
            "preview_baseline_semantic_digest": self.preview_baseline_digest,
        }
        mismatches = [
            key for key, expected in bindings.items() if raw.get(key) != expected
        ]
        if mismatches:
            raise ReplayVerificationError(
                [
                    {"scope": "v4", "reason": f"lineage_mismatch:{key}"}
                    for key in mismatches
                ]
            )
        return overlay


class ReplayVerificationError(ValueError):
    def __init__(self, failures: list[dict[str, str]]) -> None:
        self.failures = failures
        super().__init__(
            json.dumps(
                {
                    "contract": "hcp-source4-exact-replay-preflight/v1",
                    "failure_count": len(failures),
                    "failures": failures,
                    "verified": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )


@dataclass(frozen=True)
class ExactReplayResult:
    result: str
    receipt_digest: str
    master_run_id: UUID
    record_count: int
    mutation_count: int
    report_digest: str


async def verify_exact_replay(
    session: AsyncSession,
    *,
    authority: ReplaySuccessorAuthority,
    overlay: V4ExecutableOverlay,
    services: HcpCurrentOverlayNativeServices,
) -> ExactReplayResult:
    """Verify every committed execution dependency without taking write locks."""
    failures: list[dict[str, str]] = []
    if authority.schema_semantic_digest != schema_semantic_digest():
        failures.append(
            {"scope": "schema", "reason": "semantic_compatibility_mismatch"}
        )
    masters = tuple(
        (
            await session.scalars(
                select(HcpMigrationMasterRun).where(
                    HcpMigrationMasterRun.company_id == authority.company_id,
                    HcpMigrationMasterRun.branch_id == authority.branch_id,
                    HcpMigrationMasterRun.package_digest
                    == authority.source4_package_digest,
                )
            )
        ).all()
    )
    if len(masters) != 1:
        raise ReplayVerificationError(
            [{"scope": "master", "reason": f"expected_one_found_{len(masters)}"}]
        )
    master = masters[0]
    _verify_master(master, authority, overlay, failures)
    state = master.replay_state.get(STATE_KEY)
    if not isinstance(state, dict):
        raise ReplayVerificationError(
            failures + [{"scope": "receipt", "reason": "durable_replay_state_missing"}]
        )
    receipts = state.get("receipts")
    stored = (
        receipts.get(overlay.manifest.digest) if isinstance(receipts, dict) else None
    )
    if stored is None:
        failures.append({"scope": "receipt", "reason": "durable_receipt_missing"})
        receipt = None
    else:
        try:
            receipt = _receipt(stored)
            _verify_receipt(
                receipt, overlay.manifest.digest, receipt.rollback_backup_digest
            )
        except (KeyError, TypeError, ValueError):
            receipt = None
            failures.append({"scope": "receipt", "reason": "durable_receipt_invalid"})
    if receipt is not None:
        if receipt.digest != authority.original_receipt_digest:
            failures.append({"scope": "receipt", "reason": "receipt_digest_mismatch"})
        if receipt.rollback_backup_digest != authority.original_backup_digest:
            failures.append({"scope": "receipt", "reason": "backup_digest_mismatch"})
        if receipt.counts != EXPECTED_COUNTS or len(receipt.journal) != 522:
            failures.append(
                {"scope": "receipt", "reason": "receipt_accounting_mismatch"}
            )
        execution_context = (
            stored.get("execution_context", {}) if isinstance(stored, dict) else {}
        )
        expected_context = {
            "authority_contract": "hcp-current-overlay-native-execution/v3",
            "executor_version": authority.original_executor_version,
            "v4_digest": authority.v4_semantic_digest,
            "v4_file_sha256": authority.v4_file_sha256,
            "complete_current_graph_digest": authority.complete_current_graph_digest,
            "predecessor_overlay_digest": authority.predecessor_overlay_digest,
            "original_overlay_digest": authority.original_overlay_digest,
            "hold_packet_digest": authority.hold_digest,
            "update_cohort_digest": authority.cohort_digest,
            "runtime_inventory_digest": authority.runtime_inventory_digest,
            "preview_baseline_semantic_digest": authority.preview_baseline_digest,
            "idempotency_identity": authority.idempotency_identity,
            "record_count": 522,
        }
        for key, expected in expected_context.items():
            if (
                not isinstance(execution_context, dict)
                or execution_context.get(key) != expected
            ):
                failures.append(
                    {
                        "scope": "receipt",
                        "reason": f"execution_context_{key}_mismatch",
                    }
                )
        await _verify_records(session, receipt.journal, overlay, services, failures)
    child_digest = await _child_digest(session, master, failures)
    if child_digest != authority.child_lineage_digest:
        failures.append(
            {"scope": "children", "reason": "child_lineage_digest_mismatch"}
        )
    hold_digest = await _hold_digest(session, master)
    if hold_digest != authority.hold_state_digest:
        failures.append({"scope": "holds", "reason": "hold_state_digest_mismatch"})
    event_digest, event_count = await _event_digest(session, master, receipt)
    if (
        event_digest != authority.business_event_digest
        or event_count != authority.business_event_count
    ):
        failures.append(
            {"scope": "events", "reason": "business_event_evidence_mismatch"}
        )
    binding_digest = _state_family_digest(state, "source_states")
    if binding_digest != authority.source_binding_digest:
        failures.append(
            {"scope": "bindings", "reason": "source_binding_digest_mismatch"}
        )
    native_digest = await _native_digest(session, receipt)
    if native_digest != authority.native_post_state_digest:
        failures.append(
            {"scope": "native", "reason": "native_post_state_digest_mismatch"}
        )
    if failures:
        raise ReplayVerificationError(failures)
    report_digest = canonical_sha256(
        {
            "contract": "hcp-source4-exact-replay-result/v1",
            "master_run_id": str(master.id),
            "receipt_digest": authority.original_receipt_digest,
            "successor_authority": authority.successor_protected_sha,
            "result": RESULT,
        }
    )
    return ExactReplayResult(
        RESULT, authority.original_receipt_digest, master.id, 522, 0, report_digest
    )


def schema_semantic_digest() -> str:
    return canonical_sha256(
        {
            "contract": "hcp-source4-replay-schema-semantics/v1",
            "master": "hcp_migration_master_runs/v1",
            "customer_child": "customer_migration_runs/v1",
            "operational_child": "operational_migration_runs/v1",
            "holds": "hcp_migration_holds/v1",
            "events": "business_events/v1",
            "source_system": "housecall_pro_source4",
            "overlay": "hcp-current-overlay-merge-packet/v4",
            "receipt": "hcp-current-overlay-executor/v1",
        }
    )


def _verify_master(
    master: HcpMigrationMasterRun,
    authority: ReplaySuccessorAuthority,
    overlay: V4ExecutableOverlay,
    failures: list[dict[str, str]],
) -> None:
    expected = {
        "status": master.status == MASTER_STATUS,
        "original_authority": master.owner_receipts.get("execution_authority_sha")
        == authority.original_protected_sha,
        "original_schema": master.schema_head
        == json.loads(authority.original_execution_authority_path.read_bytes()).get(
            "schema_head"
        )
        == authority.original_schema_head,
        "overlay_file": master.collection_digests.get("current_overlay_file")
        == authority.v4_file_sha256,
        "hold": master.collection_digests.get("canonical_hold_packet")
        == authority.hold_digest,
        "overlay_semantic": master.transformation_contracts.get(
            "overlay_manifest_digest"
        )
        == overlay.semantic_digest,
        "receipt": master.reconciliation_digest == authority.original_receipt_digest,
        "replay_receipt": master.replay_state.get("receipt_digest")
        == authority.original_receipt_digest,
        "execution_timestamp": master.completed_at is not None
        and master.completed_at.isoformat() == authority.original_execution_timestamp,
    }
    failures.extend(
        {"scope": "master", "reason": f"{key}_mismatch"}
        for key, valid in expected.items()
        if not valid
    )


async def _verify_records(
    session: AsyncSession,
    journal: tuple[Any, ...],
    overlay: V4ExecutableOverlay,
    services: HcpCurrentOverlayNativeServices,
    failures: list[dict[str, str]],
) -> None:
    by_key = {item.key: item for item in journal}
    if set(by_key) != {record.key for record in overlay.manifest.records}:
        failures.append({"scope": "records", "reason": "journal_coverage_mismatch"})
    for record in overlay.manifest.records:
        item = by_key.get(record.key)
        label = f"{record.domain}:{record.source_id}"
        if item is None:
            continue
        successor = overlay.successor_assertions[record.key]
        if successor == "HOLD":
            if item.outcome != "held" or item.native_id is not None:
                failures.append({"scope": label, "reason": "hold_disposition_mismatch"})
            continue
        state = await services.persisted_source_state(session, record.key)
        if state is None:
            failures.append({"scope": label, "reason": "source_binding_missing"})
            continue
        if state.native_id != item.native_id:
            failures.append({"scope": label, "reason": "native_target_mismatch"})
        if state.source_digest != record.source_digest:
            failures.append({"scope": label, "reason": "source_digest_mismatch"})
        expected_outcome = {
            "CREATE_NEW": "created",
            "REUSE_EXISTING": "idempotent_replay",
            "UPDATE_EXISTING": "updated",
        }[successor]
        if item.outcome != expected_outcome:
            failures.append({"scope": label, "reason": "execution_outcome_mismatch"})


async def _child_digest(
    session: AsyncSession,
    master: HcpMigrationMasterRun,
    failures: list[dict[str, str]],
) -> str:
    customers = tuple(
        (
            await session.scalars(
                select(CustomerMigrationRun).where(
                    CustomerMigrationRun.master_run_id == master.id
                )
            )
        ).all()
    )
    operational = tuple(
        (
            await session.scalars(
                select(OperationalMigrationRun).where(
                    OperationalMigrationRun.master_run_id == master.id
                )
            )
        ).all()
    )
    if len(customers) != 1 or len(operational) != 1:
        failures.append({"scope": "children", "reason": "child_cardinality_mismatch"})
    return canonical_sha256(
        {
            "customer": [_row_snapshot(item) for item in customers],
            "operational": [_row_snapshot(item) for item in operational],
        }
    )


async def _hold_digest(session: AsyncSession, master: HcpMigrationMasterRun) -> str:
    rows = tuple(
        (
            await session.scalars(
                select(HcpMigrationHold).where(
                    HcpMigrationHold.master_run_id == master.id
                )
            )
        ).all()
    )
    return canonical_sha256([_row_snapshot(row) for row in rows])


async def _event_digest(
    session: AsyncSession, master: HcpMigrationMasterRun, receipt: Any
) -> tuple[str, int]:
    if receipt is None or master.completed_at is None:
        return canonical_sha256([]), 0
    rows = tuple(
        (
            await session.scalars(
                select(BusinessEvent).where(
                    BusinessEvent.company_id == master.company_id,
                    BusinessEvent.branch_id == master.branch_id,
                    BusinessEvent.created_at >= master.started_at,
                    BusinessEvent.created_at <= master.completed_at,
                )
            )
        ).all()
    )
    return canonical_sha256([_row_snapshot(row) for row in rows]), len(rows)


async def _native_digest(session: AsyncSession, receipt: Any) -> str:
    if receipt is None:
        return canonical_sha256([])
    from app.customers.models import Customer, ServiceLocation
    from app.jobs.models import Job
    from app.scheduling.models import Appointment

    models = {
        "customer": Customer,
        "service_location": ServiceLocation,
        "job": Job,
        "appointment": Appointment,
    }
    rows: list[dict[str, object]] = []
    for item in receipt.journal:
        if item.native_id is None:
            continue
        native = await session.get(models[item.key.domain], UUID(item.native_id))
        rows.append(
            {
                "key": f"{item.key.domain}:{item.key.source_id}",
                "row": _row_snapshot(native) if native is not None else None,
            }
        )
    return canonical_sha256(rows)


def _state_family_digest(state: dict[str, object], key: str) -> str:
    return canonical_sha256(state.get(key, {}))


def _row_snapshot(value: Any) -> dict[str, object]:
    mapper = inspect(type(value))
    return {
        column.key: _json_value(getattr(value, column.key)) for column in mapper.columns
    }


def _json_value(value: Any) -> object:
    if isinstance(value, (datetime, UUID, Decimal)):
        return str(value)
    if isinstance(value, bytes):
        return hashlib.sha256(value).hexdigest()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value
