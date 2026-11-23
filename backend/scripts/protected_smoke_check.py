"""Run one authenticated, read-only Preview smoke check.

The short-lived credential is read only from its protected runtime mount. The
tool never accepts a token on the command line or emits secret material.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import urllib.error
import urllib.request
from pathlib import Path


class SmokeBlocked(RuntimeError):
    """A safe protected-smoke prerequisite failure."""


def secret(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise SmokeBlocked("approved smoke credential file is unavailable")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise SmokeBlocked("approved smoke credential file permissions are unsafe")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise SmokeBlocked("approved smoke credential is empty")
    return value


def request(
    path: str,
    token: str | None = None,
    *,
    company_id: str | None = None,
) -> tuple[int, bytes]:
    base_url = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    headers = {"Accept": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if company_id is not None:
        headers["X-Company-ID"] = company_id
    request_obj = urllib.request.Request(
        f"{base_url}/{path.lstrip('/')}", headers=headers
    )
    try:
        with urllib.request.urlopen(request_obj, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except (OSError, urllib.error.URLError) as exc:
        raise SmokeBlocked("protected smoke endpoint is unavailable") from exc


def check_authentication(path: str, credential_file: Path) -> dict[str, str]:
    anonymous_status, _ = request(path)
    if anonymous_status not in {401, 403}:
        raise SmokeBlocked("anonymous protected request was not rejected")
    authorized_status, _ = request(path, secret(credential_file))
    if authorized_status != 200:
        raise SmokeBlocked("authorized smoke principal was not accepted")
    return {"check": "authentication", "status": "PASS"}


def check_authorization(path: str, credential_file: Path) -> dict[str, str]:
    status, _ = request(path, secret(credential_file))
    if status not in {401, 403, 404}:
        raise SmokeBlocked("least-privilege smoke principal was not denied")
    return {"check": "authorization", "status": "PASS"}


def check_tenant_isolation(path: str, credential_file: Path) -> dict[str, str]:
    denied_company = os.environ.get("SMOKE_DENIED_COMPANY_ID")
    if not denied_company:
        raise SmokeBlocked("denied tenant binding is unavailable")
    status, _ = request(
        path,
        secret(credential_file),
        company_id=denied_company,
    )
    if status not in {401, 403, 404}:
        raise SmokeBlocked("cross-tenant request was not denied")
    return {"check": "tenant-isolation", "status": "PASS"}


def check_routes(paths: tuple[str, ...], credential_file: Path) -> dict[str, str]:
    token = secret(credential_file)
    for path in paths:
        status, _ = request(path, token)
        if status >= 400:
            raise SmokeBlocked("protected route smoke failed")
    return {"check": "routes", "status": "PASS", "route_count": str(len(paths))}


def check_background(path: str, credential_file: Path) -> dict[str, str]:
    status, body = request(path, secret(credential_file))
    if status != 200:
        raise SmokeBlocked("background-service health endpoint failed")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SmokeBlocked("background-service health evidence is invalid") from exc
    if payload.get("status") != "healthy":
        raise SmokeBlocked("background-service heartbeat is not healthy")
    return {"check": "background-services", "status": "PASS"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        choices=(
            "authentication",
            "authorization",
            "tenant-isolation",
            "routes",
            "background-services",
        ),
        required=True,
    )
    parser.add_argument("--path")
    parser.add_argument("--credential-file", type=Path, required=True)
    parser.add_argument("--route", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.check == "authentication":
            result = check_authentication(
                args.path or "/api/v1/auth/session", args.credential_file
            )
        elif args.check == "authorization":
            result = check_authorization(
                args.path or "/api/v1/authorization/launch-role-matrix",
                args.credential_file,
            )
        elif args.check == "tenant-isolation":
            result = check_tenant_isolation(
                args.path or "/api/v1/workforce/employees", args.credential_file
            )
        elif args.check == "routes":
            if not args.route:
                raise SmokeBlocked("protected route list is required")
            result = check_routes(tuple(args.route), args.credential_file)
        else:
            result = check_background(args.path or "/health", args.credential_file)
    except SmokeBlocked as exc:
        print(f"BLOCKED: {exc}")
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
