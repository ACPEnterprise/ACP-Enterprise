from pathlib import Path

from sqlalchemy import CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base
from app.payments import models as payment_models  # noqa: F401

EXPECTED_CHECKS = {
    "payment_intents": {
        "payment_intents_check",
        "payment_intents_status_check",
    },
    "payment_receipts": {
        "payment_receipts_check",
        "payment_receipts_check1",
    },
    "payment_refunds": {"payment_refunds_amount_check"},
    "payment_deposits": {"payment_deposits_gross_amount_check"},
    "payment_settlements": {"payment_settlements_check"},
}


def test_payment_models_are_registered_with_alembic_metadata() -> None:
    env = Path("alembic/env.py").read_text()
    assert "from app.payments import models as payment_models" in env
    assert "payment_webhook_receipts" in Base.metadata.tables


def test_payment_checks_have_the_migrated_canonical_names() -> None:
    actual = {
        table: {
            constraint.name
            for constraint in Base.metadata.tables[table].constraints
            if isinstance(constraint, CheckConstraint)
        }
        for table in EXPECTED_CHECKS
    }
    assert actual == EXPECTED_CHECKS


def test_webhook_allowlist_uses_postgresql_jsonb() -> None:
    column = Base.metadata.tables["payment_webhook_receipts"].c.allowed_evidence
    assert isinstance(column.type, JSONB)
