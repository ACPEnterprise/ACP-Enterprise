from pathlib import Path

from app.core.config import Settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def _settings(environment: str) -> Settings:
    return Settings(
        environment=environment,
        access_token_keys={"test": "a" * 32},
        access_token_active_kid="test",
        security_token_hmac_key="b" * 32,
        platform_contract_expected_fingerprint="c" * 64,
        hsts_enabled=True,
        cors_allowed_origins=["https://beta.example.test"],
        allowed_hosts=["beta.example.test"],
    )


def test_api_documentation_is_limited_to_local_and_test_environments() -> None:
    assert _settings("development").api_documentation_enabled is True
    assert _settings("test").api_documentation_enabled is True
    assert _settings("preview").api_documentation_enabled is False
    assert _settings("production").api_documentation_enabled is False


def test_application_binds_all_documentation_surfaces_to_the_guard() -> None:
    source = (REPOSITORY_ROOT / "backend/app/main.py").read_text(encoding="utf-8")

    for option in ("docs_url", "redoc_url", "openapi_url"):
        assert f"{option}=\"/" in source
        assert "if settings.api_documentation_enabled else None" in source
