from __future__ import annotations

import asyncio
import json
import urllib.parse
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone

import pytest

from app.qbo_source.contracts import AcquisitionRequest, EntityKind, SnapshotIdentity
from app.qbo_source.intuit import (
    ACCOUNTING_SCOPE,
    ENTITY_QUERY_NAMES,
    ClientCredential,
    HttpResponse,
    IntuitAuthenticationError,
    IntuitEnvironment,
    IntuitHttpTransport,
    IntuitOAuthClient,
    IntuitProtocolError,
    IntuitReadOnlyAdapter,
    OAuthAuthorizationCoordinator,
    OAuthToken,
    PendingAuthorization,
    RealmBinding,
    SerializedTokenManager,
)


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 26, 12, tzinfo=timezone.utc)
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        return self.current

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


class FakeSecrets:
    def __init__(self, token: OAuthToken | None = None) -> None:
        self.credential = ClientCredential("synthetic-client", "synthetic-secret")
        self.token = token
        self.put_count = 0
        self.deleted = False

    async def get_client_credential(self, reference: str) -> ClientCredential:
        assert reference == "secret://synthetic/client"
        return self.credential

    async def get_token(self, reference: str) -> OAuthToken:
        assert reference == "secret://synthetic/token"
        if self.token is None:
            raise KeyError("synthetic token absent")
        return self.token

    async def put_token(
        self, reference: str, token: OAuthToken, *, expected_generation: int | None
    ) -> None:
        assert reference == "secret://synthetic/token"
        if expected_generation is not None:
            assert self.token is not None
            assert self.token.generation == expected_generation
        self.token = token
        self.put_count += 1

    async def delete_token(self, reference: str) -> None:
        assert reference == "secret://synthetic/token"
        self.token = None
        self.deleted = True


class SequenceTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses
        self.requests: list[dict[str, object]] = []

    async def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> HttpResponse:
        self.requests.append(
            {"method": method, "url": url, "headers": dict(headers), "body": body}
        )
        return self.responses.pop(0)


class FakeStates:
    def __init__(self) -> None:
        self.values: dict[str, PendingAuthorization] = {}

    async def put(self, pending: PendingAuthorization) -> None:
        if pending.state in self.values:
            raise ValueError("state already exists")
        self.values[pending.state] = pending

    async def consume(self, state: str) -> PendingAuthorization | None:
        return self.values.pop(state, None)


def response(status: int, document: object, **headers: str) -> HttpResponse:
    return HttpResponse(status, headers, json.dumps(document).encode())


def token(clock: FakeClock, *, expired: bool = False) -> OAuthToken:
    return OAuthToken(
        access_token="synthetic-access",
        refresh_token="synthetic-refresh",
        access_expires_at=clock.now()
        + (timedelta(seconds=-1) if expired else timedelta(hours=1)),
        refresh_expires_at=clock.now() + timedelta(days=100),
        scope=ACCOUNTING_SCOPE,
        generation=0,
    )


def binding() -> RealmBinding:
    return RealmBinding(
        environment=IntuitEnvironment.SANDBOX,
        realm_id="synthetic-realm",
        expected_company_name="Synthetic Plumbing Sandbox",
        credential_reference="secret://synthetic/client",
        token_reference="secret://synthetic/token",
    )


def snapshot() -> SnapshotIdentity:
    return SnapshotIdentity(
        snapshot_id="synthetic-snapshot",
        realm_id="synthetic-realm",
        environment="sandbox",
        accounting_date_cutoff=date(2026, 8, 25),
        cutoff_timezone="America/New_York",
        started_at=datetime(2026, 8, 26, 12, tzinfo=timezone.utc),
        api_minor_version=75,
    )


def test_every_contract_entity_has_explicit_official_acquisition_route() -> None:
    assert set(ENTITY_QUERY_NAMES) | {EntityKind.COMPANY_INFO} == set(EntityKind)


