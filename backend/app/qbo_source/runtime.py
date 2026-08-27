from __future__ import annotations

import json
import os
import secrets
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from app.core.config import Settings, settings

from .callback import (
    OAuthCallbackHandler,
    ProtectedAuthorizationStateStore,
    exact_callback_uri,
)
from .intuit import (
    AuthorizedRealm,
    HttpTransport,
    IntuitAuthenticationError,
    IntuitEnvironment,
    IntuitHttpTransport,
    IntuitOAuthClient,
    OAuthAuthorizationCoordinator,
)
from .secrets import ProtectedSandboxSecretProvider, SandboxSecretStoreError


class SandboxRuntimeError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ProtectedSandboxCompanyBinding:
    """Exact expected CompanyInfo name from protected sandbox configuration."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(self.root, 0o700)

    @property
    def path(self) -> Path:
        return self.root / "expected-company-name"

    def read(self) -> str:
        try:
            if stat.S_IMODE(self.path.stat().st_mode) != 0o600:
                raise SandboxRuntimeError("sandbox_company_binding_permissions_invalid")
            value = self.path.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise SandboxRuntimeError("sandbox_company_not_configured") from error
        except UnicodeDecodeError as error:
            raise SandboxRuntimeError("sandbox_company_binding_invalid") from error
        if not value or "\x00" in value or "\r" in value or "\n" in value:
            raise SandboxRuntimeError("sandbox_company_binding_invalid")
        return value


class SandboxCompanyInfoVerifier:
    def __init__(
        self,
        *,
        transport: HttpTransport,
        secrets_provider: ProtectedSandboxSecretProvider,
        expected_company_name: str,
        token_reference: str,
        minor_version: int,
        registry: SandboxConnectionRegistry,
    ) -> None:
        self.transport = transport
        self.secrets_provider = secrets_provider
        self.expected_company_name = expected_company_name
        self.token_reference = token_reference
        self.minor_version = minor_version
        self.registry = registry

    async def verify(self, authorized: AuthorizedRealm) -> None:
        url = (
            "https://sandbox-quickbooks.api.intuit.com/v3/company/"
            f"{authorized.realm_id}/companyinfo/{authorized.realm_id}"
            f"?minorversion={self.minor_version}"
        )
        try:
            response = await self.transport.request(
                method="GET",
                url=url,
                headers={
                    "Authorization": f"Bearer {authorized.token.access_token}",
                    "Accept": "application/json",
                },
                body=None,
            )
            if response.status != 200:
                raise IntuitAuthenticationError("company_info_verification_failed")
            company = response.json().get("CompanyInfo")
            if not isinstance(company, dict):
                raise IntuitAuthenticationError("company_info_verification_failed")
            if company.get("Id") != authorized.realm_id:
                raise IntuitAuthenticationError("company_realm_mismatch")
            if company.get("CompanyName") != self.expected_company_name:
                raise IntuitAuthenticationError("company_identity_mismatch")
            self.registry.record_verified(
                realm_id=authorized.realm_id,
                company_name=self.expected_company_name,
                minor_version=self.minor_version,
            )
        except Exception:
            await self.secrets_provider.delete_token(self.token_reference)
            raise


class SandboxConnectionRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(self.root, 0o700)

    def record_verified(
        self, *, realm_id: str, company_name: str, minor_version: int
    ) -> None:
        document = {
            "schema_version": "qbo-sandbox-connection/v1",
            "environment": "sandbox",
            "realm_id": realm_id,
            "company_name": company_name,
            "api_minor_version": minor_version,
            "company_info_verified_at": datetime.now(timezone.utc).isoformat(),
            "acquisition_eligible": True,
        }
        path = self.root / "verified.json"
        temporary = path.with_suffix(".tmp")
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
        )
        try:
            with os.fdopen(descriptor, "wb") as target:
                target.write(
                    json.dumps(
                        document,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                )
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        finally:
            temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class SandboxOAuthRuntime:
    callback: OAuthCallbackHandler
    verifier: SandboxCompanyInfoVerifier
    coordinator: OAuthAuthorizationCoordinator

    async def begin(self, *, redirect_uri: str) -> str:
        return await self.coordinator.begin(
            redirect_uri=redirect_uri,
            token_reference=ProtectedSandboxSecretProvider.TOKEN_REFERENCE,
        )

    async def complete(
        self,
        *,
        code: str | None,
        state: str | None,
        realm_id: str | None,
        provider_error: str | None,
    ) -> None:
        authorized = await self.callback.handle(
            code=code,
            state=state,
            realm_id=realm_id,
            provider_error=provider_error,
        )
        await self.verifier.verify(authorized)


def initialize_sandbox_runtime_storage(configuration: Settings = settings) -> None:
    if not configuration.qbo_sandbox_enabled:
        return
    root = _runtime_root(configuration)
    repository = Path(configuration.qbo_repository_root).resolve()
    ProtectedSandboxSecretProvider(
        root=root / "secrets", repository_root=repository
    )
    ProtectedAuthorizationStateStore(
        root / "oauth-state", repository_root=repository
    )
    ProtectedSandboxCompanyBinding(root / "configuration")
    SandboxConnectionRegistry(root / "connections")


@lru_cache
def get_sandbox_oauth_runtime() -> SandboxOAuthRuntime:
    configuration = settings
    if not configuration.qbo_sandbox_enabled:
        raise SandboxRuntimeError("sandbox_oauth_runtime_disabled")
    expected_uri = exact_callback_uri("https://preview.allcountyhomeservices.com")
    if configuration.qbo_sandbox_callback_uri != expected_uri:
        raise SandboxRuntimeError("sandbox_callback_uri_mismatch")
    root = _runtime_root(configuration)
    repository = Path(configuration.qbo_repository_root).resolve()
    provider = ProtectedSandboxSecretProvider(
        root=root / "secrets", repository_root=repository
    )
    state_store = ProtectedAuthorizationStateStore(
        root / "oauth-state", repository_root=repository
    )
    expected_company_name = ProtectedSandboxCompanyBinding(
        root / "configuration"
    ).read()
    transport = IntuitHttpTransport()
    oauth = IntuitOAuthClient(
        environment=IntuitEnvironment.SANDBOX,
        transport=transport,
        secrets=provider,
        credential_reference=ProtectedSandboxSecretProvider.CLIENT_REFERENCE,
    )
    coordinator = OAuthAuthorizationCoordinator(
        oauth=oauth,
        states=state_store,
        state_factory=lambda: secrets.token_urlsafe(32),
    )
    verifier = SandboxCompanyInfoVerifier(
        transport=transport,
        secrets_provider=provider,
        expected_company_name=expected_company_name,
        token_reference=ProtectedSandboxSecretProvider.TOKEN_REFERENCE,
        minor_version=configuration.qbo_sandbox_api_minor_version,
        registry=SandboxConnectionRegistry(root / "connections"),
    )
    return SandboxOAuthRuntime(
        callback=OAuthCallbackHandler(coordinator),
        verifier=verifier,
        coordinator=coordinator,
    )


def _runtime_root(configuration: Settings) -> Path:
    if not configuration.qbo_sandbox_runtime_root:
        raise SandboxRuntimeError("sandbox_runtime_root_not_configured")
    root = Path(configuration.qbo_sandbox_runtime_root).expanduser().resolve()
    if not root.is_absolute():
        raise SandboxRuntimeError("sandbox_runtime_root_invalid")
    if root.exists() and stat.S_IMODE(root.stat().st_mode) & 0o077:
        raise SandboxSecretStoreError("sandbox_runtime_root_permissions_too_open")
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    os.chmod(root, 0o700)
    return root
