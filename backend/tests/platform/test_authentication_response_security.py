import pytest
from app.platform.auth.router import development_token


@pytest.mark.parametrize("environment", ["preview", "production"])
def test_deployed_environments_never_return_plaintext_recovery_tokens(
    environment: str,
) -> None:
    assert development_token("provider-secret-token", environment=environment) is None


@pytest.mark.parametrize("environment", ["development", "test"])
def test_non_deployed_environments_can_return_test_recovery_tokens(
    environment: str,
) -> None:
    assert (
        development_token("provider-secret-token", environment=environment)
        == "provider-secret-token"
    )


def test_missing_recovery_token_remains_absent() -> None:
    assert development_token(None, environment="test") is None
