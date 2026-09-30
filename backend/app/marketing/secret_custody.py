from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.platform.secrets import ProtectedSecretProvider, SecretProviderError


@dataclass(frozen=True, slots=True)
class GoogleAdsCredentialEnvelope:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    developer_token: str = field(repr=False)
    expires_at: datetime
    generation: int


class GoogleAdsSecretProvider(Protocol):
    """Secret-manager boundary; implementations never expose material to APIs."""

    async def get_google_ads_credentials(
        self, *, client_reference: str, token_reference: str, environment: str
    ) -> GoogleAdsCredentialEnvelope: ...


class ProtectedGoogleAdsSecretProvider:
    """Adapts Platform custody to the narrow Google Ads credential port."""

    def __init__(
        self,
        provider: ProtectedSecretProvider,
        *,
        developer_token_reference: str,
    ) -> None:
        self.provider = provider
        self.developer_token_reference = developer_token_reference

    async def get_google_ads_credentials(
        self, *, client_reference: str, token_reference: str, environment: str
    ) -> GoogleAdsCredentialEnvelope:
        del client_reference, environment
        token = self.provider.read(token_reference)
        developer = self.provider.read(self.developer_token_reference)
        try:
            return GoogleAdsCredentialEnvelope(
                access_token=token.values["access_token"],
                refresh_token=token.values["refresh_token"],
                developer_token=developer.values["developer_token"],
                expires_at=datetime.fromisoformat(token.values["expires_at"]),
                generation=token.generation,
            )
        except (KeyError, ValueError) as error:
            raise SecretProviderError("google_ads_secret_material_invalid") from error


def require_environment_scoped_reference(reference: str, environment: str) -> str:
    normalized = reference.strip()
    prefix = f"marketing/{environment}/"
    if not normalized.startswith(prefix) or "://" in normalized:
        raise ValueError("credential_reference_environment_mismatch")
    return normalized
