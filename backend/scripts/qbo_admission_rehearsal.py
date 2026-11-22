"""Deterministic read-only rehearsal for sealed QBO evidence.

The rehearsal never creates Accounting facts or application-ledger rows. It reads the
current exact native bindings in a read-only transaction and projects the disposition
that the governed application service would require for every sealed source record.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import stat
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from app.accounting.models import AccountSourceIdentity, PostingSource
from app.accounts_payable.models import VendorSourceMapping
from app.core.config import settings
from app.customer_migration.models import CustomerSourceIdentity
from app.qbo_source.application_models import QboNativeApplicationRecord
from app.qbo_source.bounded_evidence import (
    BoundedEvidencePacket,
    latest_bounded_evidence,
    load_bounded_envelopes,
)
from app.qbo_source.contracts import QboSourceEnvelope
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

QBO_SOURCE_SYSTEMS = ("quickbooks_online", "qbo")
REHEARSAL_SCHEMA = "qbo-native-admission-rehearsal/v1"
MAPPED_FAMILIES = {"account", "customer", "vendor", "journal_entry"}
CONTRACT_REQUIRED_FAMILIES = {
    "bill",
    "deposit",
    "invoice",
    "payment",
    "purchase",
    "transfer",
}
SEPARATE_AUTHORITY_FAMILIES = {
    "employee",
    "tax_agency",
    "tax_payment",
    "time_activity",
}


@dataclass(frozen=True, slots=True)
class NativeInventory:
    company_id: UUID
    realm_id: str
    account_ids: frozenset[str] = frozenset()
    customer_ids: frozenset[str] = frozenset()
    vendor_ids: frozenset[str] = frozenset()
    journal_entry_ids: frozenset[str] = frozenset()
    current_application_records: int = 0

    def ids_for(self, family: str) -> frozenset[str]:
        return {
            "account": self.account_ids,
            "customer": self.customer_ids,
            "vendor": self.vendor_ids,
            "journal_entry": self.journal_entry_ids,
        }.get(family, frozenset())

    def evidence(self) -> dict[str, object]:
        identity_sets = {
            "account": self.account_ids,
            "customer": self.customer_ids,
            "journal_entry": self.journal_entry_ids,
            "vendor": self.vendor_ids,
        }
        canonical = {
            family: sorted(values) for family, values in sorted(identity_sets.items())
        }
        return {
            "company_id": str(self.company_id),
            "realm_id": self.realm_id,
            "exact_binding_counts": {
                family: len(values) for family, values in canonical.items()
            },
            "exact_binding_inventory_digest": _digest(canonical),
            "current_application_records": self.current_application_records,
            "transaction_mode": "READ_ONLY",
        }


async def read_native_inventory(
    *, database_url: str, company_id: UUID, realm_id: str
) -> NativeInventory:
    """Read exact QBO bindings; the first transaction statement is READ ONLY."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection, connection.begin():
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            accounts = frozenset(
                (
                    await connection.execute(
                        select(AccountSourceIdentity.source_account_id).where(
                            AccountSourceIdentity.company_id == company_id,
                            AccountSourceIdentity.source_system.in_(QBO_SOURCE_SYSTEMS),
                            AccountSourceIdentity.source_company_id == realm_id,
                        )
                    )
                ).scalars()
            )
            customers = frozenset(
                (
                    await connection.execute(
                        select(CustomerSourceIdentity.source_customer_id).where(
                            CustomerSourceIdentity.company_id == company_id,
                            CustomerSourceIdentity.source_system.in_(
                                QBO_SOURCE_SYSTEMS
                            ),
                        )
                    )
                ).scalars()
            )
            vendors = frozenset(
                (
                    await connection.execute(
                        select(VendorSourceMapping.source_vendor_id).where(
                            VendorSourceMapping.company_id == company_id,
                            VendorSourceMapping.source_system.in_(QBO_SOURCE_SYSTEMS),
                            VendorSourceMapping.source_company_id == realm_id,
                        )
                    )
                ).scalars()
            )
            journals = frozenset(
                (
                    await connection.execute(
                        select(PostingSource.source_identity).where(
                            PostingSource.company_id == company_id,
                            PostingSource.source_system.in_(QBO_SOURCE_SYSTEMS),
                            PostingSource.source_type == "journal_entry",
                        )
                    )
                ).scalars()
            )
            application_count = int(
                (
                    await connection.scalar(
                        select(func.count(QboNativeApplicationRecord.id)).where(
                            QboNativeApplicationRecord.company_id == company_id,
                            QboNativeApplicationRecord.superseded_at.is_(None),
                        )
                    )
                )
                or 0
            )
        return NativeInventory(
            company_id=company_id,
            realm_id=realm_id,
            account_ids=accounts,
            customer_ids=customers,
            vendor_ids=vendors,
            journal_entry_ids=journals,
            current_application_records=application_count,
        )
    finally:
        await engine.dispose()


