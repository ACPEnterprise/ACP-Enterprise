"""Source-faithful admission and attestation contracts for HCP.MIGRATION.2."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_migration.adapter_import import ReviewedCustomerAdapterOutput
from app.customer_migration.adapter_import_policy import CustomerAdapterImportPolicy
from app.operational_migration.hcp_rehearsal_authority import require_sanctioned_context
from app.operational_migration.models import (
    HcpCustomerSourceLineage,
    HcpEmployeeSourceCrosswalk,
    HcpMigrationHold,
    HcpMigrationMasterRun,
)
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext

SOURCE4_PACKAGE_DIGEST = (
    "f77e3e09457efcbf6d42137be1af43be6ad0adbea8eab2c12ca320730fd96901"
)
MASTER_NAMESPACE = UUID("af77a4be-0120-5fad-bb22-b11cc9f032b8")
MASTER_CONTRACT = "hcp-migration-master-run/v1"
CUSTOMER_LINEAGE_CONTRACT = "hcp-source4-customer-lineage/v1"
EMPLOYEE_CROSSWALK_CONTRACT = "hcp-employee-crosswalk/v1"
HOLD_CONTRACT = "hcp-migration-hold/v1"


@dataclass(frozen=True)
class Migration2PersistenceReleaseGate:
    customer_admission_qualified: bool
    customer_lineage_qualified: bool
    employee_crosswalk_qualified: bool
    durable_holds_qualified: bool
    master_attestation_qualified: bool
    target_has_real_hcp_business_rows: bool

    @property
    def ready(self) -> bool:
        return all(
            (
                self.customer_admission_qualified,
                self.customer_lineage_qualified,
                self.employee_crosswalk_qualified,
                self.durable_holds_qualified,
                self.master_attestation_qualified,
                not self.target_has_real_hcp_business_rows,
            )
        )

    @property
    def digest(self) -> str:
        return canonical_sha256(
            {"contract": "hcp-migration-2-persistence-release/v1", **asdict(self)}
        )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _digest(value: str, field: str) -> str:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _authorized(context: AuthorizationContext) -> None:
    require_sanctioned_context(context)


@dataclass(frozen=True)
class CustomerAdmissionQualification:
    source: int
    parent_admissible: int
    source_rejected: int
    source_duplicate: int
    child_exception_identities: int
    multi_location_parents: int
    similarity_review_identities: int


def qualify_customer_admission(
    reviewed: ReviewedCustomerAdapterOutput,
    *,
    policy: CustomerAdapterImportPolicy | None = None,
) -> CustomerAdmissionQualification:
    """Qualify parents independently; profile similarity never blocks admission."""
    reviewed.validate_integrity()
    selected_policy = policy or CustomerAdapterImportPolicy()
    rejected = set(reviewed.rejected_source_identities)
    duplicates = set(reviewed.duplicate_source_identities)
    clusters = selected_policy.similarity_evidence(reviewed.aggregates)
    review_identities = {
        identity
        for values in clusters.values()
        for cluster in values
        for identity in cluster
    }
    admissible = [
        item
        for item in reviewed.aggregates
        if item.source_identity_sha256 not in rejected | duplicates
    ]
    return CustomerAdmissionQualification(
        source=reviewed.source_count,
        parent_admissible=len(admissible),
        source_rejected=reviewed.rejected_count,
        source_duplicate=reviewed.duplicate_count,
        child_exception_identities=len(reviewed.child_exception_source_identities),
        multi_location_parents=sum(
            len(item.service_locations) > 1 for item in admissible
        ),
        similarity_review_identities=len(review_identities),
    )


@dataclass(frozen=True)
class MasterRunCommand:
    package_digest: str
    collection_digests: dict[str, object]
    transformation_contracts: dict[str, object]
    owner_receipts: dict[str, object]
    schema_head: str
    implementation_version: str
    supported_entities: tuple[str, ...]
    baseline_counts: dict[str, int]
    source_counts: dict[str, int]

    def input_payload(
        self, *, company_id: UUID, branch_id: UUID, actor_id: UUID
    ) -> dict[str, object]:
        return {
            "contract": MASTER_CONTRACT,
            "company_id": str(company_id),
            "branch_id": str(branch_id),
            "actor_id": str(actor_id),
            **asdict(self),
        }

    def validate(self) -> None:
        _digest(self.package_digest, "package_digest")
        if self.package_digest != SOURCE4_PACKAGE_DIGEST:
            raise ValueError("unexpected SOURCE.4 package digest")
        if not self.collection_digests or not self.transformation_contracts:
            raise ValueError("collection and transformation bindings are required")
        for binding in (
            "hybrid_customer_admission_digest",
            "customer_parent_closure_digest",
        ):
            value = self.transformation_contracts.get(binding)
            if not isinstance(value, str):
                raise TypeError(f"{binding} is required")
            _digest(value, binding)
        if len(self.owner_receipts) != 5:
            raise ValueError("all five owner receipts are required")
        for value in self.owner_receipts.values():
            _digest(str(value), "owner_receipt")
        if self.schema_head != "e2f4a6b8c091":
            raise ValueError("unexpected rehearsal schema head")
        if not self.supported_entities or len(self.supported_entities) != len(
            set(self.supported_entities)
        ):
            raise ValueError("supported entity set must be explicit and unique")
        for counts in (self.baseline_counts, self.source_counts):
            if any(value < 0 for value in counts.values()):
                raise ValueError("attestation counts cannot be negative")


async def prepare_master_run(
    session: AsyncSession,
    *,
    context: AuthorizationContext,
    command: MasterRunCommand,
) -> tuple[HcpMigrationMasterRun, bool]:
    _authorized(context)
    command.validate()
    assert context.active_branch is not None
    payload = command.input_payload(
        company_id=context.company.id,
        branch_id=context.active_branch.id,
        actor_id=context.user.id,
    )
    input_digest = canonical_sha256(payload)
    run_id = uuid5(MASTER_NAMESPACE, input_digest)
    existing = await session.get(HcpMigrationMasterRun, run_id)
    if existing is not None:
        if (
            existing.input_digest != input_digest
            or existing.package_digest != command.package_digest
            or existing.owner_receipts != command.owner_receipts
            or existing.transformation_contracts != command.transformation_contracts
            or existing.actor_user_id != context.user.id
            or existing.company_id != context.company.id
            or existing.branch_id != context.active_branch.id
        ):
            raise ValueError("master run attestation conflict")
        if (
            existing.status == "prepared"
            and existing.attestation_digest
            != canonical_sha256({"input": payload, "status": "prepared"})
        ):
            raise ValueError("prepared master run attestation was changed")
        return existing, False
    run = HcpMigrationMasterRun(
        id=run_id,
        company_id=context.company.id,
        branch_id=context.active_branch.id,
        actor_user_id=context.user.id,
        package_digest=command.package_digest,
        collection_digests=command.collection_digests,
        transformation_contracts=command.transformation_contracts,
        owner_receipts=command.owner_receipts,
        schema_head=command.schema_head,
        implementation_version=command.implementation_version,
        supported_entities=sorted(command.supported_entities),
        baseline_counts=command.baseline_counts,
        source_counts=command.source_counts,
        transformed_counts={},
        persisted_counts={},
        hold_counts={},
        exception_counts={},
        rejection_counts={},
        unresolved_counts={},
        non_applicable_counts={},
        child_run_ids={},
        reconciliation_digest=None,
        replay_state={"attempt": 0, "state": "not_started"},
        resume_state={"cursor": None, "state": "not_started"},
        rollback_state={"business_rows": "not_requested", "audit_evidence": "retained"},
        input_digest=input_digest,
        attestation_digest=canonical_sha256({"input": payload, "status": "prepared"}),
        status="prepared",
        started_at=datetime.now(timezone.utc),
        completed_at=None,
    )
    session.add(run)
    await session.flush()
    return run, True


@dataclass(frozen=True)
class MasterRunOutcome:
    transformed_counts: dict[str, int]
    persisted_counts: dict[str, int]
    hold_counts: dict[str, int]
    exception_counts: dict[str, int]
    rejection_counts: dict[str, int]
    unresolved_counts: dict[str, int]
    non_applicable_counts: dict[str, int]
    child_run_ids: dict[str, str]
    replay_state: dict[str, object]
    resume_state: dict[str, object]
    status: str

    def validate(self) -> None:
        if self.status not in {"interrupted", "completed", "failed"}:
            raise ValueError("unsupported master run terminal state")
        for counts in (
            self.transformed_counts,
            self.persisted_counts,
            self.hold_counts,
            self.exception_counts,
            self.rejection_counts,
            self.unresolved_counts,
            self.non_applicable_counts,
        ):
            if any(value < 0 for value in counts.values()):
                raise ValueError("master outcome counts cannot be negative")


async def attest_master_run_outcome(
    session: AsyncSession,
    *,
    context: AuthorizationContext,
    run_id: UUID,
    expected_input_digest: str,
    outcome: MasterRunOutcome,
) -> HcpMigrationMasterRun:
    _authorized(context)
    outcome.validate()
    run = await session.scalar(
        select(HcpMigrationMasterRun)
        .where(HcpMigrationMasterRun.id == run_id)
        .with_for_update()
    )
    if (
        run is None
        or run.company_id != context.company.id
        or context.active_branch is None
        or run.branch_id != context.active_branch.id
        or run.actor_user_id != context.user.id
        or run.input_digest != _digest(expected_input_digest, "expected_input_digest")
    ):
        raise ValueError("master run identity or scope mismatch")
    values = asdict(outcome)
    reconciliation = canonical_sha256(
        {"input_digest": run.input_digest, "outcome": values}
    )
    expected_attestation = canonical_sha256(
        {
            "contract": MASTER_CONTRACT,
            "run_id": str(run.id),
            "input_digest": run.input_digest,
            "reconciliation_digest": reconciliation,
            "outcome": values,
        }
    )
    if run.status in {"completed", "failed"}:
        if run.attestation_digest != expected_attestation:
            raise ValueError("terminal master run attestation conflict")
        return run
    run.transformed_counts = outcome.transformed_counts
    run.persisted_counts = outcome.persisted_counts
    run.hold_counts = outcome.hold_counts
    run.exception_counts = outcome.exception_counts
    run.rejection_counts = outcome.rejection_counts
    run.unresolved_counts = outcome.unresolved_counts
    run.non_applicable_counts = outcome.non_applicable_counts
    run.child_run_ids = outcome.child_run_ids
    run.replay_state = outcome.replay_state
    run.resume_state = outcome.resume_state
    run.reconciliation_digest = reconciliation
    run.status = outcome.status
    run.attestation_digest = expected_attestation
    run.completed_at = (
        None if outcome.status == "interrupted" else datetime.now(timezone.utc)
    )
    await session.flush()
    return run


@dataclass(frozen=True)
class CustomerLineageCommand:
    native_customer_id: str
    source_digest: str
    transformation_contract: str
    transformation_digest: str
    source_timestamps: dict[str, object]
    source_context: dict[str, object]
    customer_source_identity_id: UUID | None = None
    owner_disposition: str | None = None
    package_digest: str = SOURCE4_PACKAGE_DIGEST

    @property
    def evidence_digest(self) -> str:
        return canonical_sha256({"contract": CUSTOMER_LINEAGE_CONTRACT, **asdict(self)})

    def validate(self) -> None:
        if not self.native_customer_id.startswith("cus_"):
            raise ValueError("native HCP Customer identity is required")
        for field, value in (
            ("package_digest", self.package_digest),
            ("source_digest", self.source_digest),
            ("transformation_digest", self.transformation_digest),
        ):
            _digest(value, field)
        if self.package_digest != SOURCE4_PACKAGE_DIGEST:
            raise ValueError("unexpected SOURCE.4 package digest")
        if not self.transformation_contract:
            raise ValueError("Customer transformation contract is required")


async def persist_customer_lineage(
    session: AsyncSession,
    *,
    context: AuthorizationContext,
    master_run_id: UUID,
    command: CustomerLineageCommand,
) -> tuple[HcpCustomerSourceLineage, bool]:
    _authorized(context)
    command.validate()
    existing = await session.scalar(
        select(HcpCustomerSourceLineage).where(
            HcpCustomerSourceLineage.company_id == context.company.id,
            HcpCustomerSourceLineage.native_customer_id == command.native_customer_id,
        )
    )
    if existing is not None:
        if existing.evidence_digest != command.evidence_digest:
            raise ValueError("native Customer identity has changed source evidence")
        return existing, False
    assert context.active_branch is not None
    row = HcpCustomerSourceLineage(
        company_id=context.company.id,
        branch_id=context.active_branch.id,
        master_run_id=master_run_id,
        customer_source_identity_id=command.customer_source_identity_id,
        native_customer_id=command.native_customer_id,
        package_digest=command.package_digest,
        source_digest=command.source_digest,
        transformation_contract=command.transformation_contract,
        transformation_digest=command.transformation_digest,
        owner_disposition=command.owner_disposition,
        source_timestamps=command.source_timestamps,
        source_context=command.source_context,
        evidence_digest=command.evidence_digest,
    )
    session.add(row)
    await session.flush()
    return row, True


@dataclass(frozen=True)
class EmployeeCrosswalkCommand:
    native_employee_id: str
    disposition: str
    source_digest: str
    owner_receipt_digest: str
    employee_id: UUID | None = None
    prior_evidence_id: UUID | None = None
    evidence_version: int = 1
    package_digest: str = SOURCE4_PACKAGE_DIGEST

    @property
    def evidence_digest(self) -> str:
        return canonical_sha256(
            {"contract": EMPLOYEE_CROSSWALK_CONTRACT, **asdict(self)}
        )

    def validate(self) -> None:
        if not self.native_employee_id.startswith("pro_"):
            raise ValueError("native HCP Employee identity is required")
        if self.disposition not in {
            "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE",
            "EXCLUDE_EMPLOYEE_HOLD_ASSIGNMENTS",
        }:
            raise ValueError("unsupported Employee disposition")
        if self.disposition == "EXCLUDE_EMPLOYEE_HOLD_ASSIGNMENTS" and self.employee_id:
            raise ValueError("excluded non-human identity cannot have an Employee")
        if self.evidence_version < 1 or (self.evidence_version > 1) != bool(
            self.prior_evidence_id
        ):
            raise ValueError("Employee evidence version lineage is invalid")
        for field, value in (
            ("package_digest", self.package_digest),
            ("source_digest", self.source_digest),
            ("owner_receipt_digest", self.owner_receipt_digest),
        ):
            _digest(value, field)


async def persist_employee_crosswalk(
    session: AsyncSession,
    *,
    context: AuthorizationContext,
    master_run_id: UUID,
    command: EmployeeCrosswalkCommand,
) -> tuple[HcpEmployeeSourceCrosswalk, bool]:
    _authorized(context)
    command.validate()
    if command.employee_id is not None:
        target = await session.get(Employee, command.employee_id)
        if target is None or target.company_id != context.company.id:
            raise ValueError("Employee mapping target is outside Company scope")
    existing = await session.scalar(
        select(HcpEmployeeSourceCrosswalk).where(
            HcpEmployeeSourceCrosswalk.company_id == context.company.id,
            HcpEmployeeSourceCrosswalk.evidence_digest == command.evidence_digest,
        )
    )
    if existing is not None:
        return existing, False
    assert context.active_branch is not None
    row = HcpEmployeeSourceCrosswalk(
        company_id=context.company.id,
        branch_id=context.active_branch.id,
        master_run_id=master_run_id,
        prior_evidence_id=command.prior_evidence_id,
        employee_id=command.employee_id,
        native_employee_id=command.native_employee_id,
        disposition=command.disposition,
        package_digest=command.package_digest,
        source_digest=command.source_digest,
        owner_receipt_digest=command.owner_receipt_digest,
        evidence_digest=command.evidence_digest,
        evidence_version=command.evidence_version,
    )
    session.add(row)
    await session.flush()
    return row, True


@dataclass(frozen=True)
class HoldCommand:
    entity_kind: str
    native_id: str
    hold_code: str
    evidence_digest: str
    reconciliation_key: str
    owner_disposition: str | None = None
    state: str = "HELD"
    prior_hold_id: UUID | None = None
    evidence_version: int = 1
    package_digest: str = SOURCE4_PACKAGE_DIGEST

    @property
    def hold_digest(self) -> str:
        return canonical_sha256({"contract": HOLD_CONTRACT, **asdict(self)})

    def validate(self) -> None:
        if not self.entity_kind or not self.native_id or not self.hold_code:
            raise ValueError("hold identity and reason are required")
        if self.state not in {"HELD", "RELEASED"}:
            raise ValueError("unsupported hold state")
        for field, value in (
            ("package_digest", self.package_digest),
            ("evidence_digest", self.evidence_digest),
        ):
            _digest(value, field)
        if self.evidence_version < 1 or (self.evidence_version > 1) != bool(
            self.prior_hold_id
        ):
            raise ValueError("hold evidence version lineage is invalid")


async def persist_hold(
    session: AsyncSession,
    *,
    context: AuthorizationContext,
    master_run_id: UUID,
    command: HoldCommand,
) -> tuple[HcpMigrationHold, bool]:
    _authorized(context)
    command.validate()
    existing = await session.scalar(
        select(HcpMigrationHold).where(
            HcpMigrationHold.company_id == context.company.id,
            HcpMigrationHold.hold_digest == command.hold_digest,
        )
    )
    if existing is not None:
        return existing, False
    assert context.active_branch is not None
    row = HcpMigrationHold(
        company_id=context.company.id,
        branch_id=context.active_branch.id,
        master_run_id=master_run_id,
        prior_hold_id=command.prior_hold_id,
        entity_kind=command.entity_kind,
        native_id=command.native_id,
        hold_code=command.hold_code,
        owner_disposition=command.owner_disposition,
        package_digest=command.package_digest,
        evidence_digest=command.evidence_digest,
        reconciliation_key=command.reconciliation_key,
        state=command.state,
        hold_digest=command.hold_digest,
        evidence_version=command.evidence_version,
        operational_effects_enabled=False,
        financial_truth_accepted=False,
    )
    session.add(row)
    await session.flush()
    return row, True
