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
    assert "respond @internal 404" not in caddy
    for path in (
        "/mission-control*",
        "/engineering*",
        "/mission-assets/*",
        "/api/v1/engineering/*",
        "/api/v1/worker-transport*",
    ):
        assert path in caddy
    assert "app.twelve-hats.com" not in caddy


def test_beta_verifier_covers_tls_health_routes_cors_and_isolation() -> None:
    verifier = (REPOSITORY_ROOT / "scripts/verify-beta-connectivity.sh").read_text(
        encoding="utf-8"
    )

    assert PREVIEW in verifier
    assert BETA in verifier
    assert "/backend-health" in verifier
    assert 'require_status 200 "$base_url/health/live"' in verifier
    assert 'require_status 200 "$base_url/health/ready"' in verifier
    assert '"status":"alive"' in verifier
    assert '"state":"HEALTHY"' in verifier
    assert "/api/v1/auth/session" in verifier
    assert "access-control-allow-origin" in verifier
    assert "openssl s_client" in verifier
    assert 'openssl x509 -in "$certificate_file" -noout -checkend 1209600' in verifier
    assert "Preview and Beta backend health projections differ" in verifier
    assert "https://untrusted.invalid" in verifier
    assert "require_single_header content-security-policy" in verifier
    assert "require_header_value strict-transport-security" in verifier
    assert "require_header_value x-frame-options DENY" in verifier
    assert "require_https_redirect beta.twelve-hats.com" in verifier
    assert "REQUIRE_PUBLIC_METADATA" in verifier
    assert "mission-control" in verifier
    assert "app.twelve-hats.com" not in verifier
    assert "PREVIEW_URL" not in verifier
    assert "BETA_URL" not in verifier


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


def test_frontend_proxies_canonical_liveness_and_readiness_exactly() -> None:
    nginx = (REPOSITORY_ROOT / "frontend/nginx.preview.conf").read_text(
        encoding="utf-8"
    )

    assert "location = /health/live {" in nginx
    assert "proxy_pass http://backend:8000/health/live;" in nginx
    assert "location = /health/ready {" in nginx
    assert "proxy_pass http://backend:8000/health/ready;" in nginx


def test_owner_assets_route_does_not_collide_with_static_asset_directory() -> None:
    nginx = (REPOSITORY_ROOT / "frontend/nginx.preview.conf").read_text(
        encoding="utf-8"
    )

    assert "location = /assets {\n        try_files /index.html =404;\n    }" in nginx
    assert "location = /assets/ {\n        try_files /index.html =404;\n    }" in nginx