def build_rehearsal(
    *, packet: BoundedEvidencePacket, inventory: NativeInventory
) -> dict[str, object]:
    envelopes = load_bounded_envelopes(packet)
    source_counts: Counter[str] = Counter()
    disposition_counts: Counter[str] = Counter()
    by_family: dict[str, Counter[str]] = {}
    seen: set[tuple[str, str]] = set()
    relationship_count = 0
    payment_invoice_links = 0
    missing_payment_invoice_links = 0
    invoice_ids = {
        envelope.native_id
        for _, envelope in envelopes
        if envelope.native_entity_type == "invoice"
    }
    for envelope_digest, envelope in envelopes:
        if len(envelope_digest) != 64:
            raise ValueError("invalid source envelope digest")
        if envelope.snapshot.realm_id != inventory.realm_id:
            raise ValueError("native inventory realm does not match source evidence")
        key = (envelope.native_entity_type, envelope.native_id)
        if key in seen:
            raise ValueError("duplicate source identity in bounded evidence")
        seen.add(key)
        family = envelope.native_entity_type
        source_counts[family] += 1
        relationship_count += len(envelope.relationship_ids)
        disposition = _disposition(envelope, inventory)
        disposition_counts[disposition] += 1
        by_family.setdefault(family, Counter())[disposition] += 1
        if family == "payment":
            for transaction_type, transaction_id in _linked_transactions(
                envelope.raw_payload
            ):
                if transaction_type == "Invoice":
                    payment_invoice_links += 1
                    missing_payment_invoice_links += int(
                        transaction_id not in invoice_ids
                    )

    provider_unavailable = _provider_unavailable(packet)
    deterministic_core: dict[str, object] = {
        "schema_version": REHEARSAL_SCHEMA,
        "state": "REHEARSAL_COMPLETE_NO_WRITES",
        "source_run_id": packet.manifest.get("run_id"),
        "source_manifest_sha256": packet.manifest_sha256,
        "bounded_snapshot_sha256": packet.manifest.get("bounded_snapshot_sha256"),
        "source_record_count": len(envelopes),
        "source_family_counts": dict(sorted(source_counts.items())),
        "relationship_id_count": relationship_count,
        "native_inventory": inventory.evidence(),
        "disposition_counts": dict(sorted(disposition_counts.items())),
        "family_dispositions": {
            family: dict(sorted(counts.items()))
            for family, counts in sorted(by_family.items())
        },
        "provider_unavailable_families": provider_unavailable,
        "relationship_checks": {
            "payment_invoice_links": payment_invoice_links,
            "missing_payment_invoice_links": missing_payment_invoice_links,
        },
        "write_assertions": {
            "database_transaction": "READ_ONLY",
            "application_records_created": 0,
            "accounting_facts_created": 0,
            "qbo_operations": 0,
        },
        "admission_state": "BLOCKED_PENDING_EXACT_MAPPINGS_AND_CONTRACTS",
        "blocking_requirements": [
            "approved_exact_account_customer_vendor_and_journal_bindings",
            "approved_historical_invoice_payment_purchase_deposit_transfer_contracts",
            "accountant_accepted_ar_and_unapplied_payment_bridge",
        ],
    }
    if missing_payment_invoice_links:
        deterministic_core["admission_state"] = "BLOCKED_SOURCE_RELATIONSHIP_GAP"
    deterministic_core["rehearsal_digest"] = _digest(deterministic_core)
    return deterministic_core


def verify_determinism(
    *, packet: BoundedEvidencePacket, inventory: NativeInventory
) -> dict[str, object]:
    first = build_rehearsal(packet=packet, inventory=inventory)
    second = build_rehearsal(packet=packet, inventory=inventory)
    if first != second:
        raise ValueError("rehearsal replay is not deterministic")
    return first


