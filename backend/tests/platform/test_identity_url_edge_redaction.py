from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_both_public_hosts_suppress_identity_secret_urls_and_referrers() -> None:
    caddy = (
        REPOSITORY_ROOT / "docs/deployment/mission-control-preview.caddy"
    ).read_text(encoding="utf-8")

    assert caddy.count("@identity_secret_page path /activate /reset-password") == 2
    assert caddy.count("log_skip @identity_secret_page") == 2
    assert (
        caddy.count('header @identity_secret_page >Referrer-Policy "no-referrer"') == 2
    )
    assert 'header @identity_secret_page Referrer-Policy "no-referrer"' not in caddy


def test_frontend_container_does_not_log_identity_secret_urls() -> None:
    nginx = (REPOSITORY_ROOT / "frontend/nginx.preview.conf").read_text(
        encoding="utf-8"
    )

    for route in ("/activate", "/reset-password"):
        location = nginx.split(f"location = {route} {{", 1)[1].split("}", 1)[0]
        assert "access_log off;" in location
        assert "try_files /index.html =404;" in location
