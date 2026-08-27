import ast
from pathlib import Path

from app.field_service.models import (
    FieldCustomerApproval,
    FieldInvoiceHandoff,
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
            values[node.target.id] = ast.literal_eval(node.value)
    assert values == {"revision": "z1q3l5n7r942", "down_revision": "y0p2k4m6q831"}
