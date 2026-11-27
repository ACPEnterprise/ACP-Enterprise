"""Qualify the sealed All County QBO archive without external or database writes."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.qbo_source.manual_archive import (
    project_manual_aged_receivables,
    project_manual_archive,
)

EXPECTED_COUNTS = {
    "account": 131,
    "customer": 909,
    "vendor": 868,
    "invoice": 1341,
    "payment": 1237,
    "purchase": 12414,
    "deposit": 3456,
    "transfer": 15,
    "journal_entry": 33,
}
EXPECTED_CONFLICTS = {f"D-{number:03d}" for number in range(1, 8)}


def _read_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise TypeError(f"expected object: {path.name}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def qualify(root: Path, expected_custody_sha256: str) -> dict[str, object]:
    """Return a secret-free receipt or fail closed on any control mismatch."""

    root = root.expanduser().resolve(strict=True)
    custody_path = root / "custody-manifest.json"
    custody_sha256 = _sha256(custody_path)
    if custody_sha256 != expected_custody_sha256:
        raise ValueError("custody manifest digest mismatch")

    workspace = project_manual_archive(root=root, basis="accrual")
    aged = project_manual_aged_receivables(root=root, report_date="2026-11-27")
    register = _read_json(root / "reconciliation-register.json")
    rehearsal = _read_json(root / "native-admission-rehearsal.v1.json")
    acquisition = register["current_acquisition"]
    controls = register["report_reconciliation"]
    if not isinstance(acquisition, Mapping) or not isinstance(controls, Mapping):
        raise TypeError("reconciliation register contract invalid")

    counts = acquisition["counts"]
    if not isinstance(counts, Mapping):
        raise TypeError("source count contract invalid")
    for family, expected in EXPECTED_COUNTS.items():
        if counts.get(family) != expected:
            raise ValueError(f"source count mismatch: {family}")
    if acquisition.get("record_count") != 20702:
        raise ValueError("source record count mismatch")
    if acquisition.get("relationship_ids_preserved") != 97093:
        raise ValueError("relationship identity count mismatch")

    conflicts = register.get("discrepancies")
    if not isinstance(conflicts, list):
        raise TypeError("discrepancy register missing")
    conflict_ids = {
        str(item.get("id")) for item in conflicts if isinstance(item, Mapping)
    }
    if conflict_ids != EXPECTED_CONFLICTS:
        raise ValueError("discrepancy register is incomplete")
    discrepancies = {
        str(item["id"]): item
        for item in conflicts
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    ar_bridge = discrepancies["D-002"]
    unapplied = discrepancies["D-003"]
    bank_feed = register.get("bank_feed_evidence")
    if not isinstance(bank_feed, Mapping):
        raise TypeError("bank feed evidence missing")
    invoice_open_balance = Decimal(str(ar_bridge["invoice_open_balance"]))
    balance_sheet_ar = Decimal(str(ar_bridge["balance_sheet_accounts_receivable"]))
    bridge_difference = invoice_open_balance - balance_sheet_ar
    provider_unapplied = Decimal(str(unapplied["provider_unapplied_amount"]))
    unlinked_payment_total = Decimal(str(unapplied["total"]))
    if bridge_difference != Decimal(str(ar_bridge["dollar_difference"])):
        raise ValueError("A/R bridge arithmetic mismatch")
    if int(unapplied["count"]) != 73:
        raise ValueError("unlinked payment count mismatch")
    if bank_feed.get("disposition") != "UNPOSTED_SOURCE_EVIDENCE":
        raise ValueError("bank feed evidence is not preserved as unposted")
    if bank_feed.get("automatic_expense_creation_allowed") is not False:
        raise ValueError("bank feed mutation authority changed")

    trial_balance = controls.get("trial_balance")
    balance_sheet = controls.get("balance_sheet")
    profit_and_loss = controls.get("profit_and_loss")
    general_ledger = controls.get("general_ledger")
    journal_export = controls.get("journal_export")
    if not all(
        isinstance(value, Mapping)
        for value in (
            trial_balance,
            balance_sheet,
            profit_and_loss,
            general_ledger,
            journal_export,
        )
    ):
        raise ValueError("financial controls missing")
    assert isinstance(trial_balance, Mapping)
    assert isinstance(balance_sheet, Mapping)
    assert isinstance(profit_and_loss, Mapping)
    assert isinstance(general_ledger, Mapping)
    assert isinstance(journal_export, Mapping)
    if trial_balance.get("difference") != "0.00":
        raise ValueError("trial balance is not balanced")
    if balance_sheet.get("equation_difference") != "0.00":
        raise ValueError("balance sheet is not balanced")
    if profit_and_loss.get("provider_difference") != "0.00":
        raise ValueError("profit and loss control mismatch")
    if general_ledger.get("amount_difference") != "0.00":
        raise ValueError("general ledger amount mismatch")
    if journal_export.get("difference") != "0.00":
        raise ValueError("journal export is not balanced")

    relationship_checks = rehearsal.get("relationship_checks")
    write_assertions = rehearsal.get("write_assertions")
    if not isinstance(relationship_checks, Mapping) or not isinstance(
        write_assertions, Mapping
    ):
        raise TypeError("rehearsal controls missing")
    if relationship_checks.get("payment_invoice_links") != 1171:
        raise ValueError("payment-to-invoice link count mismatch")
    if relationship_checks.get("missing_payment_invoice_links") != 0:
        raise ValueError("payment-to-invoice relationships are missing")
    expected_no_writes = {
        "accounting_facts_created": 0,
        "application_records_created": 0,
        "database_transaction": "READ_ONLY",
        "qbo_operations": 0,
    }
    if dict(write_assertions) != expected_no_writes:
        raise ValueError("no-write rehearsal assertion failed")

    historical = workspace["historical_reconciliation"]
    if not isinstance(historical, Mapping):
        raise TypeError("historical reconciliation projection missing")
    return {
        "contract": "all-county-accounting-recovery-qualification/v1",
        "result": "PASS_WITH_DISCLOSED_EXCEPTIONS",
        "custody_manifest_sha256": custody_sha256,
        "source_manifest_sha256": acquisition["manifest_sha256"],
        "bounded_snapshot_sha256": acquisition["bounded_snapshot_sha256"],
        "rehearsal_digest": rehearsal["rehearsal_digest"],
        "source_record_count": historical["source_record_count"],
        "relationship_id_count": historical["relationship_id_count"],
        "customer_count": historical["customer_count"],
        "invoice_count": historical["invoice_count"],
        "invoice_line_count": historical["invoice_line_count"],
        "invoice_open_balance": historical["invoice_open_balance"],
        "open_invoice_count": aged["open_invoice_count"],
        "payment_count": historical["payment_count"],
        "payment_invoice_links": historical["payment_invoice_links"],
        "missing_payment_invoice_links": historical["missing_payment_invoice_links"],
        "conflicts": sorted(conflict_ids),
        "ar_bridge": {
            "invoice_open_balance": f"{invoice_open_balance:.2f}",
            "balance_sheet_accounts_receivable": f"{balance_sheet_ar:.2f}",
            "difference": f"{bridge_difference:.2f}",
            "provider_unapplied_amount": f"{provider_unapplied:.2f}",
            "unlinked_payment_count": int(unapplied["count"]),
            "unlinked_payment_total": f"{unlinked_payment_total:.2f}",
            "provider_unapplied_minus_unlinked": (
                f"{provider_unapplied - unlinked_payment_total:.2f}"
            ),
            "bridge_minus_provider_unapplied": (
                f"{bridge_difference - provider_unapplied:.2f}"
            ),
            "state": "UNRESOLVED_SOURCE_CROSSWALK",
        },
        "bank_feed": {
            "pending_rows": int(bank_feed["authoritative_pending_rows"]),
            "exact_duplicate_rows": int(bank_feed["exact_duplicate_rows"]),
            "authoritative_amount_total": str(bank_feed["authoritative_amount_total"]),
            "duplicate_incremental_amount": str(
                bank_feed["duplicate_incremental_amount"]
            ),
            "disposition": str(bank_feed["disposition"]),
            "automatic_expense_creation_allowed": False,
        },
        "trial_balance_difference": trial_balance["difference"],
        "balance_sheet_difference": balance_sheet["equation_difference"],
        "profit_and_loss_difference": profit_and_loss["provider_difference"],
        "general_ledger_amount_difference": general_ledger["amount_difference"],
        "journal_difference": journal_export["difference"],
        "accepted_as_native_accounting": False,
        "external_mutation_authority": "none",
        "external_mutations": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--expected-custody-sha256", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt = qualify(args.archive_root, args.expected_custody_sha256)
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
