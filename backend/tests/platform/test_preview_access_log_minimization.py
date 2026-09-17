from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_preview_edge_access_log_excludes_queries_referrers_and_user_agents() -> None:
    nginx = (REPOSITORY_ROOT / "frontend/nginx.preview.conf").read_text(
        encoding="utf-8"
    )
    log_format = nginx.split("log_format acp_safe", 1)[1].split("server {", 1)[0]

    assert '"path":"$uri"' in log_format
    assert '"request_id":"$request_id"' in log_format
    assert '"status":$status' in log_format
    assert '"request_time":$request_time' in log_format
    assert "$args" not in log_format
    assert "$request_uri" not in log_format
    assert '"$request"' not in log_format
    assert "$http_referer" not in log_format
    assert "$http_user_agent" not in log_format
    assert "access_log /var/log/nginx/access.log acp_safe;" in nginx
    assert nginx.count("location = /activate {") == 1
    assert nginx.count("location = /reset-password {") == 1


def test_backend_does_not_duplicate_query_bearing_uvicorn_access_log() -> None:
    dockerfile = (REPOSITORY_ROOT / "backend/Dockerfile.preview").read_text(
        encoding="utf-8"
    )

    assert '"--no-access-log"' in dockerfile
    assert '"--no-proxy-headers"' in dockerfile
