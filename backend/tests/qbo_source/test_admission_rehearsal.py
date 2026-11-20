from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from types import MappingProxyType
from uuid import UUID

import pytest
from app.qbo_source.contracts import QboSourceEnvelope, SnapshotIdentity
from scripts.qbo_admission_rehearsal import (
    NativeInventory,
    _disposition,
    _linked_transactions,
    write_report,
)


def envelope(family: str, native_id: str) -> QboSourceEnvelope:
    payload: dict[str, object] = {"Id": native_id, "SyncToken": "0"}
    return QboSourceEnvelope.from_native(
        snapshot=SnapshotIdentity(
            snapshot_id="qbo-production-test",
            realm_id="realm-1",
            environment="production",
            accounting_date_cutoff=date(2026, 11, 19),
            cutoff_timezone="America/New_York",
            started_at=datetime(2026, 11, 20, tzinfo=timezone.utc),
            api_minor_version=75,
        ),
        native_entity_type=family,
        native_id=native_id,
        payload=payload,
    )


def inventory(**values) -> NativeInventory:
    return NativeInventory(
        company_id=UUID("a56fc415-563b-459c-913f-2e6183109119"),
        realm_id="realm-1",
        **values,
    )


def test_exact_bindings_are_bound_and_name_matching_is_never_used() -> None:
    native = inventory(account_ids=frozenset({"account-1"}))
    assert _disposition(envelope("account", "account-1"), native) == "BOUND_EXACT"
    assert (
        _disposition(envelope("account", "same-name-different-id"), native)
        == "REVIEW_ACCOUNT_MAPPING_REQUIRED"
    )


def test_financial_contracts_and_separate_authorities_fail_closed() -> None:
    native = inventory()
    assert (
        _disposition(envelope("invoice", "invoice-1"), native)
        == "REVIEW_INVOICE_CONTRACT_REQUIRED"
    )
    assert (
        _disposition(envelope("employee", "employee-1"), native)
        == "UNSUPPORTED_SEPARATE_WORKFORCE_OR_TAX_AUTHORITY"
    )


def test_linked_transactions_are_deduplicated_and_stable() -> None:
    payload = MappingProxyType(
        {
            "Line": (
                MappingProxyType(
                    {
                        "LinkedTxn": (
                            MappingProxyType(
                                {"TxnType": "Invoice", "TxnId": "invoice-1"}
                            ),
                            MappingProxyType(
                                {"TxnType": "Invoice", "TxnId": "invoice-1"}
                            ),
                        )
                    }
                ),
            )
        }
    )
    assert _linked_transactions(payload) == (("Invoice", "invoice-1"),)


def test_inventory_evidence_exposes_counts_and_digest_not_provider_ids() -> None:
    evidence = inventory(customer_ids=frozenset({"customer-sensitive-id"})).evidence()
    encoded = json.dumps(evidence, sort_keys=True)
    assert evidence["exact_binding_counts"] == {
        "account": 0,
        "customer": 1,
        "journal_entry": 0,
        "vendor": 0,
    }
    assert "customer-sensitive-id" not in encoded


def test_report_writer_is_exclusive_private_and_outside_repository(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    evidence = tmp_path / "evidence"
    repository.mkdir(mode=0o700)
    evidence.mkdir(mode=0o700)
    output = evidence / "rehearsal.json"
    digest = write_report(
        path=output,
        repository_root=repository,
        report={"state": "REHEARSAL_COMPLETE_NO_WRITES"},
    )
    assert output.stat().st_mode & 0o777 == 0o600
    assert digest == hashlib.sha256(output.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        write_report(path=output, repository_root=repository, report={})


def test_report_writer_rejects_repository_destination(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir(mode=0o700)
    with pytest.raises(ValueError, match="outside the repository"):
        write_report(
            path=repository / "rehearsal.json",
            repository_root=repository,
            report={},
        )
