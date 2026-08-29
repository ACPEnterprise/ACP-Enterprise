from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode

from app.core.config import Settings, settings

from .intuit import (
    ENDPOINTS,
    HttpResponse,
    IntuitEnvironment,
    IntuitHttpTransport,
    IntuitOAuthClient,
    RealmBinding,
    SerializedTokenManager,
)
from .runtime import (
    ProtectedSandboxCompanyBinding,
    SandboxRuntimeError,
    _runtime_root,
)
from .secrets import ProtectedSandboxSecretProvider

FIXTURE_VERSION = "qbo-sandbox-representative-history/v1"
FIXTURE_TAG = "ACP-QBO-QUAL-12H1"
EXPECTED_LEDGER_VERSION = "qbo-sandbox-expected-ledger/v1"


class SandboxFixtureError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class FixtureTransport(Protocol):
    async def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> HttpResponse: ...


@dataclass(frozen=True)
class SandboxFixtureAuthority:
    realm_id: str
    repository_sha: str
    actor: str
    authorization_id: str
    environment: str = "sandbox"
    fixture_version: str = FIXTURE_VERSION

    def __post_init__(self) -> None:
        if self.environment != "sandbox":
            raise SandboxFixtureError("fixture_production_forbidden")
        if not self.realm_id.isascii() or not self.realm_id.isdigit():
            raise SandboxFixtureError("fixture_realm_invalid")
        if len(self.repository_sha) != 40 or any(
            char not in "0123456789abcdef" for char in self.repository_sha
        ):
            raise SandboxFixtureError("fixture_repository_sha_invalid")
        if not self.actor or not self.authorization_id:
            raise SandboxFixtureError("fixture_authorization_incomplete")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "actor": self.actor,
                "authorization_id": self.authorization_id,
                "environment": self.environment,
                "fixture_version": self.fixture_version,
                "realm_id": self.realm_id,
                "repository_sha": self.repository_sha,
            }
        )


@dataclass(frozen=True)
class FixtureObject:
    family: str
    fixture_key: str
    native_id: str
    sync_token: str
    payload_sha256: str


@dataclass(frozen=True)
class SandboxFixtureResult:
    state: str
    fixture_digest: str
    expected_ledger_digest: str
    counts: Mapping[str, int]
    created: int
    reused: int


def expected_economic_manifest() -> dict[str, object]:
    """Independent expected truth for the deterministic representative fixture."""
    values = {
        "invoice_gross": Decimal("500.00"),
        "customer_payments": Decimal("230.00"),
        "customer_credit": Decimal("20.00"),
        "ar_outstanding_before_unapplied_credit": Decimal("270.00"),
        "ar_net_customer_balance": Decimal("250.00"),
        "bill_gross": Decimal("350.00"),
        "bill_payments": Decimal("75.00"),
        "vendor_credit": Decimal("25.00"),
        "ap_net_vendor_balance": Decimal("250.00"),
        "cash_purchase": Decimal("60.00"),
        "journal_debits": Decimal("540.00"),
        "journal_credits": Decimal("540.00"),
        "transfer_amount": Decimal("100.00"),
        "transfer_net_income_effect": Decimal("0.00"),
    }
    document: dict[str, object] = {
        "schema_version": EXPECTED_LEDGER_VERSION,
        "fixture_tag": FIXTURE_TAG,
        "currency": "USD",
        "values": {key: format(value, "f") for key, value in sorted(values.items())},
        "invariants": {
            "ar_rollforward": "500.00-230.00-20.00=250.00",
            "ap_rollforward": "350.00-75.00-25.00=250.00",
            "journal_balanced": True,
            "payments_are_not_revenue": True,
            "transfers_are_not_income_or_expense": True,
            "opening_entry_distinct_from_operations": True,
        },
    }
    document["manifest_sha256"] = _digest(document)
    return document