def _disposition(envelope: QboSourceEnvelope, inventory: NativeInventory) -> str:
    family = envelope.native_entity_type
    if family in MAPPED_FAMILIES:
        if envelope.native_id in inventory.ids_for(family):
            return "BOUND_EXACT"
        return {
            "account": "REVIEW_ACCOUNT_MAPPING_REQUIRED",
            "customer": "REVIEW_CUSTOMER_IDENTITY_REQUIRED",
            "vendor": "REVIEW_VENDOR_IDENTITY_REQUIRED",
            "journal_entry": "REVIEW_JOURNAL_MAPPING_REQUIRED",
        }[family]
    if family in CONTRACT_REQUIRED_FAMILIES:
        return f"REVIEW_{family.upper()}_CONTRACT_REQUIRED"
    if family in SEPARATE_AUTHORITY_FAMILIES:
        return "UNSUPPORTED_SEPARATE_WORKFORCE_OR_TAX_AUTHORITY"
    return "UNSUPPORTED_NATIVE_APPLICATION_CONTRACT"


def _linked_transactions(payload: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    links: set[tuple[str, str]] = set()

    def visit(value: object) -> None:
        if isinstance(value, Mapping):
            transaction_type = value.get("TxnType")
            transaction_id = value.get("TxnId")
            if (
                isinstance(transaction_type, str)
                and transaction_type
                and isinstance(transaction_id, str)
                and transaction_id
            ):
                links.add((transaction_type, transaction_id))
            for child in value.values():
                visit(child)
        elif isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            for child in value:
                visit(child)

    visit(payload)
    return tuple(sorted(links))


def _provider_unavailable(packet: BoundedEvidencePacket) -> list[dict[str, str]]:
    dispositions = packet.manifest.get("catalog_dispositions", [])
    if not isinstance(dispositions, list):
        raise TypeError("catalog dispositions are invalid")
    result: list[dict[str, str]] = []
    for disposition in dispositions:
        if not isinstance(disposition, Mapping):
            raise TypeError("catalog disposition is invalid")
        result.append(
            {
                "entity_kind": str(disposition.get("entity_kind", "")),
                "disposition": str(disposition.get("disposition", "")),
                "error_classification": str(
                    disposition.get("error_classification", "")
                ),
            }
        )
    return sorted(result, key=lambda value: value["entity_kind"])


def write_report(
    *, path: Path, repository_root: Path, report: Mapping[str, Any]
) -> str:
    output = path.expanduser().resolve()
    repository = repository_root.expanduser().resolve()
    if output.is_relative_to(repository):
        raise ValueError("rehearsal evidence must be outside the repository")
    parent = output.parent
    if not parent.is_dir() or parent.is_symlink():
        raise ValueError("rehearsal evidence parent must be an existing real directory")
    parent_mode = stat.S_IMODE(parent.stat().st_mode)
    if parent_mode & 0o077:
        raise ValueError("rehearsal evidence parent must not permit group/other access")
    payload = _canonical(report) + b"\n"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(output, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        if output.exists():
            output.unlink()
        raise
    if stat.S_IMODE(output.stat().st_mode) != 0o600:
        raise ValueError("rehearsal evidence mode is not 0600")
    return hashlib.sha256(payload).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


async def _run(arguments: argparse.Namespace) -> dict[str, object]:
    packet = latest_bounded_evidence(arguments.evidence_root)
    if packet is None:
        raise ValueError("no complete bounded QBO evidence is available")
    if packet.manifest.get("run_id") != arguments.expected_run_id:
        raise ValueError("latest bounded QBO run does not match expected authority")
    snapshot = packet.manifest.get("snapshot")
    if not isinstance(snapshot, Mapping) or not isinstance(
        snapshot.get("realm_id"), str
    ):
        raise TypeError("bounded QBO realm is missing")
    inventory = await read_native_inventory(
        database_url=arguments.database_url,
        company_id=arguments.company_id,
        realm_id=snapshot["realm_id"],
    )
    report = verify_determinism(packet=packet, inventory=inventory)
    report_sha256 = write_report(
        path=arguments.output,
        repository_root=arguments.repository_root,
        report=report,
    )
    return {
        "state": report["state"],
        "source_run_id": report["source_run_id"],
        "source_record_count": report["source_record_count"],
        "rehearsal_digest": report["rehearsal_digest"],
        "report_sha256": report_sha256,
        "output": str(arguments.output.expanduser().resolve()),
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a deterministic read-only QBO native-admission rehearsal"
    )
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--company-id", required=True, type=UUID)
    parser.add_argument("--expected-run-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--database-url", default=settings.database_url)
    return parser.parse_args()


def main() -> None:
    print(json.dumps(asyncio.run(_run(parse_arguments())), sort_keys=True))


if __name__ == "__main__":
    main()
