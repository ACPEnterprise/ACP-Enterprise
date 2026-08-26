from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.qbo_source.contracts import (
    AcquisitionRequest,
    EntityKind,
    QboSourceEnvelope,
    SnapshotIdentity,
)
from app.qbo_source.fake import DeterministicSourceFake
from app.qbo_source.reconciliation import (
    ControlKind,
    ReconciliationState,
    reconcile_amount,
)


def snapshot() -> SnapshotIdentity:
    return SnapshotIdentity(
        snapshot_id="synthetic-2026-08-25",
        realm_id="synthetic-realm",
        environment="sandbox",
        accounting_date_cutoff=date(2026, 8, 25),
        cutoff_timezone="America/New_York",
        started_at=datetime(2026, 8, 26, 14, tzinfo=timezone.utc),
        api_minor_version=75,
    )


def envelope(native_id: str = "synthetic-invoice-1") -> QboSourceEnvelope:
    payload = {
        "Id": native_id,
        "SyncToken": "3",
        "Balance": "125.00",
        "TxnStatus": "Open",
        "CurrencyRef": {"value": "USD"},
    }
    return QboSourceEnvelope.from_native(
        snapshot=snapshot(),
        native_entity_type=EntityKind.INVOICE.value,
        native_id=native_id,
        payload=payload,
        acquired_at=datetime(2026, 8, 26, 14, 1, tzinfo=timezone.utc),
        sync_token="3",
        relationship_ids=("customer:synthetic-customer-1",),
        currency="USD",
        source_status="open",
        source_accounting_meaning={"open_balance": "125.00"},
    )


def test_envelope_preserves_native_open_state_and_digest() -> None:
    item = envelope()

    assert item.raw_payload["TxnStatus"] == "Open"
    assert item.source_status == "open"
    assert item.source_accounting_meaning["open_balance"] == "125.00"
    with pytest.raises(TypeError):
        item.raw_payload["Balance"] = "0.00"  # type: ignore[index]


def test_envelope_rejects_payload_digest_mismatch() -> None:
    item = envelope()

    with pytest.raises(ValueError, match="digest mismatch"):
        replace(item, raw_sha256="0" * 64)


@pytest.mark.asyncio
async def test_fake_is_deterministic_filtered_and_read_only() -> None:
    second = QboSourceEnvelope.from_native(
        snapshot=snapshot(),
        native_entity_type=EntityKind.ACCOUNT.value,
        native_id="synthetic-account-1",
        payload={"Id": "synthetic-account-1", "AccountType": "Credit Card"},
        acquired_at=datetime(2026, 8, 26, 14, 2, tzinfo=timezone.utc),
    )
    provider = DeterministicSourceFake((envelope(), second))
    request = AcquisitionRequest(
        snapshot=snapshot(), entity_kinds=(EntityKind.INVOICE,)
    )

    acquired = [item async for item in provider.acquire(request)]

    assert [item.native_id for item in acquired] == ["synthetic-invoice-1"]
    assert not hasattr(provider, "create")
    assert not hasattr(provider, "update")
    assert not hasattr(provider, "delete")


@pytest.mark.parametrize(
    ("source", "control", "state", "variance"),
    [
        (Decimal(10), Decimal(10), ReconciliationState.MATCHED, Decimal(0)),
        (Decimal(10), Decimal(9), ReconciliationState.EXCEPTION, Decimal(1)),
        (None, Decimal(0), ReconciliationState.MISSING_SOURCE_EVIDENCE, None),
        (Decimal(0), None, ReconciliationState.MISSING_CONTROL_EVIDENCE, None),
    ],
)
def test_reconciliation_never_treats_missing_as_zero(
    source: Decimal | None,
    control: Decimal | None,
    state: ReconciliationState,
    variance: Decimal | None,
) -> None:
    result = reconcile_amount(
        control_kind=ControlKind.TRIAL_BALANCE,
        key="synthetic-account",
        source_amount=source,
        control_amount=control,
        source_evidence_ids=("account:synthetic-account",),
        control_evidence_sha256="a" * 64,
    )

    assert result.state == state
    assert result.variance == variance
