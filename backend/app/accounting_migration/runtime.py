from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Protocol

from app.accounting_migration.manifest import OpeningPackage


class RuntimeValidationError(ValueError):
    """Deterministic opening-state validation failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class JournalLine:
    line_id: str
    account_source_id: str
    branch_id: str
    debit: Decimal = Decimal("0.00")
    credit: Decimal = Decimal("0.00")
    source_artifact_id: str = ""
    source_row: int = 0


@dataclass(frozen=True)
class ControlTie:
    control_id: str
    source_amount: Decimal
    opening_amount: Decimal
    source_artifact_id: str


@dataclass(frozen=True)
class RowAccounting:
    artifact_id: str
    source: int
    accepted: int
    rejected: int
    pending_disposition: int = 0


@dataclass(frozen=True)
class RejectionEvidence:
    artifact_id: str
    source_row: int
    reason_code: str
    source_identity_sha256: str


@dataclass(frozen=True)
class OpeningStatePlan:
    package_id: str
    manifest_sha256: str
    transformation_version: str
    target_company_id: str
    target_branch_ids: tuple[str, ...]
    journal_lines: tuple[JournalLine, ...]
    controls: tuple[ControlTie, ...]
    row_accounting: tuple[RowAccounting, ...]
    rejections: tuple[RejectionEvidence, ...] = ()


@dataclass(frozen=True)
class RehearsalResult:
    idempotency_key: str
    plan_sha256: str
    audit_sha256: str
    manifest_sha256: str
    transformation_version: str
    accepted_rows: int
    rejected_rows: int
    staged_records: int
    committed_records: int
    delta_records: int
    replayed: bool
    rolled_back: bool
    archive_artifact_ids: tuple[str, ...]


class RehearsalTarget(Protocol):
    """A target adapter must stage and then prove rollback without committing."""

    @property
    def committed_records(self) -> int: ...

    def stage(self, plan: OpeningStatePlan) -> int: ...

    def rollback(self) -> None: ...


class OpeningStateTransformer(Protocol):
    """Provider-neutral seam; real-field implementations require source evidence."""

    @property
    def transformation_version(self) -> str: ...

    def transform(self, package: OpeningPackage) -> OpeningStatePlan: ...


class RollbackOnlyTarget:
    """Synthetic adapter that cannot commit and exposes rollback evidence."""

    def __init__(self, *, fail_after_stage: bool = False) -> None:
        self._staged = 0
        self._committed = 0
        self._fail_after_stage = fail_after_stage

    @property
    def committed_records(self) -> int:
        return self._committed

    @property
    def staged_records(self) -> int:
        return self._staged

    def stage(self, plan: OpeningStatePlan) -> int:
        self._staged = len(plan.journal_lines)
        if self._fail_after_stage:
            raise RuntimeError("synthetic_target_failure")
        return self._staged

    def rollback(self) -> None:
        self._staged = 0


class InMemoryCheckpointStore:
    """Append-only process-local evidence; persistence awaits target schemas."""

    def __init__(self) -> None:
        self._completed: dict[str, RehearsalResult] = {}
        self._attempts: list[tuple[str, str]] = []

    def completed(self, key: str) -> RehearsalResult | None:
        return self._completed.get(key)

    def record_attempt(self, key: str, state: str) -> None:
        self._attempts.append((key, state))

    def record_completed(self, key: str, result: RehearsalResult) -> None:
        existing = self._completed.get(key)
        if existing is not None and existing != result:
            raise RuntimeValidationError("contradictory_replay")
        self._completed[key] = result
        self._attempts.append((key, "completed"))

    @property
    def attempts(self) -> tuple[tuple[str, str], ...]:
        return tuple(self._attempts)


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(raw).hexdigest()


class OpeningMigrationRuntime:
    """Pure reconciliation and rollback-only orchestration for synthetic inputs."""

    def __init__(self, *, checkpoints: InMemoryCheckpointStore | None = None) -> None:
        self._checkpoints = checkpoints or InMemoryCheckpointStore()

    @staticmethod
    def _validate_money(value: Decimal) -> None:
        if not value.is_finite():
            raise RuntimeValidationError("invalid_money")

    @classmethod
    def _validate_plan(cls, package: OpeningPackage, plan: OpeningStatePlan) -> None:
        if (
            plan.package_id != package.package_id
            or plan.manifest_sha256 != package.manifest_sha256
            or plan.transformation_version != package.transformation_version
        ):
            raise RuntimeValidationError("plan_manifest_identity_mismatch")
        if plan.target_company_id != package.binding.target_company_id or tuple(
            sorted(plan.target_branch_ids)
        ) != package.binding.branch_ids:
            raise RuntimeValidationError("plan_company_branch_mismatch")
        if not plan.journal_lines:
            raise RuntimeValidationError("opening_journal_missing")

        artifact_ids = {artifact.artifact_id for artifact in package.artifacts}
        primary = {
            artifact.artifact_id: artifact
            for artifact in package.artifacts
            if artifact.role == "primary_source" and artifact.state == "accepted"
        }
        line_ids: set[str] = set()
        debits = Decimal(0)
        credits = Decimal(0)
        for line in plan.journal_lines:
            if not line.line_id or line.line_id in line_ids:
                raise RuntimeValidationError("duplicate_journal_line")
            if not line.account_source_id:
                raise RuntimeValidationError("journal_account_identity_missing")
            line_ids.add(line.line_id)
            cls._validate_money(line.debit)
            cls._validate_money(line.credit)
            if line.debit < 0 or line.credit < 0 or (line.debit == 0) == (line.credit == 0):
                raise RuntimeValidationError("invalid_debit_credit_line")
            if line.branch_id not in package.binding.branch_ids:
                raise RuntimeValidationError("journal_branch_mismatch")
            if line.source_artifact_id not in primary or line.source_row < 1:
                raise RuntimeValidationError("journal_provenance_missing")
            debits += line.debit
            credits += line.credit
        if debits != credits:
            raise RuntimeValidationError("opening_journal_unbalanced")

        if not plan.controls:
            raise RuntimeValidationError("control_ties_missing")
        control_ids: set[str] = set()
        for control in plan.controls:
            if not control.control_id or control.control_id in control_ids:
                raise RuntimeValidationError("duplicate_control_tie")
            control_ids.add(control.control_id)
            cls._validate_money(control.source_amount)
            cls._validate_money(control.opening_amount)
            if control.source_amount != control.opening_amount:
                raise RuntimeValidationError("control_account_mismatch")
            if control.source_artifact_id not in primary:
                raise RuntimeValidationError("control_provenance_missing")

        rejection_keys = {
            (item.artifact_id, item.source_row) for item in plan.rejections
        }
        if len(rejection_keys) != len(plan.rejections):
            raise RuntimeValidationError("duplicate_rejection_evidence")
        for rejection in plan.rejections:
            if (
                rejection.artifact_id not in artifact_ids
                or rejection.source_row < 1
                or not rejection.reason_code
                or len(rejection.source_identity_sha256) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in rejection.source_identity_sha256
                )
            ):
                raise RuntimeValidationError("rejection_not_explainable")

        row_ids: set[str] = set()
        rejected_total = 0
        for rows in plan.row_accounting:
            if rows.artifact_id in row_ids or rows.artifact_id not in primary:
                raise RuntimeValidationError("invalid_row_accounting_artifact")
            row_ids.add(rows.artifact_id)
            if min(rows.source, rows.accepted, rows.rejected, rows.pending_disposition) < 0:
                raise RuntimeValidationError("invalid_row_accounting")
            if rows.source != rows.accepted + rows.rejected + rows.pending_disposition:
                raise RuntimeValidationError("row_accounting_mismatch")
            if rows.pending_disposition:
                raise RuntimeValidationError("pending_finance_disposition")
            source = primary[rows.artifact_id]
            if (
                rows.source != source.source_rows
                or rows.accepted != source.accepted_rows
                or rows.rejected != source.rejected_rows
                or rows.pending_disposition != source.pending_rows
            ):
                raise RuntimeValidationError("manifest_plan_row_accounting_mismatch")
            rejected_total += rows.rejected
        if row_ids != set(primary):
            raise RuntimeValidationError("row_accounting_incomplete")
        if rejected_total != len(plan.rejections):
            raise RuntimeValidationError("rejection_evidence_count_mismatch")

    @staticmethod
    def _plan_payload(plan: OpeningStatePlan) -> dict[str, object]:
        return asdict(plan)

    def run(
        self,
        package: OpeningPackage,
        plan: OpeningStatePlan,
        *,
        target: RehearsalTarget,
    ) -> RehearsalResult:
        self._validate_plan(package, plan)
        plan_sha256 = _canonical_digest(self._plan_payload(plan))
        idempotency_key = _canonical_digest(
            {
                "source_company_id": package.binding.source_company_id,
                "package_id": package.package_id,
                "manifest_sha256": package.manifest_sha256,
                "transformation_version": package.transformation_version,
                "target_company_id": package.binding.target_company_id,
                "mode": "synthetic_rollback_only",
            }
        )
        completed = self._checkpoints.completed(idempotency_key)
        if completed is not None:
            if completed.plan_sha256 != plan_sha256:
                raise RuntimeValidationError("contradictory_replay")
            return RehearsalResult(
                **{
                    **asdict(completed),
                    "delta_records": 0,
                    "replayed": True,
                }
            )

        self._checkpoints.record_attempt(idempotency_key, "started")
        staged = 0
        try:
            staged = target.stage(plan)
        except Exception:
            self._checkpoints.record_attempt(idempotency_key, "failed")
            raise
        finally:
            target.rollback()
        if target.committed_records != 0:
            raise RuntimeValidationError("rollback_committed_target_mutation")

        accepted_rows = sum(item.accepted for item in plan.row_accounting)
        rejected_rows = sum(item.rejected for item in plan.row_accounting)
        evidence = {
            "idempotency_key": idempotency_key,
            "plan_sha256": plan_sha256,
            "manifest_sha256": package.manifest_sha256,
            "transformation_version": package.transformation_version,
            "accepted_rows": accepted_rows,
            "rejected_rows": rejected_rows,
            "staged_records": staged,
            "committed_records": 0,
            "rolled_back": True,
            "archive_artifact_ids": package.archive_artifact_ids,
        }
        result = RehearsalResult(
            idempotency_key=idempotency_key,
            plan_sha256=plan_sha256,
            audit_sha256=_canonical_digest(evidence),
            manifest_sha256=package.manifest_sha256,
            transformation_version=package.transformation_version,
            accepted_rows=accepted_rows,
            rejected_rows=rejected_rows,
            staged_records=staged,
            committed_records=0,
            delta_records=staged,
            replayed=False,
            rolled_back=True,
            archive_artifact_ids=package.archive_artifact_ids,
        )
        self._checkpoints.record_completed(idempotency_key, result)
        return result

    def transform_and_run(
        self,
        package: OpeningPackage,
        *,
        transformer: OpeningStateTransformer,
        target: RehearsalTarget,
    ) -> RehearsalResult:
        if transformer.transformation_version != package.transformation_version:
            raise RuntimeValidationError("transformation_version_mismatch")
        return self.run(package, transformer.transform(package), target=target)