@pytest.mark.asyncio
async def test_authorization_exchange_refresh_and_revoke() -> None:
    clock = FakeClock()
    secrets = FakeSecrets()
    transport = SequenceTransport(
        [
            response(
                200,
                {
                    "access_token": "synthetic-a1",
                    "refresh_token": "synthetic-r1",
                    "expires_in": 3600,
                    "x_refresh_token_expires_in": 8_640_000,
                    "scope": ACCOUNTING_SCOPE,
                },
            ),
            response(
                200,
                {
                    "access_token": "synthetic-a2",
                    "refresh_token": "synthetic-r2",
                    "expires_in": 3600,
                    "scope": ACCOUNTING_SCOPE,
                },
            ),
            response(200, {}),
        ]
    )
    oauth = IntuitOAuthClient(
        environment=IntuitEnvironment.SANDBOX,
        transport=transport,
        secrets=secrets,
        credential_reference="secret://synthetic/client",
        clock=clock,
    )

    url = await oauth.build_authorization_url(
        redirect_uri="https://localhost.example/qbo/callback", state="s" * 32
    )
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert query["scope"] == [ACCOUNTING_SCOPE]
    assert query["response_type"] == ["code"]
    first = await oauth.exchange_code(
        code="synthetic-code",
        redirect_uri="https://localhost.example/qbo/callback",
        token_reference="secret://synthetic/token",
    )
    second = await oauth.refresh(first)
    await secrets.put_token(
        "secret://synthetic/token", second, expected_generation=first.generation
    )
    await oauth.revoke(token_reference="secret://synthetic/token")

    assert second.generation == 1
    assert secrets.deleted
    assert all(
        "synthetic-secret" not in str(request["body"]) for request in transport.requests
    )


@pytest.mark.asyncio
async def test_callback_state_is_single_use_and_returns_realm_binding_input() -> None:
    clock = FakeClock()
    secrets = FakeSecrets()
    transport = SequenceTransport(
        [
            response(
                200,
                {
                    "access_token": "synthetic-a1",
                    "refresh_token": "synthetic-r1",
                    "expires_in": 3600,
                    "scope": ACCOUNTING_SCOPE,
                },
            )
        ]
    )
    oauth = IntuitOAuthClient(
        environment=IntuitEnvironment.SANDBOX,
        transport=transport,
        secrets=secrets,
        credential_reference="secret://synthetic/client",
        clock=clock,
    )
    coordinator = OAuthAuthorizationCoordinator(
        oauth=oauth,
        states=FakeStates(),
        state_factory=lambda: "state" * 8,
        clock=clock,
    )
    url = await coordinator.begin(
        redirect_uri="https://localhost.example/qbo/callback",
        token_reference="secret://synthetic/token",
    )

    authorized = await coordinator.complete(
        code="synthetic-code", state="state" * 8, realm_id="synthetic-realm"
    )

    assert "state=" in url
    assert authorized.realm_id == "synthetic-realm"
    with pytest.raises(IntuitAuthenticationError, match="oauth_state_invalid"):
        await coordinator.complete(
            code="replay", state="state" * 8, realm_id="synthetic-realm"
        )


@pytest.mark.asyncio
async def test_refresh_is_serialized_and_rotated_once() -> None:
    clock = FakeClock()
    secrets = FakeSecrets(token(clock, expired=True))
    transport = SequenceTransport(
        [
            response(
                200,
                {
                    "access_token": "synthetic-fresh",
                    "refresh_token": "synthetic-rotated",
                    "expires_in": 3600,
                    "scope": ACCOUNTING_SCOPE,
                },
            )
        ]
    )
    oauth = IntuitOAuthClient(
        environment=IntuitEnvironment.SANDBOX,
        transport=transport,
        secrets=secrets,
        credential_reference="secret://synthetic/client",
        clock=clock,
    )
    manager = SerializedTokenManager(
        oauth=oauth, secrets=secrets, binding=binding(), clock=clock
    )

    values = await asyncio.gather(*(manager.access_token() for _ in range(8)))

    assert values == ["synthetic-fresh"] * 8
    assert secrets.put_count == 1
    assert len(transport.requests) == 1


