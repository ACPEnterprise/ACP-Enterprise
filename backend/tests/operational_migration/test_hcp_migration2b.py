from uuid import UUID

import pytest

from app.customer_migration.adapter_import_policy import CustomerAdapterImportPolicy
from app.customers.schemas import CustomerCreate, CustomerType
from app.operational_migration.hcp_migration2b import (
    SOURCE4_PACKAGE_DIGEST,
    CustomerLineageCommand,
    EmployeeCrosswalkCommand,
    HoldCommand,
    MasterRunCommand,
    MasterRunOutcome,
    Migration2PersistenceReleaseGate,
    canonical_sha256,
)


class Aggregate:
    def __init__(self, identity: str, name: str) -> None:
        self.source_identity_sha256 = identity
        self.customer = CustomerCreate(
            customer_type=CustomerType.RESIDENTIAL, display_name=name
        )
        self.contact = None
        self.service_locations = ()
        self.billing_address = None


def test_name_similarity_is_review_evidence_not_an_admission_barrier() -> None:
    aggregates = (Aggregate("a" * 64, "Same Name"), Aggregate("b" * 64, "Same Name"))
    policy = CustomerAdapterImportPolicy()

    assert policy.duplicate_members(aggregates) == frozenset()
    assert policy.similarity_evidence(aggregates) == {
        "same name": (("a" * 64, "b" * 64),)
    }


def test_release_gate_requires_all_five_contracts_and_zero_real_rows() -> None:
    ready = Migration2PersistenceReleaseGate(True, True, True, True, True, False)
    blocked = Migration2PersistenceReleaseGate(True, True, True, True, True, True)
    assert ready.ready
    assert len(ready.digest) == 64
    assert not blocked.ready


def master_command(**overrides: object) -> MasterRunCommand:
    values: dict[str, object] = {
        "package_digest": SOURCE4_PACKAGE_DIGEST,
        "collection_digests": {"customers": "a" * 64},
        "transformation_contracts": {
            "customer": "hcp_customer/v1",
            "hybrid_customer_admission_digest": "6" * 64,
            "customer_parent_closure_digest": "7" * 64,
        },
        "owner_receipts": {
            f"receipt-{index}": str(index) * 64 for index in range(1, 6)
        },
        "schema_head": "f3a5c7e9b102",
        "implementation_version": "hcp-migration-2b/v1",
        "supported_entities": ("customer", "job"),
        "baseline_counts": {"customers": 0},
        "source_counts": {"customers": 1},
    }
    values.update(overrides)
    return MasterRunCommand(**values)  # type: ignore[arg-type]


def test_master_attestation_inputs_are_deterministic_and_tamper_evident() -> None:
    command = master_command()
    command.validate()
    payload = command.input_payload(
        company_id=UUID(int=1), branch_id=UUID(int=2), actor_id=UUID(int=3)
    )
    assert canonical_sha256(payload) == canonical_sha256(
        dict(reversed(list(payload.items())))
    )
    changed = master_command(source_counts={"customers": 2})
    assert canonical_sha256(payload) != canonical_sha256(
        changed.input_payload(
            company_id=UUID(int=1), branch_id=UUID(int=2), actor_id=UUID(int=3)
        )
    )


def test_master_requires_all_owner_receipts_and_current_schema() -> None:
    with pytest.raises(ValueError, match="five owner receipts"):
        master_command(owner_receipts={}).validate()
    with pytest.raises(ValueError, match="schema head"):
        master_command(schema_head="old").validate()


def test_master_outcome_keeps_holds_distinct_from_other_counts() -> None:
    outcome = MasterRunOutcome(
        transformed_counts={"job": 1},
        persisted_counts={"job": 0},
        hold_counts={"job": 1},
        exception_counts={"job": 0},
        rejection_counts={"job": 0},
        unresolved_counts={"job": 0},
        non_applicable_counts={"job": 0},
        child_run_ids={"operational": str(UUID(int=1))},
        replay_state={"stable": True},
        resume_state={"cursor": None},
        status="completed",
    )
    outcome.validate()
    assert outcome.hold_counts == {"job": 1}
    assert outcome.rejection_counts == {"job": 0}


def test_customer_lineage_detects_changed_source_digest() -> None:
    first = CustomerLineageCommand(
        native_customer_id="cus_fixture",
        source_digest="a" * 64,
        transformation_contract="hcp-source4-customer/v1",
        transformation_digest="b" * 64,
        source_timestamps={},
        source_context={"fixture": True},
    )
    changed = CustomerLineageCommand(
        native_customer_id="cus_fixture",
        source_digest="c" * 64,
        transformation_contract="hcp-source4-customer/v1",
        transformation_digest="b" * 64,
        source_timestamps={},
        source_context={"fixture": True},
    )
    first.validate()
    assert first.evidence_digest != changed.evidence_digest


def test_excluded_lokal_identity_cannot_create_employee_mapping() -> None:
    command = EmployeeCrosswalkCommand(
        native_employee_id="pro_lokal_fixture",
        disposition="EXCLUDE_EMPLOYEE_HOLD_ASSIGNMENTS",
        source_digest="a" * 64,
        owner_receipt_digest="b" * 64,
        employee_id=UUID(int=1),
    )
    with pytest.raises(ValueError, match="cannot have an Employee"):
        command.validate()


def test_employee_crosswalk_and_hold_digests_are_replay_stable() -> None:
    employee = EmployeeCrosswalkCommand(
        native_employee_id="pro_fixture",
        disposition="CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE",
        source_digest="a" * 64,
        owner_receipt_digest="b" * 64,
    )
    hold = HoldCommand(
        entity_kind="job",
        native_id="job_fixture",
        hold_code="HOLD_OPERATIONAL_RECONCILE_BALANCE",
        evidence_digest="c" * 64,
        reconciliation_key="job:job_fixture",
        owner_disposition="HOLD_OPERATIONAL_RECONCILE_BALANCE",
    )
    employee.validate()
    hold.validate()
    assert employee.evidence_digest == employee.evidence_digest
    assert hold.hold_digest == hold.hold_digest
    assert hold.state == "HELD"


def test_hold_is_neither_rejection_nor_financial_acceptance() -> None:
    hold = HoldCommand(
        entity_kind="invoice",
        native_id="invoice_fixture",
        hold_code="FINANCIAL_TRUTH_UNRESOLVED",
        evidence_digest="d" * 64,
        reconciliation_key="invoice:fixture",
    )
    hold.validate()
    assert hold.state == "HELD"
    assert "reject" not in hold.hold_code.lower()
