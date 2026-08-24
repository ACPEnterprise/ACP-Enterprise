from pathlib import Path

from app.events.types import EventType
from app.platform.permissions.codes import PaymentPermission


def test_permissions_and_business_events_match_packet() -> None:
    assert len(PaymentPermission.ALL) == 7
    expected = {
        "payment.intent_created", "payment.authorization_recorded", "payment.receipt_captured", "payment.failed",
        "payment.refund_requested", "payment.refund_succeeded", "payment.refund_failed", "payment.dispute_recorded",
        "payment.deposit_submitted", "payment.deposit_reversed", "payment.settlement_received", "payment.settlement_reconciled",
        "payment.reconciliation_exception_opened", "payment.reconciliation_exception_resolved",
    }
    assert expected <= {event.value for event in EventType}


def test_slot_three_migration_has_invoice_parent_and_sensitive_columns_are_absent() -> None:
    root = Path(__file__).resolve().parents[2]
    migration = (root / "alembic/versions/x9n1j3l5p720_create_day_one_payments_runtime.py").read_text()
    assert 'down_revision: str | Sequence[str] | None = "w8m0i2k4n619"' in migration
    lowered = migration.lower()
    for forbidden in ('"pan"', '"cvv"', '"webhook_secret"', '"raw_payload"', '"bank_credentials"'):
        assert forbidden not in lowered
