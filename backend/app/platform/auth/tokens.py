import hashlib
import hmac
import secrets

from app.core.config import Settings, settings


class SecurityTokenService:
    def __init__(self, configuration: Settings = settings) -> None:
        self.configuration = configuration
        assert configuration.security_token_hmac_key is not None
        self._hmac_key = configuration.security_token_hmac_key.encode("utf-8")

    def generate_token(self) -> str:
        return secrets.token_urlsafe(self.configuration.security_token_bytes)

    def hash_token(self, token: str) -> str:
        return hmac.new(
            self._hmac_key,
            token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def compare_hash(self, token: str, expected_hash: str) -> bool:
        return hmac.compare_digest(self.hash_token(token), expected_hash)

    def hash_identifier(self, identifier: str) -> str:
        return self.hash_token(f"identity:{identifier}")
