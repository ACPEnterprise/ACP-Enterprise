from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt
import pytest

from app.core.config import Settings
from app.platform.auth.access_tokens import AccessTokenService
from app.platform.auth.errors import InvalidTokenError, PasswordPolicyError
from app.platform.auth.passwords import PasswordService
from app.platform.auth.tokens import SecurityTokenService


def build_test_settings(**overrides: object) -> Settings:
    values: dict[str, Any] = {
        "environment": "test",
        "access_token_signing_key": "test-signing-key-with-at-least-32-characters",
        "security_token_hmac_key": "test-hmac-key-with-at-least-32-characters",
        "argon2_time_cost": 1,
        "argon2_memory_cost_kib": 1024,
        "argon2_parallelism": 1,
        "password_min_length": 12,
        "password_max_length": 128,
    }
    values.update(overrides)
    return Settings(**values)


def test_password_hashing_policy_verification_and_upgrade_detection() -> None:
    configuration = build_test_settings()
    service = PasswordService(configuration)
    password = "correct horse battery staple"
    encoded_hash = service.hash_password(password)

    assert encoded_hash.startswith("$argon2id$")
    assert password not in encoded_hash
    assert service.verify_password(encoded_hash, password)
    assert not service.verify_password(encoded_hash, "incorrect password")
    assert not service.needs_rehash(encoded_hash)

    stronger_service = PasswordService(
        build_test_settings(argon2_time_cost=2, argon2_memory_cost_kib=2048)
    )
    assert stronger_service.needs_rehash(encoded_hash)

    for invalid_password in ("", "   ", "too-short"):
        with pytest.raises(PasswordPolicyError):
            service.hash_password(invalid_password)
    with pytest.raises(PasswordPolicyError):
        service.hash_password("x" * 129)


def test_security_tokens_are_random_and_deterministically_hashed() -> None:
    service = SecurityTokenService(build_test_settings())
    first = service.generate_token()
    second = service.generate_token()

    assert first != second
    assert len(first) >= 43
    assert service.hash_token(first) == service.hash_token(first)
    assert service.hash_token(first) != first
    assert service.compare_hash(first, service.hash_token(first))
    assert not service.compare_hash(second, service.hash_token(first))


def test_access_token_validation_rejects_invalid_security_properties() -> None:
    configuration = build_test_settings()
    service = AccessTokenService(configuration)
    user_id = uuid4()
    session_id = uuid4()
    now = datetime.now(timezone.utc)
    token, _ = service.issue(
        user_id=user_id,
        session_id=session_id,
        credential_version=2,
        authorization_version=3,
        now=now,
    )
    claims = service.decode(token)
    assert claims.user_id == user_id
    assert claims.session_id == session_id
    assert claims.credential_version == 2
    assert claims.authorization_version == 3

    expired_token, _ = service.issue(
        user_id=user_id,
        session_id=session_id,
        credential_version=2,
        authorization_version=3,
        now=now - timedelta(hours=1),
    )
    with pytest.raises(InvalidTokenError):
        service.decode(expired_token)

    for alternate in (
        AccessTokenService(build_test_settings(access_token_issuer="wrong-issuer")),
        AccessTokenService(build_test_settings(access_token_audience="wrong-audience")),
        AccessTokenService(
            build_test_settings(
                access_token_signing_key=(
                    "different-test-signing-key-with-32-characters"
                )
            )
        ),
    ):
        alternate_token, _ = alternate.issue(
            user_id=user_id,
            session_id=session_id,
            credential_version=2,
            authorization_version=3,
            now=now,
        )
        with pytest.raises(InvalidTokenError):
            service.decode(alternate_token)

    assert configuration.access_token_signing_key is not None
    disallowed_algorithm_token = jwt.encode(
        {
            "iss": configuration.access_token_issuer,
            "aud": configuration.access_token_audience,
            "sub": str(user_id),
            "sid": str(session_id),
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "jti": str(uuid4()),
            "cv": 2,
            "av": 3,
        },
        configuration.access_token_signing_key + "-extra-key-material-for-hs384",
        algorithm="HS384",
    )
    with pytest.raises(InvalidTokenError):
        service.decode(disallowed_algorithm_token)

    missing_claim_token = jwt.encode(
        {
            "iss": configuration.access_token_issuer,
            "aud": configuration.access_token_audience,
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "jti": str(uuid4()),
            "cv": 2,
            "av": 3,
        },
        configuration.access_token_signing_key,
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        service.decode(missing_claim_token)
