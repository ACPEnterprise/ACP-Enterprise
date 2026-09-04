from types import SimpleNamespace
from uuid import UUID

import pytest

from app.operational_migration.hcp_migration2b import (
    SOURCE4_PACKAGE_DIGEST,
    MasterRunCommand,
)
from app.operational_migration.hcp_migration2c import (
    ORCHESTRATOR_VERSION,
    CompletionRequirements,
    EmployeeCandidateCommand,
)
from app.operational_migration.hcp_owner_disposition import NonProductionTarget
from app.operational_migration.hcp_rehearsal_authority import (
    ACTOR_ID,
    BRANCH_ID,
    COMPANY_ID,
    require_sanctioned_context,
    require_sanctioned_target,
)
from app.operational_migration.models import OperationalMigrationRun


class Context:
    def __init__(
        self,
        *,
        company_id: UUID = COMPANY_ID,
        branch_id: UUID = BRANCH_ID,
        actor_id: UUID = ACTOR_ID,
        permitted: bool = True,
        company_status: str = "active",
        branch_status: str = "active",
        actor_status: str = "active",
        membership_status: str = "active",
        membership_company_id: UUID | None = None,
        membership_actor_id: UUID | None = None,
        branch_company_id: UUID | None = None,
        accessible: bool = True,
    ) -> None:
        self.company = SimpleNamespace(id=company_id, status=company_status)
        self.active_branch = SimpleNamespace(
            id=branch_id,
            company_id=branch_company_id or company_id,
            status=branch_status,
        )
        self.user = SimpleNamespace(id=actor_id, status=actor_status)
        self.membership = SimpleNamespace(
            company_id=membership_company_id or company_id,
            user_id=membership_actor_id or actor_id,
            status=membership_status,
        )
        self._permitted = permitted
        self._accessible = accessible

    def can_access_branch(self, branch_id: UUID) -> bool:
        return self._accessible and branch_id == self.active_branch.id

    def has_permission(self, _permission: object) -> bool:
        return self._permitted


def master_command() -> MasterRunCommand:
    return MasterRunCommand(
        package_digest=SOURCE4_PACKAGE_DIGEST,
        collection_digests={"customers": "a" * 64},
        transformation_contracts={
            "customers": "hcp-source4-customer/v1",
            "hybrid_customer_admission_digest": "6" * 64,
            "customer_parent_closure_digest": "7" * 64,
        },
        owner_receipts={f"receipt-{index}": str(index) * 64 for index in range(1, 6)},
        schema_head="f3a5c7e9b102",
        implementation_version=ORCHESTRATOR_VERSION,
        supported_entities=(
            "customer",
            "contact",
            "service_location",
            "employee",
            "job",
            "appointment",
            "estimate",
            "invoice",
            "payment",
            "note",
        ),
        baseline_counts={"customer": 0, "job": 0},
        source_counts={"customer": 1, "job": 2},
    )


def test_current_master_command_is_deterministic_and_schema_bound() -> None:
    command = master_command()
    command.validate()
    assert command.schema_head == "f3a5c7e9b102"
    assert command.implementation_version == ORCHESTRATOR_VERSION


def test_source4_operational_run_contract_requires_master_and_domain() -> None:
    constraints = {
        item.name: str(item.sqltext)
        for item in OperationalMigrationRun.__table__.constraints
        if getattr(item, "sqltext", None) is not None
    }
    assert (
        "master_run_id IS NOT NULL"
        in constraints["ck_operational_source4_master_required"]
    )
    assert "master_domain" in constraints["ck_operational_source4_master_required"]


def test_reconciliation_requires_every_source_subject_to_have_one_outcome() -> None:
    requirements = CompletionRequirements(
        customer_lineage=1,
        location_identities=1,
        location_exceptions=0,
        employee_crosswalks=7,
        employee_candidates=6,
        employee_excluded=1,
        note_outcomes={
            "persisted": 2640,
            "duplicate": 0,
            "exception": 0,
            "rejected": 0,
        },
        holds_by_code={"HOLD_OPERATIONAL_RECONCILE_BALANCE": 1},
        hold_counts={"job": 1},
        unlinked_estimates=24,
        transformed_counts={"customer": 1, "job": 2},
        persisted_counts={"customer": 1, "job": 1},
        exception_counts={},
        rejection_counts={},
        unresolved_counts={},
        non_applicable_counts={},
    )
    requirements.validate_reconciliation({"customer": 1, "job": 2})
    with pytest.raises(ValueError, match="aggregate reconciliation mismatch"):
        requirements.validate_reconciliation({"customer": 2, "job": 2})


@pytest.mark.parametrize(
    "context",
    (
        Context(membership_actor_id=UUID(int=3)),
        Context(branch_company_id=UUID(int=2)),
        Context(membership_company_id=UUID(int=1)),
        Context(accessible=False),
        Context(permitted=False),
        Context(company_status="inactive"),
        Context(branch_status="inactive"),
        Context(actor_status="disabled"),
        Context(membership_status="revoked"),
    ),
)
def test_spoofed_cross_company_inactive_or_unpermitted_context_is_rejected(
    context: Context,
) -> None:
    with pytest.raises(ValueError, match="sanctioned"):
        require_sanctioned_context(context)  # type: ignore[arg-type]


def test_preview_production_and_remote_targets_are_rejected() -> None:
    with pytest.raises(ValueError):
        require_sanctioned_target(
            NonProductionTarget(
                environment="migration_rehearsal",
                database_url="postgresql://actor@production/acp_hcp_rehearsal_import",
                expected_database="acp_hcp_rehearsal_import",
                production_access_enabled=False,
                preview_access_enabled=False,
                initially_empty_required=True,
            )
        )


def test_sanctioned_context_is_exact() -> None:
    require_sanctioned_context(Context())  # type: ignore[arg-type]


def test_employee_candidate_requires_explicit_human_identity() -> None:
    EmployeeCandidateCommand(
        native_employee_id="pro_human",
        disposition="CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE",
        source_digest="a" * 64,
        owner_receipt_digest="b" * 64,
        first_name="Approved",
        last_name="Human",
        display_name="Approved Human",
    ).validate()
    with pytest.raises(ValueError, match="identity is incomplete"):
        EmployeeCandidateCommand(
            native_employee_id="pro_human",
            disposition="CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE",
            source_digest="a" * 64,
            owner_receipt_digest="b" * 64,
        ).validate()


def test_excluded_employee_identity_cannot_carry_candidate_fields() -> None:
    EmployeeCandidateCommand(
        native_employee_id="pro_lokal",
        disposition="EXCLUDE_EMPLOYEE_HOLD_ASSIGNMENTS",
        source_digest="a" * 64,
        owner_receipt_digest="b" * 64,
    ).validate()
    with pytest.raises(ValueError, match="cannot carry Employee"):
        EmployeeCandidateCommand(
            native_employee_id="pro_lokal",
            disposition="EXCLUDE_EMPLOYEE_HOLD_ASSIGNMENTS",
            source_digest="a" * 64,
            owner_receipt_digest="b" * 64,
            display_name="Not an Employee",
        ).validate()
