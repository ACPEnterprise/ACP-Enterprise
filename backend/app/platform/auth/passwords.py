from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from argon2.low_level import Type

from app.core.config import Settings, settings
from app.platform.auth.errors import PasswordPolicyError


class PasswordService:
    def __init__(self, configuration: Settings = settings) -> None:
        self.configuration = configuration
        self.hasher = PasswordHasher(
            time_cost=configuration.argon2_time_cost,
            memory_cost=configuration.argon2_memory_cost_kib,
            parallelism=configuration.argon2_parallelism,
            hash_len=configuration.argon2_hash_length,
            salt_len=configuration.argon2_salt_length,
            type=Type.ID,
        )
        self._dummy_hash = self.hasher.hash("not-a-user-password-timing-sentinel")

    def validate_policy(self, password: str) -> None:
        length = len(password)
        if not password.strip():
            raise PasswordPolicyError("Password cannot be blank or whitespace-only.")
        if length < self.configuration.password_min_length:
            raise PasswordPolicyError(
                f"Password must contain at least "
                f"{self.configuration.password_min_length} characters."
            )
        if length > self.configuration.password_max_length:
            raise PasswordPolicyError(
                f"Password cannot exceed "
                f"{self.configuration.password_max_length} characters."
            )

    def hash_password(self, password: str) -> str:
        self.validate_policy(password)
        return self.hasher.hash(password)

    def verify_password(self, encoded_hash: str, password: str) -> bool:
        try:
            return self.hasher.verify(encoded_hash, password)
        except (VerifyMismatchError, InvalidHashError):
            return False

    def needs_rehash(self, encoded_hash: str) -> bool:
        try:
            return self.hasher.check_needs_rehash(encoded_hash)
        except InvalidHashError:
            return True

    def perform_dummy_verification(self, password: str) -> None:
        self.verify_password(self._dummy_hash, password)
