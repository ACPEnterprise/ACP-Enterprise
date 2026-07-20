from functools import lru_cache
from ipaddress import ip_network
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ACP Enterprise"
    app_version: str = "0.1.0"
    environment: str = "development"
    business_timezone: str = "America/New_York"

    database_url: str = (
        "postgresql+asyncpg://acp_enterprise:"
        "acp_development_password@postgres:5432/acp_enterprise"
    )
    redis_url: str = "redis://redis:6379/0"
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "test", "testserver"]
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    password_min_length: int = 12
    password_max_length: int = 256
    argon2_time_cost: int = 3
    argon2_memory_cost_kib: int = 65536
    argon2_parallelism: int = 4
    argon2_hash_length: int = 32
    argon2_salt_length: int = 16

    access_token_signing_key: str | None = None
    access_token_keys: dict[str, str] = Field(default_factory=dict)
    access_token_active_kid: str = "legacy"
    access_token_algorithm: str = "HS256"
    access_token_issuer: str = "acp-enterprise"
    access_token_audience: str = "acp-enterprise-api"
    access_token_lifetime_seconds: int = 900
    security_token_hmac_key: str | None = None
    security_token_bytes: int = 32

    session_absolute_lifetime_seconds: int = 2592000
    session_idle_lifetime_seconds: int = 604800
    session_last_seen_throttle_seconds: int = 300
    refresh_token_lifetime_seconds: int = 2592000
    password_reset_lifetime_seconds: int = 3600
    email_verification_lifetime_seconds: int = 86400
    credential_lockout_threshold: int = 5
    credential_lockout_duration_seconds: int = 900

    trusted_proxy_cidrs: list[str] = Field(default_factory=list)
    trust_forwarded_headers: bool = False
    security_headers_enabled: bool = True
    hsts_enabled: bool = False
    hsts_max_age_seconds: int = 31536000
    hsts_include_subdomains: bool = True
    hsts_preload: bool = False
    content_security_policy: str = "default-src 'self'; frame-ancestors 'none'"
    permissions_policy: str = "camera=(), microphone=(), geolocation=()"
    referrer_policy: str = "strict-origin-when-cross-origin"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_security_configuration(self) -> "Settings":
        if self.environment == "test":
            self.access_token_signing_key = (
                self.access_token_signing_key or "test-signing-key-not-for-production"
            )
            self.security_token_hmac_key = (
                self.security_token_hmac_key or "test-hmac-key-not-for-production"
            )

        if not self.access_token_keys and self.access_token_signing_key:
            self.access_token_keys = {
                self.access_token_active_kid: self.access_token_signing_key
            }

        if (
            self.access_token_signing_key is not None
            and len(self.access_token_signing_key) < 32
        ):
            raise ValueError(
                "ACCESS_TOKEN_SIGNING_KEY must contain at least 32 characters"
            )
        if not self.access_token_keys:
            raise ValueError("At least one access-token signing key is required")
        if not self.security_token_hmac_key or len(self.security_token_hmac_key) < 32:
            raise ValueError(
                "SECURITY_TOKEN_HMAC_KEY must contain at least 32 characters"
            )
        if self.access_token_algorithm not in {"HS256", "HS384", "HS512"}:
            raise ValueError("ACCESS_TOKEN_ALGORITHM is not permitted")
        if self.access_token_active_kid not in self.access_token_keys:
            raise ValueError("ACCESS_TOKEN_ACTIVE_KID must identify a configured key")
        if any(
            not kid.strip() or len(key) < 32
            for kid, key in self.access_token_keys.items()
        ):
            raise ValueError(
                "Every access-token key needs a nonblank kid and 32 characters"
            )
        if not 8 <= self.password_min_length <= self.password_max_length <= 1024:
            raise ValueError("Password length configuration is invalid")
        if self.security_token_bytes < 32:
            raise ValueError("SECURITY_TOKEN_BYTES must be at least 32")
        if self.trust_forwarded_headers and not self.trusted_proxy_cidrs:
            raise ValueError("Trusted proxy CIDRs are required for forwarded headers")
        try:
            for cidr in self.trusted_proxy_cidrs:
                ip_network(cidr, strict=False)
        except ValueError as error:
            raise ValueError(
                "TRUSTED_PROXY_CIDRS contains an invalid network"
            ) from error
        if self.hsts_max_age_seconds < 0:
            raise ValueError("HSTS_MAX_AGE_SECONDS cannot be negative")
        if self.environment in {"preview", "production"}:
            insecure_markers = (
                "development",
                "not-for-production",
                "change-before-use",
                "replace",
            )
            secrets = [*self.access_token_keys.values(), self.security_token_hmac_key]
            if any(
                secret is None
                or any(marker in secret.lower() for marker in insecure_markers)
                for secret in secrets
            ):
                raise ValueError("Production security secrets are insecure")
            if not self.security_headers_enabled or not self.hsts_enabled:
                raise ValueError(
                    "Secure environments require security headers and HSTS"
                )
            if not self.cors_allowed_origins or any(
                origin == "*" or not origin.startswith("https://")
                for origin in self.cors_allowed_origins
            ):
                raise ValueError(
                    "Secure environments require explicit HTTPS CORS origins"
                )
            if not self.allowed_hosts or "*" in self.allowed_hosts:
                raise ValueError(
                    "Secure environments require explicit trusted host names"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
