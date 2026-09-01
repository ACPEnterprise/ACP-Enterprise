from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import ClassVar, Protocol
from urllib.parse import urlencode

import httpx

from .contracts import (
    AcquisitionRequest,
    EntityKind,
    QboSourceEnvelope,
    SourceAcquisitionProvider,
)


class IntuitEnvironment(str, Enum):
    SANDBOX = "sandbox"
    PRODUCTION = "production"


@dataclass(frozen=True)
class IntuitEndpoints:
    authorization: str
    token: str
    revoke: str
    api_base: str


ENDPOINTS = {
    IntuitEnvironment.SANDBOX: IntuitEndpoints(
        authorization="https://appcenter.intuit.com/connect/oauth2",
        token="https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
        revoke="https://developer.api.intuit.com/v2/oauth2/tokens/revoke",
        api_base="https://sandbox-quickbooks.api.intuit.com/v3/company",
    ),
    IntuitEnvironment.PRODUCTION: IntuitEndpoints(
        authorization="https://appcenter.intuit.com/connect/oauth2",
        token="https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
        revoke="https://developer.api.intuit.com/v2/oauth2/tokens/revoke",
        api_base="https://quickbooks.api.intuit.com/v3/company",
    ),
}

ACCOUNTING_SCOPE = "com.intuit.quickbooks.accounting"


@dataclass(frozen=True)
class ClientCredential:
    client_id: str
    client_secret: str


@dataclass(frozen=True)
class RealmBinding:
    environment: IntuitEnvironment
    realm_id: str
    expected_company_name: str
    credential_reference: str
    token_reference: str

    def __post_init__(self) -> None:
        if not all(
            (
                self.realm_id,
                self.expected_company_name,
                self.credential_reference,
                self.token_reference,
            )
        ):
            raise ValueError("complete realm binding is required")


@dataclass(frozen=True)
class OAuthToken:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime | None
    scope: str
    generation: int
    realm_id: str | None = None

    def __post_init__(self) -> None:
        if not self.access_token or not self.refresh_token:
            raise ValueError("complete OAuth token material is required")
        if self.access_expires_at.tzinfo is None:
            raise ValueError("token expiry must be timezone-aware")
        if self.scope != ACCOUNTING_SCOPE:
            raise ValueError("unexpected OAuth scope")


@dataclass(frozen=True)
class PendingAuthorization:
    state: str
    environment: IntuitEnvironment
    redirect_uri: str
    token_reference: str
    expires_at: datetime


class AuthorizationStateStore(Protocol):
    async def put(self, pending: PendingAuthorization) -> None: ...

    async def consume(self, state: str) -> PendingAuthorization | None: ...


@dataclass(frozen=True)
class AuthorizedRealm:
    realm_id: str
    token: OAuthToken


class SecretProvider(Protocol):
    async def get_client_credential(self, reference: str) -> ClientCredential: ...

    async def get_token(self, reference: str) -> OAuthToken: ...

    async def put_token(
        self, reference: str, token: OAuthToken, *, expected_generation: int | None
    ) -> None: ...

    async def delete_token(self, reference: str) -> None: ...


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes

    def json(self) -> dict[str, object]:
        value = json.loads(self.body)
        if not isinstance(value, dict):
            raise IntuitProtocolError("response_not_object")
        return value


class HttpTransport(Protocol):
    async def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> HttpResponse: ...


class IntuitHttpTransport:
    """Bounded official HTTPS transport with no payload or credential logging."""

    _allowed_hosts = frozenset(
        {
            "oauth.platform.intuit.com",
            "developer.api.intuit.com",
            "sandbox-quickbooks.api.intuit.com",
            "quickbooks.api.intuit.com",
        }
    )

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        _install_intuit_url_log_filter()
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(30, connect=10), follow_redirects=False
        )

    async def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> HttpResponse:
        parsed = httpx.URL(url)
        if parsed.scheme != "https" or parsed.host not in self._allowed_hosts:
            raise IntuitProtocolError("transport_destination_rejected")
        normalized_method = method.upper()
        if normalized_method not in {"GET", "POST"}:
            raise IntuitProtocolError("transport_method_rejected")
        if normalized_method == "GET" and parsed.host not in {
            "sandbox-quickbooks.api.intuit.com",
            "quickbooks.api.intuit.com",
        }:
            raise IntuitProtocolError("transport_operation_rejected")
        if normalized_method == "POST" and parsed.host not in {
            "oauth.platform.intuit.com",
            "developer.api.intuit.com",
        }:
            raise IntuitProtocolError("transport_operation_rejected")
        response = await self.client.request(
            normalized_method, url, headers=headers, content=body
        )
        return HttpResponse(
            status=response.status_code,
            headers=dict(response.headers),
            body=response.content,
        )


