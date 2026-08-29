from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from app.qbo_source.intuit import HttpResponse
from app.qbo_source.sandbox_fixture import (
    FIXTURE_TAG,
    SandboxFixtureAuthority,
    SandboxFixtureError,
    SandboxFixtureService,
    expected_economic_manifest,
)


class TokenManager:
    async def access_token(self) -> str:
        return "protected-token"


class FixtureTransport:
    def __init__(self) -> None:
        self.next_id = 100
        self.rows: dict[str, list[dict[str, object]]] = {
            "Account": [
                {"Id": "1", "AccountType": "Bank", "Active": True},
                {"Id": "2", "AccountType": "Bank", "Active": True},
                {"Id": "3", "AccountType": "Income", "Active": True},
                {"Id": "4", "AccountType": "Expense", "Active": True},
                {"Id": "5", "AccountType": "Equity", "Active": True},
            ]
        }
        self.posts = 0

    async def request(self, *, method: str, url: str, headers: object, body: bytes | None) -> HttpResponse:
        del headers
        if method == "GET":
            query = parse_qs(urlparse(url).query).get("query", [""])[0]
            native_type = query.split(" from ", 1)[1].split(" ", 1)[0]
            rows = list(self.rows.get(native_type, []))
            if " where " in query:
                condition = query.split(" where ", 1)[1].split(" maxresults", 1)[0]
                field, value = condition.split(" = ", 1)
                expected = value.strip("'")
                rows = [row for row in rows if row.get(field) == expected]
            return _response({"QueryResponse": {native_type: rows}})
        assert body is not None
        native_type = urlparse(url).path.rsplit("/", 1)[-1]
        mapping = {
            "billpayment": "BillPayment",
            "creditmemo": "CreditMemo",
            "journalentry": "JournalEntry",
            "paymentmethod": "PaymentMethod",
            "vendorcredit": "VendorCredit",
        }
        native_type = mapping.get(native_type, native_type.title())
        payload = json.loads(body)
        payload.update({"Id": str(self.next_id), "SyncToken": "0"})
        self.next_id += 1
        self.posts += 1
        self.rows.setdefault(native_type, []).append(payload)
        return _response({native_type: payload})


def _response(document: dict[str, object]) -> HttpResponse:
    return HttpResponse(
        status=200,
        headers={},
        body=json.dumps(document, sort_keys=True).encode(),
    )


def _authority() -> SandboxFixtureAuthority:
    return SandboxFixtureAuthority(
        realm_id="123456789",
        repository_sha="a" * 40,
        actor="sandbox-fixture-actor",
        authorization_id="owner-approval",
    )


def _runtime(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    (root / "connections").mkdir(parents=True)
    (root / "connections" / "verified.json").write_text(
        json.dumps(
            {
                "environment": "sandbox",
                "realm_id": "123456789",
                "acquisition_eligible": True,
            }
        )
    )
    return root


def test_authority_rejects_production() -> None:
    with pytest.raises(SandboxFixtureError, match="fixture_production_forbidden"):
        SandboxFixtureAuthority(
            realm_id="123",
            repository_sha="a" * 40,
            actor="actor",
            authorization_id="approval",
            environment="production",
        )


def test_expected_manifest_uses_exact_decimal_strings() -> None:
    document = expected_economic_manifest()
    assert document["values"]["ar_net_customer_balance"] == "250.00"  # type: ignore[index]
    assert document["values"]["journal_debits"] == "540.00"  # type: ignore[index]
    assert len(str(document["manifest_sha256"])) == 64


@pytest.mark.asyncio
async def test_fixture_creation_is_protected_and_idempotent(tmp_path: Path) -> None:
    transport = FixtureTransport()
    service = SandboxFixtureService(
        authority=_authority(),
        token_manager=TokenManager(),  # type: ignore[arg-type]
        transport=transport,
        runtime_root=_runtime(tmp_path),
        minor_version=75,
    )
    result = await service.create()
    assert result.state == "CREATED"
    assert result.counts == {
        "account": 15,
        "bill": 2,
        "bill_payment": 1,
        "credit_memo": 1,
        "customer": 2,
        "invoice": 4,
        "item": 2,
        "journal_entry": 2,
        "payment": 3,
        "payment_method": 1,
        "purchase": 1,
        "transfer": 1,
        "term": 1,
        "vendor": 1,
        "vendor_credit": 1,
    }
    assert transport.posts == 38
    manifest = service.fixture_root / "fixture-manifest.json"
    expected = service.fixture_root / "expected-ledger.json"
    assert manifest.stat().st_mode & 0o777 == 0o600
    assert expected.stat().st_mode & 0o777 == 0o600
    assert service.fixture_root.stat().st_mode & 0o777 == 0o700
    replay = await service.create()
    assert replay.state == "ALREADY_CURRENT"
    assert replay.fixture_digest == result.fixture_digest
    assert transport.posts == 38


@pytest.mark.asyncio
async def test_wrong_realm_fails_before_mutation(tmp_path: Path) -> None:
    root = _runtime(tmp_path)
    marker = json.loads((root / "connections" / "verified.json").read_text())
    marker["realm_id"] = "987654321"
    (root / "connections" / "verified.json").write_text(json.dumps(marker))
    transport = FixtureTransport()
    service = SandboxFixtureService(
        authority=_authority(),
        token_manager=TokenManager(),  # type: ignore[arg-type]
        transport=transport,
        runtime_root=root,
        minor_version=75,
    )
    with pytest.raises(SandboxFixtureError, match="fixture_realm_mismatch"):
        await service.create()
    assert transport.posts == 0


def test_synthetic_labels_contain_no_real_business_identity() -> None:
    assert FIXTURE_TAG.startswith("ACP-QBO-QUAL")