@pytest.mark.asyncio
async def test_company_verification_pagination_retry_and_fidelity() -> None:
    clock = FakeClock()
    secrets = FakeSecrets(token(clock))
    transport = SequenceTransport(
        [
            response(429, {}, **{"Retry-After": "2"}),
            response(
                200,
                {
                    "CompanyInfo": {
                        "Id": "synthetic-realm",
                        "CompanyName": "Synthetic Plumbing Sandbox",
                        "SyncToken": "4",
                    }
                },
            ),
            response(
                200,
                {
                    "QueryResponse": {
                        "Invoice": [
                            {
                                "Id": "synthetic-invoice-1",
                                "SyncToken": "7",
                                "TxnDate": "2026-08-25",
                                "Balance": 125.0,
                                "TotalAmt": 125.0,
                                "CustomerRef": {"value": "synthetic-customer-1"},
                                "CurrencyRef": {"value": "USD"},
                                "LinkedTxn": [
                                    {
                                        "TxnId": "synthetic-payment-1",
                                        "TxnType": "Payment",
                                    }
                                ],
                                "MetaData": {
                                    "CreateTime": "2026-08-25T10:00:00-04:00",
                                    "LastUpdatedTime": "2026-08-25T11:00:00-04:00",
                                },
                            }
                        ],
                        "startPosition": 1,
                        "maxResults": 1,
                    }
                },
                intuit_tid="synthetic-tid-1",
            ),
            response(200, {"QueryResponse": {}}),
        ]
    )
    oauth = IntuitOAuthClient(
        environment=IntuitEnvironment.SANDBOX,
        transport=transport,
        secrets=secrets,
        credential_reference="secret://synthetic/client",
        clock=clock,
    )
    manager = SerializedTokenManager(
        oauth=oauth, secrets=secrets, binding=binding(), clock=clock
    )
    adapter = IntuitReadOnlyAdapter(
        binding=binding(),
        token_manager=manager,
        transport=transport,
        clock=clock,
    )
    request = AcquisitionRequest(
        snapshot=snapshot(),
        entity_kinds=(EntityKind.COMPANY_INFO, EntityKind.INVOICE),
        page_size=1,
    )

    acquired = [item async for item in adapter.acquire(request)]

    assert [item.native_id for item in acquired] == [
        "synthetic-realm",
        "synthetic-invoice-1",
    ]
    invoice = acquired[1]
    assert invoice.sync_token == "7"
    assert invoice.source_status == "open"
    assert invoice.source_accounting_meaning["Balance"] == 125.0
    assert invoice.relationship_ids == (
        "CurrencyRef:USD",
        "CustomerRef:synthetic-customer-1",
        "TxnId:synthetic-payment-1",
    )
    assert invoice.raw_payload["Balance"] == 125.0
    assert clock.sleeps == [2.0]
    assert all(request["method"] == "GET" for request in transport.requests)
    assert all(
        "minorversion=75" in str(request["url"]) for request in transport.requests
    )


@pytest.mark.asyncio
async def test_company_mismatch_fails_before_entity_query() -> None:
    clock = FakeClock()
    secrets = FakeSecrets(token(clock))
    transport = SequenceTransport(
        [response(200, {"CompanyInfo": {"Id": "x", "CompanyName": "Wrong"}})]
    )
    oauth = IntuitOAuthClient(
        environment=IntuitEnvironment.SANDBOX,
        transport=transport,
        secrets=secrets,
        credential_reference="secret://synthetic/client",
        clock=clock,
    )
    adapter = IntuitReadOnlyAdapter(
        binding=binding(),
        token_manager=SerializedTokenManager(
            oauth=oauth, secrets=secrets, binding=binding(), clock=clock
        ),
        transport=transport,
        clock=clock,
    )

    with pytest.raises(IntuitAuthenticationError, match="company_identity_mismatch"):
        _ = [
            item
            async for item in adapter.acquire(
                AcquisitionRequest(snapshot(), (EntityKind.ACCOUNT,))
            )
        ]
    assert len(transport.requests) == 1


@pytest.mark.asyncio
async def test_official_transport_rejects_non_intuit_or_write_destinations() -> None:
    transport = IntuitHttpTransport()
    with pytest.raises(IntuitProtocolError, match="destination_rejected"):
        await transport.request(
            method="GET", url="https://example.com/qbo", headers={}, body=None
        )
    with pytest.raises(IntuitProtocolError, match="operation_rejected"):
        await transport.request(
            method="POST",
            url="https://sandbox-quickbooks.api.intuit.com/v3/company/realm/invoice",
            headers={},
            body=b"{}",
        )
    await transport.client.aclose()