class _IntuitProviderUrlLogFilter(logging.Filter):
    """Suppress httpx records containing realm-scoped or OAuth provider URLs."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "httpx":
            return True
        message = record.getMessage()
        return not any(host in message for host in IntuitHttpTransport._allowed_hosts)


def _install_intuit_url_log_filter() -> None:
    logger = logging.getLogger("httpx")
    if not any(
        isinstance(item, _IntuitProviderUrlLogFilter) for item in logger.filters
    ):
        logger.addFilter(_IntuitProviderUrlLogFilter())


class Clock(Protocol):
    def now(self) -> datetime: ...

    async def sleep(self, seconds: float) -> None: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class IntuitError(RuntimeError):
    def __init__(self, code: str, *, provider_status: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.provider_status = provider_status


class IntuitAuthenticationError(IntuitError):
    pass


class IntuitProtocolError(IntuitError):
    pass


class IntuitRequestError(IntuitError):
    pass


class PartialAcquisitionError(IntuitError):
    def __init__(
        self,
        code: str,
        *,
        entity_kind: str,
        page: int,
        provider_status: int | None = None,
    ) -> None:
        super().__init__(code, provider_status=provider_status)
        self.entity_kind = entity_kind
        self.page = page


def _basic_authorization(credential: ClientCredential) -> str:
    material = f"{credential.client_id}:{credential.client_secret}".encode()
    return "Basic " + base64.b64encode(material).decode("ascii")


class IntuitOAuthClient:
    def __init__(
        self,
        *,
        environment: IntuitEnvironment,
        transport: HttpTransport,
        secrets: SecretProvider,
        credential_reference: str,
        clock: Clock | None = None,
    ) -> None:
        self.environment = environment
        self.endpoints = ENDPOINTS[environment]
        self.transport = transport
        self.secrets = secrets
        self.credential_reference = credential_reference
        self.clock = clock or SystemClock()

    async def build_authorization_url(self, *, redirect_uri: str, state: str) -> str:
        if not redirect_uri.startswith("https://") or len(state) < 32:
            raise ValueError("secure redirect URI and high-entropy state are required")
        credential = await self.secrets.get_client_credential(self.credential_reference)
        query = urlencode(
            {
                "client_id": credential.client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": ACCOUNTING_SCOPE,
                "state": state,
            }
        )
        return f"{self.endpoints.authorization}?{query}"

    async def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
        token_reference: str,
        realm_id: str,
    ) -> OAuthToken:
        if not code or not redirect_uri.startswith("https://") or not realm_id:
            raise ValueError("authorization code and secure redirect URI are required")
        try:
            token = await self._token_request(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                generation=0,
            )
        except IntuitError:
            raise
        except Exception as error:
            raise IntuitAuthenticationError(
                "token_exchange_transport_failed"
            ) from error
        try:
            token = replace(token, realm_id=realm_id)
            await self.secrets.put_token(
                token_reference, token, expected_generation=None
            )
        except Exception as error:
            raise IntuitAuthenticationError("token_persistence_failed") from error
        return token

    async def refresh(self, current: OAuthToken) -> OAuthToken:
        return replace(
            await self._token_request(
                {"grant_type": "refresh_token", "refresh_token": current.refresh_token},
                generation=current.generation + 1,
            ),
            realm_id=current.realm_id,
        )

    async def revoke(self, *, token_reference: str) -> None:
        token = await self.secrets.get_token(token_reference)
        credential = await self.secrets.get_client_credential(self.credential_reference)
        response = await self.transport.request(
            method="POST",
            url=self.endpoints.revoke,
            headers={
                "Authorization": _basic_authorization(credential),
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            body=json.dumps({"token": token.refresh_token}).encode(),
        )
        if response.status not in {200, 204}:
            raise IntuitAuthenticationError("token_revocation_failed")
        await self.secrets.delete_token(token_reference)

    async def _token_request(
        self, fields: Mapping[str, str], *, generation: int
    ) -> OAuthToken:
        credential = await self.secrets.get_client_credential(self.credential_reference)
        response = await self.transport.request(
            method="POST",
            url=self.endpoints.token,
            headers={
                "Authorization": _basic_authorization(credential),
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body=urlencode(fields).encode(),
        )
        if response.status != 200:
            raise IntuitAuthenticationError(
                "token_request_rejected", provider_status=response.status
            )
        payload = response.json()
        try:
            access_token = str(payload["access_token"])
            refresh_token = str(payload["refresh_token"])
            expires_value = payload["expires_in"]
            if not isinstance(expires_value, (str, int, float)):
                raise TypeError
            expires_in = int(expires_value)
        except (KeyError, TypeError, ValueError) as error:
            raise IntuitProtocolError("invalid_token_response") from error
        refresh_seconds = payload.get("x_refresh_token_expires_in")
        if refresh_seconds is not None and not isinstance(
            refresh_seconds, (str, int, float)
        ):
            raise IntuitProtocolError("invalid_token_response")
        now = self.clock.now()
        return OAuthToken(
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_at=now + timedelta(seconds=expires_in),
            refresh_expires_at=(
                now + timedelta(seconds=int(refresh_seconds))
                if refresh_seconds is not None
                else None
            ),
            scope=str(payload.get("scope", ACCOUNTING_SCOPE)),
            generation=generation,
        )


class OAuthAuthorizationCoordinator:
    """Single-use callback contract; state storage must be protected and atomic."""

    def __init__(
        self,
        *,
        oauth: IntuitOAuthClient,
        states: AuthorizationStateStore,
        state_factory: Callable[[], str],
        clock: Clock | None = None,
        state_lifetime: timedelta = timedelta(minutes=10),
    ) -> None:
        self.oauth = oauth
        self.states = states
        self.state_factory = state_factory
        self.clock = clock or SystemClock()
        self.state_lifetime = state_lifetime

    async def begin(self, *, redirect_uri: str, token_reference: str) -> str:
        state = self.state_factory()
        if len(state) < 32:
            raise ValueError("high-entropy OAuth state is required")
        pending = PendingAuthorization(
            state=state,
            environment=self.oauth.environment,
            redirect_uri=redirect_uri,
            token_reference=token_reference,
            expires_at=self.clock.now() + self.state_lifetime,
        )
        await self.states.put(pending)
        return await self.oauth.build_authorization_url(
            redirect_uri=redirect_uri, state=state
        )

    async def complete(
        self, *, code: str, state: str, realm_id: str
    ) -> AuthorizedRealm:
        pending = await self._consume_valid_state(state)
        if not realm_id:
            raise IntuitAuthenticationError("oauth_realm_missing")
        token = await self.oauth.exchange_code(
            code=code,
            redirect_uri=pending.redirect_uri,
            token_reference=pending.token_reference,
            realm_id=realm_id,
        )
        return AuthorizedRealm(realm_id=realm_id, token=token)

    async def reject(self, *, state: str) -> None:
        await self._consume_valid_state(state)
        raise IntuitAuthenticationError("oauth_provider_rejected")

    async def _consume_valid_state(self, state: str) -> PendingAuthorization:
        pending = await self.states.consume(state)
        if pending is None or pending.state != state:
            raise IntuitAuthenticationError("oauth_state_invalid")
        if pending.environment != self.oauth.environment:
            raise IntuitAuthenticationError("oauth_environment_mismatch")
        if pending.expires_at <= self.clock.now():
            raise IntuitAuthenticationError("oauth_state_expired")
        return pending


class SerializedTokenManager:
    _locks: ClassVar[dict[tuple[str, str], asyncio.Lock]] = {}

    def __init__(
        self,
        *,
        oauth: IntuitOAuthClient,
        secrets: SecretProvider,
        binding: RealmBinding,
        clock: Clock | None = None,
        refresh_skew: timedelta = timedelta(minutes=5),
    ) -> None:
        if oauth.environment != binding.environment:
            raise ValueError("OAuth client and realm environment mismatch")
        self.oauth = oauth
        self.secrets = secrets
        self.binding = binding
        self.clock = clock or SystemClock()
        self.refresh_skew = refresh_skew

    async def access_token(self) -> str:
        token = await self.secrets.get_token(self.binding.token_reference)
        self._require_bound_realm(token)
        if token.access_expires_at > self.clock.now() + self.refresh_skew:
            return token.access_token
        key = (self.binding.environment.value, self.binding.realm_id)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            token = await self.secrets.get_token(self.binding.token_reference)
            self._require_bound_realm(token)
            if token.access_expires_at > self.clock.now() + self.refresh_skew:
                return token.access_token
            refreshed = await self.oauth.refresh(token)
            await self.secrets.put_token(
                self.binding.token_reference,
                refreshed,
                expected_generation=token.generation,
            )
            return refreshed.access_token

    def _require_bound_realm(self, token: OAuthToken) -> None:
        if token.realm_id != self.binding.realm_id:
            raise IntuitAuthenticationError("token_realm_mismatch")


ENTITY_QUERY_NAMES: Mapping[EntityKind, str] = {
    EntityKind.ACCOUNT: "Account",
    EntityKind.CUSTOMER: "Customer",
    EntityKind.VENDOR: "Vendor",
    EntityKind.INVOICE: "Invoice",
    EntityKind.PAYMENT: "Payment",
    EntityKind.CREDIT_MEMO: "CreditMemo",
    EntityKind.BILL: "Bill",
    EntityKind.BILL_PAYMENT: "BillPayment",
    EntityKind.VENDOR_CREDIT: "VendorCredit",
    EntityKind.PURCHASE: "Purchase",
    EntityKind.CREDIT_CARD_PAYMENT: "CreditCardPayment",
    EntityKind.DEPOSIT: "Deposit",
    EntityKind.TRANSFER: "Transfer",
    EntityKind.JOURNAL_ENTRY: "JournalEntry",
    EntityKind.TAX_PAYMENT: "TaxPayment",
    EntityKind.TAX_AGENCY: "TaxAgency",
    EntityKind.CLASS: "Class",
    EntityKind.DEPARTMENT: "Department",
    EntityKind.ITEM: "Item",
    EntityKind.EMPLOYEE: "Employee",
    EntityKind.TIME_ACTIVITY: "TimeActivity",
    EntityKind.REFUND_RECEIPT: "RefundReceipt",
    EntityKind.SALES_RECEIPT: "SalesReceipt",
    EntityKind.ESTIMATE: "Estimate",
    EntityKind.PURCHASE_ORDER: "PurchaseOrder",
    EntityKind.TERM: "Term",
    EntityKind.PAYMENT_METHOD: "PaymentMethod",
}


@dataclass(frozen=True)
class PageEvidence:
    entity_kind: str
    page: int
    start_position: int
    returned_count: int
    response_sha256: str
    request_id: str | None


class PageObserver(Protocol):
    async def record_page(self, evidence: PageEvidence, raw_body: bytes) -> None: ...


class NullPageObserver:
    async def record_page(self, evidence: PageEvidence, raw_body: bytes) -> None:
        return None


class IntuitReadOnlyAdapter(SourceAcquisitionProvider):
    def __init__(
        self,
        *,
        binding: RealmBinding,
        token_manager: SerializedTokenManager,
        transport: HttpTransport,
        clock: Clock | None = None,
        page_observer: PageObserver | None = None,
        max_attempts: int = 4,
        max_backoff_seconds: int = 30,
    ) -> None:
        if max_attempts < 1 or max_backoff_seconds < 1:
            raise ValueError("bounded retry configuration is required")
        self.binding = binding
        self.token_manager = token_manager
        self.transport = transport
        self.clock = clock or SystemClock()
        self.page_observer = page_observer or NullPageObserver()
        self.max_attempts = max_attempts
        self.max_backoff_seconds = max_backoff_seconds
        self.endpoints = ENDPOINTS[binding.environment]

    async def acquire(
        self, request: AcquisitionRequest
    ) -> AsyncIterator[QboSourceEnvelope]:
        if request.snapshot.environment != self.binding.environment.value:
            raise ValueError("snapshot and adapter environment mismatch")
        if request.snapshot.realm_id != self.binding.realm_id:
            raise ValueError("snapshot and adapter realm mismatch")
        company_payload = await self._verify_company(request)
        if EntityKind.COMPANY_INFO in request.entity_kinds:
            yield self._envelope(
                request=request,
                kind=EntityKind.COMPANY_INFO,
                native_type="CompanyInfo",
                payload=company_payload,
            )
        for kind in request.entity_kinds:
            if kind == EntityKind.COMPANY_INFO:
                continue
            native_type = ENTITY_QUERY_NAMES.get(kind)
            if native_type is None:
                raise IntuitProtocolError("unsupported_entity_kind")
            async for payload in self._query_pages(request, kind, native_type):
                yield self._envelope(
                    request=request,
                    kind=kind,
                    native_type=native_type,
                    payload=payload,
                )

    async def _verify_company(self, request: AcquisitionRequest) -> dict[str, object]:
        url = (
            f"{self.endpoints.api_base}/{self.binding.realm_id}/companyinfo/"
            f"{self.binding.realm_id}?minorversion={request.snapshot.api_minor_version}"
        )
        response = await self._get(url, request_identity="company_info")
        document = response.json()
        company = document.get("CompanyInfo")
        if not isinstance(company, dict):
            raise IntuitProtocolError("company_info_missing")
        if company.get("CompanyName") != self.binding.expected_company_name:
            raise IntuitAuthenticationError("company_identity_mismatch")
        return company

    async def _query_pages(
        self, request: AcquisitionRequest, kind: EntityKind, native_type: str
    ) -> AsyncIterator[dict[str, object]]:
        start = 1
        page = 1
        seen: set[str] = set()
        while True:
            query = f"select * from {native_type} startposition {start} maxresults {request.page_size}"
            url = (
                f"{self.endpoints.api_base}/{self.binding.realm_id}/query?"
                + urlencode(
                    {
                        "query": query,
                        "minorversion": request.snapshot.api_minor_version,
                    }
                )
            )
            try:
                response = await self._get(
                    url, request_identity=f"{kind.value}:{page}:{start}"
                )
            except IntuitError as error:
                raise PartialAcquisitionError(
                    error.code,
                    entity_kind=kind.value,
                    page=page,
                    provider_status=error.provider_status,
                ) from error
            document = response.json()
            query_response = document.get("QueryResponse")
            if not isinstance(query_response, dict):
                raise PartialAcquisitionError(
                    "query_response_missing", entity_kind=kind.value, page=page
                )
            rows = query_response.get(native_type, [])
            if not isinstance(rows, list) or not all(
                isinstance(row, dict) for row in rows
            ):
                raise PartialAcquisitionError(
                    "query_rows_invalid", entity_kind=kind.value, page=page
                )
            digest = hashlib.sha256(response.body).hexdigest()
            await self.page_observer.record_page(
                PageEvidence(
                    entity_kind=kind.value,
                    page=page,
                    start_position=start,
                    returned_count=len(rows),
                    response_sha256=digest,
                    request_id=response.headers.get("intuit_tid"),
                ),
                response.body,
            )
            for row in rows:
                native_id = row.get("Id")
                if not isinstance(native_id, str) or not native_id:
                    raise PartialAcquisitionError(
                        "native_id_missing", entity_kind=kind.value, page=page
                    )
                if native_id in seen:
                    raise PartialAcquisitionError(
                        "duplicate_native_id", entity_kind=kind.value, page=page
                    )
                seen.add(native_id)
                yield row
            if len(rows) < request.page_size:
                break
            start += len(rows)
            page += 1

    async def _get(self, url: str, *, request_identity: str) -> HttpResponse:
        for attempt in range(1, self.max_attempts + 1):
            token = await self.token_manager.access_token()
            response = await self.transport.request(
                method="GET",
                url=url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                body=None,
            )
            if response.status == 200:
                return response
            if response.status in {401, 403}:
                raise IntuitAuthenticationError("api_authorization_rejected")
            if response.status not in {408, 429, 500, 502, 503, 504}:
                raise IntuitRequestError(
                    "api_request_rejected", provider_status=response.status
                )
            if attempt == self.max_attempts:
                break
            retry_after = response.headers.get("Retry-After")
            delay = min(
                float(retry_after)
                if retry_after and retry_after.isdigit()
                else self._backoff(request_identity, attempt),
                self.max_backoff_seconds,
            )
            await self.clock.sleep(delay)
        raise IntuitRequestError(
            "api_retry_exhausted", provider_status=response.status
        )

    def _backoff(self, request_identity: str, attempt: int) -> float:
        seed = hashlib.sha256(f"{request_identity}:{attempt}".encode()).digest()[0]
        jitter = seed / 255
        return min((2 ** (attempt - 1)) + jitter, self.max_backoff_seconds)

    def _envelope(
        self,
        *,
        request: AcquisitionRequest,
        kind: EntityKind,
        native_type: str,
        payload: Mapping[str, object],
    ) -> QboSourceEnvelope:
        native_id = payload.get("Id")
        if not isinstance(native_id, str) or not native_id:
            raise IntuitProtocolError("native_id_missing")
        metadata = payload.get("MetaData")
        metadata = metadata if isinstance(metadata, dict) else {}
        currency_ref = payload.get("CurrencyRef")
        currency = currency_ref.get("value") if isinstance(currency_ref, dict) else None
        links = _relationship_ids(payload)
        return QboSourceEnvelope.from_native(
            snapshot=request.snapshot,
            native_entity_type=kind.value,
            native_id=native_id,
            payload=payload,
            acquired_at=self.clock.now(),
            sync_token=str(payload["SyncToken"]) if "SyncToken" in payload else None,
            source_created_at=_parse_qbo_datetime(metadata.get("CreateTime")),
            source_updated_at=_parse_qbo_datetime(metadata.get("LastUpdatedTime")),
            relationship_ids=links,
            currency=str(currency) if currency else None,
            source_status=_source_status(payload),
            source_accounting_meaning=_accounting_meaning(native_type, payload),
        )


def _parse_qbo_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise IntuitProtocolError("source_timestamp_invalid") from error
    if parsed.tzinfo is None:
        raise IntuitProtocolError("source_timestamp_missing_timezone")
    return parsed


def _relationship_ids(payload: Mapping[str, object]) -> tuple[str, ...]:
    found: set[str] = set()

    def visit(value: object, key: str = "") -> None:
        if isinstance(value, dict):
            reference = value.get("value")
            if key.endswith("Ref") and isinstance(reference, str) and reference:
                found.add(f"{key}:{reference}")
            for child_key, child in value.items():
                if (
                    child_key in {"TxnId", "TxnLineId"}
                    and isinstance(child, str)
                    and child
                ):
                    found.add(f"{child_key}:{child}")
                visit(child, str(child_key))
        elif isinstance(value, list):
            for child in value:
                visit(child, key)

    visit(payload)
    return tuple(sorted(found))


def _source_status(payload: Mapping[str, object]) -> str | None:
    for key in ("TxnStatus", "status", "Active", "PrintStatus", "EmailStatus"):
        value = payload.get(key)
        if isinstance(value, (str, bool)):
            return str(value)
    balance = payload.get("Balance")
    if isinstance(balance, (str, int, float)):
        return "open" if str(balance) not in {"0", "0.0", "0.00"} else "closed"
    return None


def _accounting_meaning(
    native_type: str, payload: Mapping[str, object]
) -> Mapping[str, object]:
    # Lossless indexes only: values are copied, never inferred or corrected.
    keys = (
        "TxnDate",
        "DueDate",
        "TotalAmt",
        "Balance",
        "PaymentType",
        "AccountType",
        "AccountSubType",
        "CurrentBalance",
        "DocNumber",
        "PaymentRefNum",
        "PrivateNote",
    )
    return {
        "native_type": native_type,
        **{key: payload[key] for key in keys if key in payload},
    }
