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
    branch_id: str | None = None,
) -> tuple[int, bytes]:
    base_url = os.environ.get("SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    headers = {"Accept": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if company_id is not None:
        headers["X-Company-ID"] = company_id
    if branch_id is not None:
        headers["X-Branch-ID"] = branch_id
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


def tenant_binding() -> tuple[str, str]:
    company_id = os.environ.get("SMOKE_COMPANY_ID")
    branch_id = os.environ.get("SMOKE_BRANCH_ID")
    if not company_id or not branch_id:
        raise SmokeBlocked(
            "authorized smoke tenant and branch bindings are unavailable"
        )
    return company_id, branch_id


def check_authentication(path: str, credential_file: Path) -> dict[str, str]:
    anonymous_status, _ = request(path)
    if anonymous_status not in {401, 403}:
        raise SmokeBlocked("anonymous protected request was not rejected")
    token = secret(credential_file)
    if path == "/api/v1/authorization/companies":
        authorized_status, _ = request(path, token)
    else:
        company_id, branch_id = tenant_binding()
        authorized_status, _ = request(
            path, token, company_id=company_id, branch_id=branch_id
        )
    if authorized_status != 200:
        raise SmokeBlocked("authorized smoke principal was not accepted")
    return {"check": "authentication", "status": "PASS"}


def check_authorization(path: str, credential_file: Path) -> dict[str, str]:
    token = secret(credential_file)
    company_id, branch_id = tenant_binding()
    authorized_status, _ = request(
        path, token, company_id=company_id, branch_id=branch_id
    )
    if authorized_status != 200:
        raise SmokeBlocked("authorized request did not establish the real resource")
    denied_company = os.environ.get("SMOKE_DENIED_COMPANY_ID")
    if not denied_company:
        raise SmokeBlocked("denied tenant binding is unavailable")
    denied_status, _ = request(
        path,
        token,
        company_id=denied_company,
        branch_id=os.environ.get("SMOKE_DENIED_BRANCH_ID"),
    )
    if denied_status not in {401, 403}:
        raise SmokeBlocked("unauthorized request to the real resource was not denied")
    return {"check": "authorization", "status": "PASS"}


def check_tenant_isolation(path: str, credential_file: Path) -> dict[str, str]:
    token = secret(credential_file)
    denied_company = os.environ.get("SMOKE_DENIED_COMPANY_ID")
    if not denied_company:
        raise SmokeBlocked("denied tenant binding is unavailable")
    company_id, branch_id = tenant_binding()
    authorized_status, _ = request(
        path,
        token,
        company_id=company_id,
        branch_id=branch_id,
    )
    if authorized_status != 200:
        raise SmokeBlocked(
            "authorized tenant request did not establish the real resource"
        )
    status, _ = request(
        path,
        token,
        company_id=denied_company,
        branch_id=os.environ.get("SMOKE_DENIED_BRANCH_ID"),
    )
    if status not in {401, 403}:
        raise SmokeBlocked("cross-tenant request was not denied")
    return {"check": "tenant-isolation", "status": "PASS"}


def check_routes(paths: tuple[str, ...], credential_file: Path) -> dict[str, str]:
    token = secret(credential_file)
    company_id = os.environ.get("SMOKE_COMPANY_ID")
    branch_id = os.environ.get("SMOKE_BRANCH_ID")
    for path in paths:
        status, _ = request(
            path,
            token,
            company_id=None
            if path
            in {
                "/health",
                "/health/live",
                "/health/ready",
                "/api/v1/authorization/companies",
            }
            else company_id,
            branch_id=None
            if path
            in {
                "/health",
                "/health/live",
                "/health/ready",
                "/api/v1/authorization/companies",
            }
            else branch_id,
        )
        if status >= 400:
            raise SmokeBlocked("protected route smoke failed")
    return {"check": "routes", "status": "PASS", "route_count": str(len(paths))}


def check_background(path: str, credential_file: Path) -> dict[str, str]:
    secret(credential_file)
    status, body = request(path)
    if status != 200:
        raise SmokeBlocked("application readiness endpoint failed")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SmokeBlocked("background-service health evidence is invalid") from exc
    if payload.get("state") != "HEALTHY":
        raise SmokeBlocked("application readiness is not healthy")
    components = payload.get("components")
    if (
        not isinstance(components, list)
        or not components
        or any(
            item.get("state") != "HEALTHY"
            for item in components
            if isinstance(item, dict)
        )
    ):
        raise SmokeBlocked("application readiness component is not healthy")
    return {"check": "background-services", "status": "PASS", "source": path}


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
                args.path or "/api/v1/authorization/companies", args.credential_file
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
            result = check_background(
                args.path or "/health/ready", args.credential_file
            )
    except SmokeBlocked as exc:
        print(f"BLOCKED: {exc}")
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
