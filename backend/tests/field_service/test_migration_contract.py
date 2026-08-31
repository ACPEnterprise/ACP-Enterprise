import ast
from pathlib import Path
from typing import Any

from sqlalchemy import ForeignKeyConstraint

from app.field_service.models import (
    FieldCompletionEvidence,
    FieldCompletionRequirementSnapshot,
    FieldCustomerApproval,
    FieldInvoiceHandoff,
    FieldNonBillableDisposition,
    FieldWorkNote,
)


def test_field_tables_have_closed_idempotency_and_job_contracts() -> None:
    assert {
        FieldWorkNote.__tablename__,
        FieldCustomerApproval.__tablename__,
        FieldInvoiceHandoff.__tablename__,
    } == {"field_work_notes", "field_customer_approvals", "field_invoice_handoffs"}
    for model in (FieldWorkNote, FieldCustomerApproval, FieldInvoiceHandoff):
        assert "company_id" in model.__table__.columns
        assert "job_id" in model.__table__.columns
        assert "idempotency_key" in model.__table__.columns


def test_field_migration_descends_from_authoritative_head() -> None:
    tree = ast.parse(
        Path(
            "alembic/versions/z1q3l5n7r942_create_technician_field_evidence.py"
        ).read_text()
    )
    values = {}
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id in {"revision", "down_revision"}
        ):
            assert node.value is not None
            values[node.target.id] = ast.literal_eval(node.value)
    assert values == {"revision": "z1q3l5n7r942", "down_revision": "y0p2k4m6q831"}


def test_completion_contract_models_are_durable_and_scoped() -> None:
    assert (
        FieldCompletionRequirementSnapshot.__tablename__
        == "field_completion_requirement_snapshots"
    )
    assert FieldCompletionEvidence.__tablename__ == "field_completion_evidence"
    assert (
        FieldNonBillableDisposition.__tablename__ == "field_non_billable_dispositions"
    )
    for model in (
        FieldCompletionRequirementSnapshot,
        FieldCompletionEvidence,
        FieldNonBillableDisposition,
    ):
        assert "company_id" in model.__table__.columns
        assert "job_id" in model.__table__.columns


def test_completion_contract_migration_descends_from_field_head() -> None:
    tree = ast.parse(
        Path(
            "alembic/versions/a2r4m6p8s053_close_field_completion_contract.py"
        ).read_text()
    )
    values = {}
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id in {"revision", "down_revision"}
        ):
            assert node.value is not None
            values[node.target.id] = ast.literal_eval(node.value)
    assert values == {"revision": "a2r4m6p8s053", "down_revision": "z1q3l5n7r942"}


def _foreign_key_columns(model: Any, name: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    constraint = next(
        item
        for item in model.__table__.constraints
        if isinstance(item, ForeignKeyConstraint) and item.name == name
    )
    return (
        tuple(column.name for column in constraint.columns),
        tuple(element.target_fullname for element in constraint.elements),
    )


def test_field_evidence_is_bound_to_exact_parent_scope() -> None:
    assignment_target = (
        "dispatch_assignments.company_id",
        "dispatch_assignments.branch_id",
        "dispatch_assignments.job_id",
        "dispatch_assignments.id",
    )
    for model, name in (
        (FieldWorkNote, "fk_field_notes_assignment_scope"),
        (FieldCustomerApproval, "fk_field_approvals_assignment_scope"),
        (FieldInvoiceHandoff, "fk_field_handoffs_assignment_scope"),
        (
            FieldCompletionRequirementSnapshot,
            "fk_field_requirement_snapshots_assignment_scope",
        ),
        (FieldNonBillableDisposition, "fk_field_non_billable_assignment_scope"),
    ):
        columns, targets = _foreign_key_columns(model, name)
        assert columns == ("company_id", "branch_id", "job_id", "assignment_id")
        assert targets == assignment_target

    assert _foreign_key_columns(
        FieldInvoiceHandoff, "fk_field_handoffs_invoice_scope"
    ) == (
        ("company_id", "branch_id", "job_id", "invoice_id"),
        (
            "invoices.company_id",
            "invoices.branch_id",
            "invoices.job_id",
            "invoices.id",
        ),
    )
    assert _foreign_key_columns(
        FieldCompletionEvidence, "fk_field_completion_evidence_snapshot_scope"
    ) == (
        ("company_id", "branch_id", "job_id", "snapshot_id"),
        (
            "field_completion_requirement_snapshots.company_id",
            "field_completion_requirement_snapshots.branch_id",
            "field_completion_requirement_snapshots.job_id",
            "field_completion_requirement_snapshots.id",
        ),
    )
