from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from app.qbo_source.contracts import QboSourceEnvelope, SnapshotIdentity
from app.qbo_source.fixture_reconciliation import reconcile_fixture
from app.qbo_source.sandbox_fixture import (
    FIXTURE_VERSION,
    expected_economic_manifest,
)
from app.qbo_source.transformation import transform_qbo_envelope

SNAPSHOT = SnapshotIdentity(
    snapshot_id="fixture",
    realm_id="123",
    environment="sandbox",
    accounting_date_cutoff=date(2026, 8, 29),
    cutoff_timezone="America/New_York",
    started_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
    api_minor_version=75,
)


def _envelope(family: str, native_id: str, payload: dict[str, object]) -> QboSourceEnvelope:
    return QboSourceEnvelope.from_native(
        snapshot=SNAPSHOT,
        native_entity_type=family,
        native_id=native_id,
        payload={"Id": native_id, **payload},
    )


def test_transformation_is_deterministic_and_never_accepts_accounting_truth() -> None:
    envelope = _envelope(
        "invoice",
        "inv-1",
        {"TotalAmt": 100, "Balance": 70, "Line": [{"Amount": 100}]},
    )
    first = transform_qbo_envelope(envelope)
    second = transform_qbo_envelope(envelope)
    assert first.candidate_sha256 == second.candidate_sha256
    assert first.accounting_acceptance == "source_evidence_only_unreconciled"
    assert first.source_fields["line_amount_total"] == "100"


def test_representative_fixture_reconciles_exactly() -> None:
    rows: dict[tuple[str, str], QboSourceEnvelope] = {}
    objects: list[dict[str, object]] = []

    def add(family: str, native_id: str, payload: dict[str, object]) -> None:
        rows[(family, native_id)] = _envelope(family, native_id, payload)
        objects.append({"family": family, "native_id": native_id})

    for index, (total, balance) in enumerate(
        ((100, 70), (120, 0), (200, 150), (80, 50)), 1
    ):
        add("invoice", f"i{index}", {"TotalAmt": total, "Balance": balance})
    add("payment", "p1", {"TotalAmt": 120, "Line": [{"Amount": 120, "LinkedTxn": [{"TxnId": "i2"}]}]})
    add("payment", "p2", {"TotalAmt": 50, "Line": [{"Amount": 50, "LinkedTxn": [{"TxnId": "i3"}]}]})
    add("payment", "p3", {"TotalAmt": 60, "Line": [{"Amount": 30, "LinkedTxn": [{"TxnId": "i1"}]}, {"Amount": 30, "LinkedTxn": [{"TxnId": "i4"}]}]})
    add("credit_memo", "cm1", {"TotalAmt": 20, "RemainingCredit": 20})
    add("bill", "b1", {"TotalAmt": 150, "Balance": 150})
    add("bill", "b2", {"TotalAmt": 200, "Balance": 125})
    add("bill_payment", "bp1", {"TotalAmt": 75, "Line": [{"Amount": 75, "LinkedTxn": [{"TxnId": "b2"}]}]})
    add("vendor_credit", "vc1", {"TotalAmt": 25, "Balance": 25})
    add("purchase", "pur1", {"TotalAmt": 60})
    for index, amount in enumerate((500, 40), 1):
        add("journal_entry", f"j{index}", {"Line": [{"Amount": amount, "JournalEntryLineDetail": {"PostingType": "Debit"}}, {"Amount": amount, "JournalEntryLineDetail": {"PostingType": "Credit"}}]})
    add("transfer", "t1", {"Amount": 100})
    expected = expected_economic_manifest()
    fixture = {
        "schema_version": FIXTURE_VERSION,
        "fixture_digest": "f" * 64,
        "objects": objects,
    }
    result = reconcile_fixture(
        fixture_manifest=fixture,
        expected_manifest=expected,
        envelopes=rows,
    )
    assert result.state == "RECONCILED"
    assert all(Decimal(value) == 0 for value in result.deltas.values())
    assert all(result.invariants.values())
