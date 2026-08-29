from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from .contracts import QboSourceEnvelope
from .sandbox_fixture import EXPECTED_LEDGER_VERSION, FIXTURE_VERSION

RECONCILIATION_VERSION = "qbo-sandbox-fixture-reconciliation/v1"


@dataclass(frozen=True)
class FixtureReconciliationResult:
    state: str
    reconciliation_sha256: str
    expected_ledger_digest: str
    fixture_digest: str
    values: Mapping[str, str]
    deltas: Mapping[str, str]
    invariants: Mapping[str, bool]


def reconcile_fixture(
    *,
    fixture_manifest: Mapping[str, object],
    expected_manifest: Mapping[str, object],
    envelopes: Mapping[tuple[str, str], QboSourceEnvelope],
) -> FixtureReconciliationResult:
    if fixture_manifest.get("schema_version") != FIXTURE_VERSION:
        raise ValueError("fixture manifest version mismatch")
    if expected_manifest.get("schema_version") != EXPECTED_LEDGER_VERSION:
        raise ValueError("expected ledger version mismatch")
    objects = fixture_manifest.get("objects")
    if not isinstance(objects, list):
        raise TypeError("fixture objects missing")
    selected: dict[str, list[QboSourceEnvelope]] = {}
    found: set[tuple[str, str]] = set()
    for item in objects:
        if not isinstance(item, Mapping):
            raise TypeError("fixture object invalid")
        family = str(item["family"])
        key = (family, str(item["native_id"]))
        envelope = envelopes.get(key)
        if envelope is None:
            raise ValueError("fixture source identity missing")
        if key in found:
            raise ValueError("fixture source identity duplicated")
        found.add(key)
        selected.setdefault(family, []).append(envelope)

    values = {
        "invoice_gross": _sum(selected, "invoice", "TotalAmt"),
        "customer_payments": _sum(selected, "payment", "TotalAmt"),
        "customer_credit": _sum_credit(selected, "credit_memo"),
        "ar_outstanding_before_unapplied_credit": _sum(
            selected, "invoice", "Balance"
        ),
        "bill_gross": _sum(selected, "bill", "TotalAmt"),
        "bill_payments": _sum(selected, "bill_payment", "TotalAmt"),
        "vendor_credit": _sum_credit(selected, "vendor_credit"),
        "cash_purchase": _sum(selected, "purchase", "TotalAmt"),
        "journal_debits": _journal_total(selected, "Debit"),
        "journal_credits": _journal_total(selected, "Credit"),
        "transfer_amount": _sum(selected, "transfer", "Amount"),
        "transfer_net_income_effect": Decimal(0),
    }
    values["ar_net_customer_balance"] = (
        values["ar_outstanding_before_unapplied_credit"] - values["customer_credit"]
    )
    values["ap_net_vendor_balance"] = (
        _sum(selected, "bill", "Balance") - values["vendor_credit"]
    )
    expected_values = expected_manifest.get("values")
    if not isinstance(expected_values, Mapping):
        raise TypeError("expected values missing")
    deltas = {
        key: values[key] - Decimal(str(expected_values[key])) for key in sorted(values)
    }
    invariants = {
        "journal_balanced": values["journal_debits"] == values["journal_credits"],
        "payment_applications_exact": _linked_total(selected, "payment")
        == values["customer_payments"],
        "bill_payment_applications_exact": _linked_total(
            selected, "bill_payment"
        )
        == values["bill_payments"],
        "transfer_neutral": values["transfer_net_income_effect"] == 0,
        "all_expected_values_match": all(value == 0 for value in deltas.values()),
    }
    canonical = {
        "schema_version": RECONCILIATION_VERSION,
        "fixture_digest": fixture_manifest.get("fixture_digest"),
        "expected_ledger_digest": expected_manifest.get("manifest_sha256"),
        "values": {key: format(value, "f") for key, value in sorted(values.items())},
        "deltas": {key: format(value, "f") for key, value in sorted(deltas.items())},
        "invariants": dict(sorted(invariants.items())),
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return FixtureReconciliationResult(
        state=("RECONCILED" if all(invariants.values()) else "EXCEPTION"),
        reconciliation_sha256=digest,
        expected_ledger_digest=str(expected_manifest["manifest_sha256"]),
        fixture_digest=str(fixture_manifest["fixture_digest"]),
        values=canonical["values"],  # type: ignore[arg-type]
        deltas=canonical["deltas"],  # type: ignore[arg-type]
        invariants=invariants,
    )


def _sum(
    selected: Mapping[str, list[QboSourceEnvelope]], family: str, field: str
) -> Decimal:
    return sum(
        (Decimal(str(item.raw_payload.get(field, 0))) for item in selected.get(family, [])),
        Decimal(0),
    )


def _sum_credit(
    selected: Mapping[str, list[QboSourceEnvelope]], family: str
) -> Decimal:
    return sum(
        (
            Decimal(
                str(
                    item.raw_payload.get(
                        "RemainingCredit", item.raw_payload.get("Balance", item.raw_payload.get("TotalAmt", 0))
                    )
                )
            )
            for item in selected.get(family, [])
        ),
        Decimal(0),
    )


def _journal_total(
    selected: Mapping[str, list[QboSourceEnvelope]], posting_type: str
) -> Decimal:
    total = Decimal(0)
    for envelope in selected.get("journal_entry", []):
        lines = envelope.raw_payload.get("Line", ())
        if not isinstance(lines, tuple):
            continue
        for line in lines:
            if not isinstance(line, Mapping):
                continue
            detail = line.get("JournalEntryLineDetail")
            if isinstance(detail, Mapping) and detail.get("PostingType") == posting_type:
                total += Decimal(str(line.get("Amount", 0)))
    return total


def _linked_total(
    selected: Mapping[str, list[QboSourceEnvelope]], family: str
) -> Decimal:
    total = Decimal(0)
    for envelope in selected.get(family, []):
        lines = envelope.raw_payload.get("Line", ())
        if not isinstance(lines, tuple):
            continue
        for line in lines:
            if isinstance(line, Mapping) and line.get("LinkedTxn"):
                total += Decimal(str(line.get("Amount", 0)))
    return total