class SandboxFixtureService:
    def __init__(
        self,
        *,
        authority: SandboxFixtureAuthority,
        token_manager: SerializedTokenManager,
        transport: FixtureTransport,
        runtime_root: Path,
        minor_version: int,
    ) -> None:
        if authority.environment != "sandbox":
            raise SandboxFixtureError("fixture_production_forbidden")
        self.authority = authority
        self.token_manager = token_manager
        self.transport = transport
        self.runtime_root = runtime_root.resolve()
        self.minor_version = minor_version
        self.api_base = ENDPOINTS[IntuitEnvironment.SANDBOX].api_base
        self.fixture_root = self.runtime_root / "fixtures" / authority.digest

    async def qualify(self) -> SandboxFixtureResult:
        marker = _read_json(self.runtime_root / "connections" / "verified.json")
        if marker.get("environment") != "sandbox":
            raise SandboxFixtureError("fixture_connection_not_sandbox")
        if marker.get("realm_id") != self.authority.realm_id:
            raise SandboxFixtureError("fixture_realm_mismatch")
        if marker.get("acquisition_eligible") is not True:
            raise SandboxFixtureError("fixture_connection_unverified")
        existing = self.fixture_root / "fixture-manifest.json"
        if not existing.exists():
            return SandboxFixtureResult(
                state="QUALIFIED",
                fixture_digest=self.authority.digest,
                expected_ledger_digest=str(expected_economic_manifest()["manifest_sha256"]),
                counts={},
                created=0,
                reused=0,
            )
        document = _read_json(existing)
        if document.get("authority_digest") != self.authority.digest:
            raise SandboxFixtureError("fixture_manifest_authority_conflict")
        objects = document.get("objects")
        if not isinstance(objects, list):
            raise SandboxFixtureError("fixture_manifest_invalid")
        counts = _counts_from_objects(objects)
        return SandboxFixtureResult(
            state="ALREADY_CURRENT",
            fixture_digest=str(document["fixture_digest"]),
            expected_ledger_digest=str(document["expected_ledger_digest"]),
            counts=counts,
            created=0,
            reused=len(objects),
        )

    async def create(self) -> SandboxFixtureResult:
        qualification = await self.qualify()
        if qualification.state == "ALREADY_CURRENT":
            return qualification
        objects: list[FixtureObject] = []
        created = 0
        reused = 0

        account_specs: tuple[tuple[str, dict[str, object]], ...] = (
            ("account-bank", _account("ACP Qualification Operating Checking", "Bank", "Checking")),
            ("account-bank-secondary", _account("ACP Qualification Reserve Savings", "Bank", "Savings")),
            ("account-ar", _account("ACP Qualification Accounts Receivable", "Accounts Receivable", "AccountsReceivable")),
            ("account-ap", _account("ACP Qualification Accounts Payable", "Accounts Payable", "AccountsPayable")),
            ("account-service-income", _account("ACP Qualification Service Revenue", "Income", "ServiceFeeIncome")),
            ("account-product-income", _account("ACP Qualification Material Revenue", "Income", "SalesOfProductIncome")),
            ("account-cogs", _account("ACP Qualification Materials COGS", "Cost of Goods Sold", "SuppliesMaterialsCogs")),
            ("account-expense", _account("ACP Qualification Operating Expense", "Expense", "OtherMiscellaneousServiceCost")),
            ("account-payroll-expense", _account("ACP Qualification Payroll Expense", "Expense", "PayrollExpenses")),
            ("account-payroll-liability", _account("ACP Qualification Payroll Liability", "Other Current Liability", "PayrollTaxPayable")),
            ("account-fixed-asset", _account("ACP Qualification Fixed Asset", "Fixed Asset", "FurnitureAndFixtures")),
            ("account-depreciation", _account("ACP Qualification Accumulated Depreciation", "Fixed Asset", "OtherFixedAssets")),
            ("account-equity", _account("ACP Qualification Owner Equity", "Equity", "OwnersEquity")),
            ("account-credit-card", _account("ACP Qualification Credit Card", "Credit Card", "CreditCard")),
        )
        fixture_accounts: dict[str, dict[str, object]] = {}
        for key, payload in account_specs:
            value, was_created = await self._ensure_named(
                "Account", key, payload, name_field="Name"
            )
            fixture_accounts[key] = value
            objects.append(_fixture_object("account", key, value))
            created += was_created
            reused += not was_created
        refs = {
            "bank": str(fixture_accounts["account-bank"]["Id"]),
            "bank_secondary": str(
                fixture_accounts["account-bank-secondary"]["Id"]
            ),
            "income": str(fixture_accounts["account-service-income"]["Id"]),
            "expense": str(fixture_accounts["account-expense"]["Id"]),
            "equity": str(fixture_accounts["account-equity"]["Id"]),
        }

        term, was_created = await self._ensure_named(
            "Term",
            "term-net-30",
            {
                "Name": "ACP Qualification Net 30",
                "Type": "STANDARD",
                "DueDays": 30,
            },
            name_field="Name",
        )
        objects.append(_fixture_object("term", "term-net-30", term))
        created += was_created
        reused += not was_created
        payment_method, was_created = await self._ensure_named(
            "PaymentMethod",
            "payment-method",
            {
                "Name": "ACP Qual EPay",
                "Type": "NON_CREDIT_CARD",
            },
            name_field="Name",
        )
        objects.append(
            _fixture_object("payment_method", "payment-method", payment_method)
        )
        created += was_created
        reused += not was_created

        customer_specs: tuple[tuple[str, dict[str, object]], ...] = (
            ("customer-active", {"DisplayName": "ACP QBO Qualification Customer 001", "Notes": FIXTURE_TAG}),
            ("customer-history", {"DisplayName": "ACP QBO Qualification Customer 002", "Notes": FIXTURE_TAG}),
        )
        customers: dict[str, dict[str, object]] = {}
        for key, payload in customer_specs:
            value, was_created = await self._ensure_named("Customer", key, payload)
            customers[key] = value
            objects.append(_fixture_object("customer", key, value))
            created += was_created
            reused += not was_created

        vendor, was_created = await self._ensure_named(
            "Vendor",
            "vendor-primary",
            {"DisplayName": "ACP QBO Qualification Vendor 001", "CompanyName": "ACP Synthetic Qualification Vendor", "Notes": FIXTURE_TAG},
        )
        objects.append(_fixture_object("vendor", "vendor-primary", vendor))
        created += was_created
        reused += not was_created

        item_specs: tuple[tuple[str, dict[str, object]], ...] = (
            (
                "item-service",
                {
                    "Name": "ACP Qualification Service",
                    "Type": "Service",
                    "IncomeAccountRef": {"value": refs["income"]},
                    "Description": FIXTURE_TAG,
                },
            ),
            (
                "item-material",
                {
                    "Name": "ACP Qualification Material",
                    "Type": "NonInventory",
                    "IncomeAccountRef": {"value": refs["income"]},
                    "ExpenseAccountRef": {"value": refs["expense"]},
                    "Description": FIXTURE_TAG,
                },
            ),
        )
        items: dict[str, dict[str, object]] = {}
        for key, payload in item_specs:
            value, was_created = await self._ensure_named("Item", key, payload, name_field="Name")
            items[key] = value
            objects.append(_fixture_object("item", key, value))
            created += was_created
            reused += not was_created

        invoice_specs = (
            ("invoice-unpaid", "ACP-QUAL-INV-001", 100, "2025-12-15", "customer-active"),
            ("invoice-paid", "ACP-QUAL-INV-002", 120, "2026-01-15", "customer-active"),
            ("invoice-partial", "ACP-QUAL-INV-003", 200, "2026-08-01", "customer-history"),
            ("invoice-multiple", "ACP-QUAL-INV-004", 80, "2026-08-02", "customer-active"),
        )
        invoices: dict[str, dict[str, object]] = {}
        for key, doc, amount, txn_date, customer_key in invoice_specs:
            invoice_payload: dict[str, object] = {
                "DocNumber": doc,
                "TxnDate": txn_date,
                "DueDate": "2026-09-15",
                "CustomerRef": {"value": str(customers[customer_key]["Id"])},
                "SalesTermRef": {"value": str(term["Id"])},
                "CustomerMemo": {"value": FIXTURE_TAG},
                "PrivateNote": FIXTURE_TAG,
                "Line": [_sales_line(amount, str(items["item-service"]["Id"]))],
            }
            value, was_created = await self._ensure_transaction(
                "Invoice", key, doc, invoice_payload
            )
            invoices[key] = value
            objects.append(_fixture_object("invoice", key, value))
            created += was_created
            reused += not was_created

        payment_specs = (
            ("payment-full", "ACP-QUAL-PAY-001", "customer-active", (("invoice-paid", 120),)),
            ("payment-partial", "ACP-QUAL-PAY-002", "customer-history", (("invoice-partial", 50),)),
            ("payment-multiple", "ACP-QUAL-PAY-003", "customer-active", (("invoice-unpaid", 30), ("invoice-multiple", 30))),
        )
        for key, ref, customer_key, applications in payment_specs:
            payment_payload: dict[str, object] = {
                "PaymentRefNum": ref,
                "CustomerRef": {"value": str(customers[customer_key]["Id"])},
                "PaymentMethodRef": {"value": str(payment_method["Id"])},
                "TxnDate": "2026-08-10",
                "PrivateNote": FIXTURE_TAG,
                "TotalAmt": sum(amount for _, amount in applications),
                "Line": [
                    {"Amount": amount, "LinkedTxn": [{"TxnId": str(invoices[invoice_key]["Id"]), "TxnType": "Invoice"}]}
                    for invoice_key, amount in applications
                ],
            }
            value, was_created = await self._ensure_transaction(
                "Payment",
                key,
                ref,
                payment_payload,
                lookup_field="PaymentRefNum",
            )
            objects.append(_fixture_object("payment", key, value))
            created += was_created
            reused += not was_created

        credit_payload: dict[str, object] = {
            "DocNumber": "ACP-QUAL-CM-001",
            "TxnDate": "2026-08-11",
            "CustomerRef": {"value": str(customers["customer-active"]["Id"])},
            "PrivateNote": FIXTURE_TAG,
            "Line": [_sales_line(20, str(items["item-service"]["Id"]))],
        }
        credit, was_created = await self._ensure_transaction("CreditMemo", "credit-memo", "ACP-QUAL-CM-001", credit_payload)
        objects.append(_fixture_object("credit_memo", "credit-memo", credit))
        created += was_created
        reused += not was_created

        bill_specs = (("bill-unpaid", "ACP-QUAL-BILL-001", 150), ("bill-partial", "ACP-QUAL-BILL-002", 200))
        bills: dict[str, dict[str, object]] = {}
        for key, doc, amount in bill_specs:
            bill_payload: dict[str, object] = {
                "DocNumber": doc,
                "TxnDate": "2026-08-03",
                "DueDate": "2026-09-03",
                "VendorRef": {"value": str(vendor["Id"])},
                "PrivateNote": FIXTURE_TAG,
                "Line": [_expense_line(amount, refs["expense"])],
            }
            value, was_created = await self._ensure_transaction(
                "Bill", key, doc, bill_payload
            )
            bills[key] = value
            objects.append(_fixture_object("bill", key, value))
            created += was_created
            reused += not was_created

        bill_payment_payload: dict[str, object] = {
            "DocNumber": "ACP-QUAL-BP-001",
            "TxnDate": "2026-08-12",
            "VendorRef": {"value": str(vendor["Id"])},
            "PayType": "Check",
            "CheckPayment": {"BankAccountRef": {"value": refs["bank"]}},
            "TotalAmt": 75,
            "Line": [{"Amount": 75, "LinkedTxn": [{"TxnId": str(bills["bill-partial"]["Id"]), "TxnType": "Bill"}]}],
        }
        bill_payment, was_created = await self._ensure_transaction("BillPayment", "bill-payment", "ACP-QUAL-BP-001", bill_payment_payload)
        objects.append(_fixture_object("bill_payment", "bill-payment", bill_payment))
        created += was_created
        reused += not was_created

        purchase_payload: dict[str, object] = {
            "TxnDate": "2026-08-04",
            "PaymentType": "Cash",
            "AccountRef": {"value": refs["bank"]},
            "EntityRef": {"value": str(vendor["Id"]), "type": "Vendor"},
            "PrivateNote": f"{FIXTURE_TAG}:ACP-QUAL-PUR-001",
            "Line": [_expense_line(60, refs["expense"])],
        }
        purchase, was_created = await self._ensure_private_note("Purchase", "purchase", "ACP-QUAL-PUR-001", purchase_payload)
        objects.append(_fixture_object("purchase", "purchase", purchase))
        created += was_created
        reused += not was_created

        vendor_credit_payload: dict[str, object] = {
            "DocNumber": "ACP-QUAL-VC-001",
            "TxnDate": "2026-08-13",
            "VendorRef": {"value": str(vendor["Id"])},
            "PrivateNote": FIXTURE_TAG,
            "Line": [_expense_line(25, refs["expense"])],
        }
        vendor_credit, was_created = await self._ensure_transaction("VendorCredit", "vendor-credit", "ACP-QUAL-VC-001", vendor_credit_payload)
        objects.append(_fixture_object("vendor_credit", "vendor-credit", vendor_credit))
        created += was_created
        reused += not was_created

        journal_specs = (
            ("journal-opening", "ACP-QUAL-JE-001", 500, refs["bank"], refs["equity"], "2025-12-31"),
            ("journal-adjustment", "ACP-QUAL-JE-002", 40, refs["expense"], refs["equity"], "2026-08-15"),
        )
        for key, doc, amount, debit, credit_ref, txn_date in journal_specs:
            journal_payload: dict[str, object] = {
                "DocNumber": doc,
                "TxnDate": txn_date,
                "PrivateNote": FIXTURE_TAG,
                "Line": [_journal_line(amount, "Debit", debit), _journal_line(amount, "Credit", credit_ref)],
            }
            value, was_created = await self._ensure_transaction(
                "JournalEntry", key, doc, journal_payload
            )
            objects.append(_fixture_object("journal_entry", key, value))
            created += was_created
            reused += not was_created

        transfer_payload: dict[str, object] = {
            "TxnDate": "2026-08-16",
            "Amount": 100,
            "FromAccountRef": {"value": refs["bank"]},
            "ToAccountRef": {"value": refs["bank_secondary"]},
            "PrivateNote": f"{FIXTURE_TAG}:ACP-QUAL-XFER-001",
        }
        transfer, was_created = await self._ensure_private_note("Transfer", "transfer", "ACP-QUAL-XFER-001", transfer_payload)
        objects.append(_fixture_object("transfer", "transfer", transfer))
        created += was_created
        reused += not was_created

        return self._seal(objects, created=created, reused=reused)

    async def update_controlled_change(self) -> dict[str, str]:
        manifest = _read_json(self.fixture_root / "fixture-manifest.json")
        objects = manifest.get("objects")
        if not isinstance(objects, list):
            raise SandboxFixtureError("fixture_manifest_invalid")
        record = next((item for item in objects if isinstance(item, dict) and item.get("fixture_key") == "customer-active"), None)
        if not isinstance(record, dict):
            raise SandboxFixtureError("fixture_change_subject_missing")
        current = await self._get_entity("Customer", str(record["native_id"]))
        before = _digest(current)
        marker = f"{FIXTURE_TAG}:CONTROLLED-CHANGE-V1"
        if current.get("Notes") != marker:
            updated = await self._post(
                "Customer",
                {
                    "Id": current["Id"],
                    "SyncToken": current["SyncToken"],
                    "sparse": True,
                    "Notes": marker,
                },
            )
        else:
            updated = current
        change = {
            "schema_version": "qbo-sandbox-controlled-change/v1",
            "fixture_digest": str(manifest["fixture_digest"]),
            "fixture_key": "customer-active",
            "native_id_hash": hashlib.sha256(str(updated["Id"]).encode()).hexdigest(),
            "before_sha256": before,
            "after_sha256": _digest(updated),
        }
        change["change_digest"] = _digest(change)
        _write_protected(self.fixture_root / "controlled-change.json", change)
        return {"state": "CHANGED" if before != change["after_sha256"] else "ALREADY_CURRENT", "change_digest": str(change["change_digest"])}

    def _seal(self, objects: list[FixtureObject], *, created: int, reused: int) -> SandboxFixtureResult:
        ordered = sorted(objects, key=lambda item: (item.family, item.fixture_key))
        expected = expected_economic_manifest()
        document: dict[str, object] = {
            "schema_version": FIXTURE_VERSION,
            "authority_digest": self.authority.digest,
            "environment": "sandbox",
            "realm_id_hash": hashlib.sha256(self.authority.realm_id.encode()).hexdigest(),
            "fixture_tag": FIXTURE_TAG,
            "objects": [item.__dict__ for item in ordered],
            "expected_ledger_digest": expected["manifest_sha256"],
        }
        document["fixture_digest"] = _digest(document)
        _write_protected(self.fixture_root / "expected-ledger.json", expected)
        _write_protected(self.fixture_root / "fixture-manifest.json", document)
        return SandboxFixtureResult(
            state="CREATED" if created else "ALREADY_CURRENT",
            fixture_digest=str(document["fixture_digest"]),
            expected_ledger_digest=str(expected["manifest_sha256"]),
            counts=_counts_from_objects(document["objects"]),
            created=created,
            reused=reused,
        )

    async def _ensure_named(self, native_type: str, fixture_key: str, payload: dict[str, object], *, name_field: str = "DisplayName") -> tuple[dict[str, object], bool]:
        matches = await self._query(native_type, name_field, str(payload[name_field]))
        if len(matches) > 1:
            raise SandboxFixtureError("fixture_identity_ambiguous")
        if matches:
            value = matches[0]
            marker = value.get("Notes") or value.get("Description")
            synthetic_name = str(value.get(name_field, "")).startswith(
                "ACP Qualification"
            )
            if marker != FIXTURE_TAG and not synthetic_name:
                raise SandboxFixtureError("fixture_identity_conflict")
            return value, False
        return await self._post(native_type, payload), True

    async def _ensure_transaction(self, native_type: str, fixture_key: str, identity: str, payload: dict[str, object], *, lookup_field: str = "DocNumber") -> tuple[dict[str, object], bool]:
        matches = await self._query(native_type, lookup_field, identity)
        if len(matches) > 1:
            raise SandboxFixtureError("fixture_identity_ambiguous")
        if matches:
            return matches[0], False
        return await self._post(native_type, payload), True

    async def _ensure_private_note(self, native_type: str, fixture_key: str, identity: str, payload: dict[str, object]) -> tuple[dict[str, object], bool]:
        marker = f"{FIXTURE_TAG}:{identity}"
        matches = [
            item
            for item in await self._query_all(native_type)
            if item.get("PrivateNote") == marker
        ]
        if len(matches) > 1:
            raise SandboxFixtureError("fixture_identity_ambiguous")
        if matches:
            return matches[0], False
        return await self._post(native_type, payload), True

    async def _query(self, native_type: str, field: str, value: str) -> list[dict[str, object]]:
        escaped = value.replace("'", "\\'")
        query = f"select * from {native_type} where {field} = '{escaped}' maxresults 10"
        url = f"{self.api_base}/{self.authority.realm_id}/query?" + urlencode({"query": query, "minorversion": self.minor_version})
        response = await self._request("GET", url, None)
        document = response.json()
        query_response = document.get("QueryResponse")
        if not isinstance(query_response, dict):
            raise SandboxFixtureError("fixture_query_response_invalid")
        rows = query_response.get(native_type, [])
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise SandboxFixtureError("fixture_query_response_invalid")
        return rows

    async def _query_all(self, native_type: str) -> list[dict[str, object]]:
        query = f"select * from {native_type} maxresults 1000"
        url = f"{self.api_base}/{self.authority.realm_id}/query?" + urlencode({"query": query, "minorversion": self.minor_version})
        response = await self._request("GET", url, None)
        document = response.json()
        query_response = document.get("QueryResponse")
        if not isinstance(query_response, dict):
            raise SandboxFixtureError("fixture_query_response_invalid")
        rows = query_response.get(native_type, [])
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise SandboxFixtureError("fixture_query_response_invalid")
        return rows

    async def _get_entity(self, native_type: str, native_id: str) -> dict[str, object]:
        url = f"{self.api_base}/{self.authority.realm_id}/{native_type.lower()}/{native_id}?minorversion={self.minor_version}"
        response = await self._request("GET", url, None)
        value = response.json().get(native_type)
        if not isinstance(value, dict):
            raise SandboxFixtureError("fixture_entity_response_invalid")
        return value

    async def _post(self, native_type: str, payload: dict[str, object]) -> dict[str, object]:
        url = f"{self.api_base}/{self.authority.realm_id}/{native_type.lower()}?minorversion={self.minor_version}"
        response = await self._request("POST", url, json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
        value = response.json().get(native_type)
        if not isinstance(value, dict) or not isinstance(value.get("Id"), str):
            raise SandboxFixtureError("fixture_create_response_invalid")
        return value

    async def _request(self, method: str, url: str, body: bytes | None) -> HttpResponse:
        if not url.startswith(self.api_base + "/"):
            raise SandboxFixtureError("fixture_destination_rejected")
        token = await self.token_manager.access_token()
        response = await self.transport.request(
            method=method,
            url=url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"},
            body=body,
        )
        if response.status != 200:
            raise SandboxFixtureError(f"fixture_provider_rejected_{response.status}")
        return response

class SandboxFixtureHttpTransport:
    """Mutation transport restricted to the one Intuit sandbox API host."""

    def __init__(self) -> None:
        import httpx

        self.client = httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10), follow_redirects=False)

    async def request(self, *, method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> HttpResponse:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "sandbox-quickbooks.api.intuit.com":
            raise SandboxFixtureError("fixture_destination_rejected")
        if method not in {"GET", "POST"}:
            raise SandboxFixtureError("fixture_method_rejected")
        response = await self.client.request(method, url, headers=headers, content=body)
        return HttpResponse(status=response.status_code, headers=dict(response.headers), body=response.content)


def build_fixture_service(authority: SandboxFixtureAuthority, configuration: Settings = settings) -> SandboxFixtureService:
    if not configuration.qbo_sandbox_enabled or configuration.qbo_production_enabled:
        raise SandboxFixtureError("fixture_environment_not_isolated")
    root = _runtime_root(configuration); repository = Path(configuration.qbo_repository_root).resolve(); marker = _read_json(root / "connections" / "verified.json")
    if marker.get("realm_id") != authority.realm_id or marker.get("environment") != "sandbox":
        raise SandboxFixtureError("fixture_realm_mismatch")
    expected = ProtectedSandboxCompanyBinding(root / "configuration").read(); provider = ProtectedSandboxSecretProvider(root=root / "secrets", repository_root=repository); oauth = IntuitOAuthClient(environment=IntuitEnvironment.SANDBOX, transport=IntuitHttpTransport(), secrets=provider, credential_reference=provider.CLIENT_REFERENCE); binding = RealmBinding(environment=IntuitEnvironment.SANDBOX, realm_id=authority.realm_id, expected_company_name=expected, credential_reference=provider.CLIENT_REFERENCE, token_reference=provider.TOKEN_REFERENCE)
    return SandboxFixtureService(authority=authority, token_manager=SerializedTokenManager(oauth=oauth, secrets=provider, binding=binding), transport=SandboxFixtureHttpTransport(), runtime_root=root, minor_version=configuration.qbo_sandbox_api_minor_version)


def _sales_line(amount: int, item_id: str) -> dict[str, object]:
    return {"Amount": amount, "DetailType": "SalesItemLineDetail", "Description": FIXTURE_TAG, "SalesItemLineDetail": {"ItemRef": {"value": item_id}, "Qty": 1, "UnitPrice": amount}}


def _account(name: str, account_type: str, account_subtype: str) -> dict[str, object]:
    return {
        "Name": name,
        "AccountType": account_type,
        "AccountSubType": account_subtype,
        "Description": FIXTURE_TAG,
    }


def _expense_line(amount: int, account_id: str) -> dict[str, object]:
    return {"Amount": amount, "DetailType": "AccountBasedExpenseLineDetail", "Description": FIXTURE_TAG, "AccountBasedExpenseLineDetail": {"AccountRef": {"value": account_id}}}


def _journal_line(amount: int, posting_type: str, account_id: str) -> dict[str, object]:
    return {"Amount": amount, "DetailType": "JournalEntryLineDetail", "Description": FIXTURE_TAG, "JournalEntryLineDetail": {"PostingType": posting_type, "AccountRef": {"value": account_id}}}


def _fixture_object(family: str, fixture_key: str, value: Mapping[str, object]) -> FixtureObject:
    return FixtureObject(family=family, fixture_key=fixture_key, native_id=str(value["Id"]), sync_token=str(value.get("SyncToken", "0")), payload_sha256=_digest(value))


def _counts_from_objects(objects: object) -> dict[str, int]:
    if not isinstance(objects, list):
        raise SandboxFixtureError("fixture_manifest_invalid")
    counts: dict[str, int] = {}
    for item in objects:
        if not isinstance(item, dict) or not isinstance(item.get("family"), str):
            raise SandboxFixtureError("fixture_manifest_invalid")
        family = str(item["family"]); counts[family] = counts.get(family, 0) + 1
    return dict(sorted(counts.items()))


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _read_json(path: Path) -> dict[str, object]:
    try: value = json.loads(path.read_bytes())
    except (FileNotFoundError, json.JSONDecodeError) as error: raise SandboxFixtureError("fixture_authority_missing") from error
    if not isinstance(value, dict): raise SandboxFixtureError("fixture_document_invalid")
    return value


def _write_protected(path: Path, document: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True); os.chmod(path.parent, 0o700); rendered=json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    if path.exists():
        if path.read_bytes() != rendered: raise SandboxFixtureError("fixture_immutable_conflict")
        return
    temporary=path.with_suffix(".tmp"); descriptor=os.open(temporary, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor,"wb") as target: target.write(rendered); target.flush(); os.fsync(target.fileno())
        os.replace(temporary,path); os.chmod(path,0o600)
    finally: temporary.unlink(missing_ok=True)


def _safe_result(result: SandboxFixtureResult) -> dict[str, object]:
    return {"state": result.state, "fixture_digest": result.fixture_digest, "expected_ledger_digest": result.expected_ledger_digest, "counts": dict(result.counts), "created": result.created, "reused": result.reused}


async def _main_async(arguments: argparse.Namespace) -> None:
    if arguments.command in {"create", "controlled-change"} and not arguments.authorize_fixture_mutation:
        raise SandboxFixtureError("fixture_mutation_not_authorized")
    root=_runtime_root(settings); marker=_read_json(root/"connections"/"verified.json"); authority=SandboxFixtureAuthority(realm_id=str(marker["realm_id"]), repository_sha=arguments.repository_sha, actor=arguments.actor, authorization_id=arguments.authorization_id); service=build_fixture_service(authority)
    if arguments.command == "qualify": print(json.dumps(_safe_result(await service.qualify()), sort_keys=True))
    elif arguments.command == "create": print(json.dumps(_safe_result(await service.create()), sort_keys=True))
    else: print(json.dumps(await service.update_controlled_change(), sort_keys=True))


def main() -> None:
    parser=argparse.ArgumentParser(description="Manage authorized synthetic QBO sandbox qualification fixtures"); parser.add_argument("command",choices=("qualify","create","controlled-change")); parser.add_argument("--repository-sha",required=True); parser.add_argument("--actor",required=True); parser.add_argument("--authorization-id",default="MIGRATION.CONTINUOUS.PRODUCTION.12H.1"); parser.add_argument("--authorize-fixture-mutation",action="store_true"); arguments=parser.parse_args()
    try: asyncio.run(_main_async(arguments))
    except (SandboxFixtureError,SandboxRuntimeError) as error: print(json.dumps({"state":"REJECTED","error_code":error.code},sort_keys=True)); raise SystemExit(2) from None


if __name__ == "__main__": main()
