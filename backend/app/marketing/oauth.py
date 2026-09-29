from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import stat
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from uuid import UUID

import httpx

from app.core.config import Settings, get_settings
from app.platform.secrets import ProtectedSecretProvider, SecretProviderError

from .google_ads import GOOGLE_ADS_SCOPE

AUTHORIZE_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


class GoogleAdsOAuthError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class PendingGoogleAuthorization:
    state: str
    nonce_digest: str
    company_id: UUID
    user_id: UUID
    session_id: UUID
    environment: str
    redirect_uri: str
    token_reference: str
    expires_at: datetime


class ProtectedGoogleAuthorizationStore:
    """Single-use protected state. The browser receives only state and nonce."""

    def __init__(self, *, root: Path, repository_root: Path) -> None:
        self.root = root.expanduser().resolve()
        repository = repository_root.expanduser().resolve()
        if self.root == repository or repository in self.root.parents:
            raise GoogleAdsOAuthError("oauth_state_inside_repository")
        if self.root.exists() and stat.S_IMODE(self.root.stat().st_mode) & 0o077:
            raise GoogleAdsOAuthError("oauth_state_permissions_invalid")
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(self.root, 0o700)

    def put(self, pending: PendingGoogleAuthorization) -> None:
        path = self._path(pending.state)
        document = {
            **asdict(pending),
            "company_id": str(pending.company_id),
            "user_id": str(pending.user_id),
            "session_id": str(pending.session_id),
            "expires_at": pending.expires_at.isoformat(),
        }
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(document, stream, sort_keys=True, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())

    def consume(self, state: str) -> PendingGoogleAuthorization:
        path = self._path(state)
        claimed = path.with_suffix(".claimed")
        try:
            os.replace(path, claimed)
        except FileNotFoundError as error:
            raise GoogleAdsOAuthError("oauth_state_replayed") from error
        try:
            document = json.loads(claimed.read_bytes())
            pending = PendingGoogleAuthorization(
                state=str(document["state"]),
                nonce_digest=str(document["nonce_digest"]),
                company_id=UUID(str(document["company_id"])),
                user_id=UUID(str(document["user_id"])),
                session_id=UUID(str(document["session_id"])),
                environment=str(document["environment"]),
                redirect_uri=str(document["redirect_uri"]),
                token_reference=str(document["token_reference"]),
                expires_at=datetime.fromisoformat(str(document["expires_at"])),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise GoogleAdsOAuthError("oauth_state_invalid") from error
        finally:
            claimed.unlink(missing_ok=True)
        return pending

    def _path(self, state: str) -> Path:
        if len(state) < 32:
            raise GoogleAdsOAuthError("oauth_state_invalid")
        return self.root / f"{hashlib.sha256(state.encode()).hexdigest()}.json"


class GoogleAdsOAuthRuntime:
    def __init__(
        self,
        *,
        environment: str,
        redirect_uri: str,
        client_reference: str,
        developer_reference: str,
        secrets_provider: ProtectedSecretProvider,
        states: ProtectedGoogleAuthorizationStore,
        state_signing_key: bytes,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.environment = environment
        self.redirect_uri = redirect_uri
        self.client_reference = client_reference
        self.developer_reference = developer_reference
        self.secrets = secrets_provider
        self.states = states
        self.client = client or httpx.AsyncClient(timeout=30, follow_redirects=False)
        if len(state_signing_key) < 32:
            raise GoogleAdsOAuthError("oauth_state_signing_key_invalid")
        self.state_signing_key = state_signing_key

    def ready(self) -> bool:
        return self.secrets.configured(
            self.client_reference
        ) and self.secrets.configured(self.developer_reference)

    def begin(
        self, *, company_id: UUID, user_id: UUID, session_id: UUID
    ) -> tuple[str, str]:
        client = self.secrets.read(self.client_reference)
        client_id = client.values.get("client_id")
        if not client_id or not client.values.get("client_secret"):
            raise SecretProviderError("oauth_client_invalid")
        state_value, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        signature = hmac.new(
            self.state_signing_key, state_value.encode(), hashlib.sha256
        ).hexdigest()
        state = f"{state_value}.{signature}"
        token_reference = (
            f"marketing/{self.environment}/google-ads/company/{company_id}/token"
        )
        self.states.put(
            PendingGoogleAuthorization(
                state=state,
                nonce_digest=hashlib.sha256(nonce.encode()).hexdigest(),
                company_id=company_id,
                user_id=user_id,
                session_id=session_id,
                environment=self.environment,
                redirect_uri=self.redirect_uri,
                token_reference=token_reference,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            )
        )
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": GOOGLE_ADS_SCOPE,
                "access_type": "offline",
                "prompt": "consent",
                "state": state,
            }
        )
        return f"{AUTHORIZE_ENDPOINT}?{query}", nonce

    async def complete(
        self, *, code: str, state: str, nonce: str
    ) -> tuple[PendingGoogleAuthorization, int, datetime]:
        try:
            state_value, supplied_signature = state.rsplit(".", 1)
        except ValueError as error:
            raise GoogleAdsOAuthError("oauth_state_invalid") from error
        expected_signature = hmac.new(
            self.state_signing_key, state_value.encode(), hashlib.sha256
        ).hexdigest()
        if not secrets.compare_digest(supplied_signature, expected_signature):
            raise GoogleAdsOAuthError("oauth_state_invalid")
        pending = self.states.consume(state)
        now = datetime.now(timezone.utc)
        if pending.expires_at <= now:
            raise GoogleAdsOAuthError("oauth_state_expired")
        if (
            pending.environment != self.environment
            or pending.redirect_uri != self.redirect_uri
        ):
            raise GoogleAdsOAuthError("oauth_environment_mismatch")
        if not secrets.compare_digest(
            pending.nonce_digest, hashlib.sha256(nonce.encode()).hexdigest()
        ):
            raise GoogleAdsOAuthError("oauth_session_mismatch")
        client = self.secrets.read(self.client_reference)
        response = await self.client.post(
            TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": client.values["client_id"],
                "client_secret": client.values["client_secret"],
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if response.status_code != 200:
            raise GoogleAdsOAuthError("oauth_token_exchange_failed")
        payload = response.json()
        access_token, refresh_token = (
            payload.get("access_token"),
            payload.get("refresh_token"),
        )
        expires_in = payload.get("expires_in")
        if (
            not isinstance(access_token, str)
            or not isinstance(refresh_token, str)
            or not isinstance(expires_in, int)
        ):
            raise GoogleAdsOAuthError("oauth_token_response_invalid")
        scope = str(payload.get("scope", GOOGLE_ADS_SCOPE))
        if GOOGLE_ADS_SCOPE not in scope.split():
            raise GoogleAdsOAuthError("oauth_scope_invalid")
        expires_at = now + timedelta(seconds=expires_in)
        try:
            expected_generation = self.secrets.read(pending.token_reference).generation
        except SecretProviderError as error:
            if error.code != "secret_unavailable":
                raise
            expected_generation = None
        material = self.secrets.write(
            pending.token_reference,
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "scope": scope,
                "expires_at": expires_at.isoformat(),
            },
            expected_generation=expected_generation,
        )
        return pending, material.generation, expires_at


