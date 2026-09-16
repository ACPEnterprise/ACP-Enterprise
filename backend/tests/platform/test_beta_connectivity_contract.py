from pathlib import Path

import yaml  # type: ignore[import-untyped]

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PREVIEW = "https://preview.allcountyhomeservices.com"
BETA = "https://beta.twelve-hats.com"


def test_preview_runtime_accepts_both_exact_beta_origins_and_hosts() -> None:
    compose = yaml.safe_load(
        (REPOSITORY_ROOT / "docker-compose.preview.yml").read_text(encoding="utf-8")
    )
    environment = compose["x-backend-environment"]

    assert environment["CORS_ALLOWED_ORIGINS"] == (
        '${CORS_ALLOWED_ORIGINS:-["https://preview.allcountyhomeservices.com",'
        '"https://beta.twelve-hats.com"]}'
    )
    assert environment["ALLOWED_HOSTS"] == (
        '${ALLOWED_HOSTS:-["preview.allcountyhomeservices.com",'
        '"beta.twelve-hats.com","backend","localhost","127.0.0.1"]}'
    )
    assert environment["IDENTITY_EMAIL_ACTIVATION_ORIGIN"] == PREVIEW
    assert environment["QBO_SANDBOX_CALLBACK_URI"].startswith(f"{PREVIEW}/")
    assert environment["QBO_PRODUCTION_CALLBACK_URI"].startswith(f"{PREVIEW}/")


def test_beta_edge_preserves_preview_and_blocks_internal_surfaces() -> None:
    caddy = (
        REPOSITORY_ROOT / "docs/deployment/mission-control-preview.caddy"
    ).read_text(encoding="utf-8")

    assert "preview.allcountyhomeservices.com {" in caddy
    assert "beta.twelve-hats.com {" in caddy
    assert "handle @internal {" in caddy
    assert "respond 404" in caddy
    for path in (
        "/mission-control*",
        "/engineering*",
        "/mission-assets/*",
        "/api/v1/engineering/*",
        "/api/v1/worker-transport*",
    ):
        assert path in caddy
    assert "app.twelve-hats.com" not in caddy
    assert caddy.count("@browser_secret_path path /activate /reset-password") == 2
    assert caddy.count("log_skip @browser_secret_path") == 2


def test_beta_verifier_covers_tls_health_routes_cors_and_isolation() -> None:
    verifier = (REPOSITORY_ROOT / "scripts/verify-beta-connectivity.sh").read_text(
        encoding="utf-8"
    )

    assert PREVIEW in verifier
    assert BETA in verifier
    assert "/backend-health" in verifier
    assert "/api/v1/auth/session" in verifier
    assert "access-control-allow-origin" in verifier
    assert "https://attacker.invalid" in verifier
    assert "openssl s_client" in verifier
    assert "-checkend 604800" in verifier
    assert "mission-control" in verifier
    assert "app.twelve-hats.com" not in verifier
    assert "PREVIEW_URL" not in verifier
    assert "BETA_URL" not in verifier
    for header in (
        "strict-transport-security",
        "x-content-type-options",
        "x-frame-options",
        "referrer-policy",
        "permissions-policy",
        "content-security-policy",
    ):
        assert header in verifier


def test_local_monitor_is_bounded_and_does_not_claim_external_alerting() -> None:
    service = (
        REPOSITORY_ROOT
        / "docs/deployment/twelve-hats-beta-connectivity-monitor.service.example"
    ).read_text(encoding="utf-8")
    timer = (
        REPOSITORY_ROOT
        / "docs/deployment/twelve-hats-beta-connectivity-monitor.timer.example"
    ).read_text(encoding="utf-8")

    assert "verify-beta-connectivity.sh" in service
    assert "NoNewPrivileges=true" in service
    assert "ProtectSystem=strict" in service
    assert "OnUnitActiveSec=5min" in timer
    assert "Persistent=true" in timer


def test_frontend_proxy_emits_one_security_header_policy() -> None:
    nginx = (REPOSITORY_ROOT / "frontend/nginx.preview.conf").read_text(
        encoding="utf-8"
    )

    for header in (
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Content-Security-Policy",
        "Permissions-Policy",
        "Strict-Transport-Security",
    ):
        assert f"proxy_hide_header {header};" in nginx


def test_frontend_proxy_does_not_log_browser_borne_credentials() -> None:
    nginx = (REPOSITORY_ROOT / "frontend/nginx.preview.conf").read_text(
        encoding="utf-8"
    )

    for route in ("/activate", "/reset-password"):
        location = nginx.split(f"location = {route} {{", 1)[1].split("}", 1)[0]
        assert "access_log off;" in location
        assert "try_files $uri /index.html;" in location
