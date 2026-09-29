from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


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


def require_environment_scoped_reference(reference: str, environment: str) -> str:
    normalized = reference.strip()
    prefix = f"marketing/{environment}/"
    if not normalized.startswith(prefix) or "://" in normalized:
        raise ValueError("credential_reference_environment_mismatch")
    return normalized