def build_google_ads_oauth_runtime(
    configuration: Settings | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> GoogleAdsOAuthRuntime:
    configuration = configuration or get_settings()
    if (
        not configuration.google_ads_live_access_enabled
        or configuration.environment != "beta"
        or not configuration.google_ads_runtime_root
        or not configuration.google_ads_callback_uri
        or not configuration.google_ads_oauth_client_reference
        or not configuration.google_ads_developer_token_reference
    ):
        raise GoogleAdsOAuthError("google_ads_oauth_runtime_disabled")
    root = Path(configuration.google_ads_runtime_root).expanduser().resolve()
    repository = Path(configuration.qbo_repository_root).expanduser().resolve()
    provider = ProtectedSecretProvider(
        root=root / "secrets",
        repository_root=repository,
        environment=configuration.environment,
    )
    states = ProtectedGoogleAuthorizationStore(
        root=root / "oauth-state", repository_root=repository
    )
    signing_key = configuration.security_token_hmac_key
    if signing_key is None:
        raise GoogleAdsOAuthError("google_ads_oauth_signing_key_unavailable")
    return GoogleAdsOAuthRuntime(
        environment=configuration.environment,
        redirect_uri=configuration.google_ads_callback_uri,
        client_reference=configuration.google_ads_oauth_client_reference,
        developer_reference=configuration.google_ads_developer_token_reference,
        secrets_provider=provider,
        states=states,
        state_signing_key=signing_key.encode(),
        client=client,
    )
