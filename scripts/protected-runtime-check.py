#!/usr/bin/env python3
"""Perform authenticated, read-only health checks against a protected Preview runtime."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


class RuntimeCheckError(RuntimeError):
    pass


def compose_base(runtime_root: Path, project: str) -> list[str]:
    current = runtime_root / "current"
    if not current.exists():
        raise RuntimeCheckError("protected runtime current release is unavailable")
    compose_file = current / "docker-compose.preview.yml"
    if not compose_file.is_file() or compose_file.is_symlink():
        raise RuntimeCheckError("protected Preview compose file is unavailable")
    return ["docker", "compose", "--project-name", project, "--file", str(compose_file)]


def run_read_only(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeCheckError("protected health command could not execute") from exc
    if completed.returncode != 0:
        raise RuntimeCheckError("protected health command failed")
    return completed.stdout.strip()


def verify_runtime_identity(
    runtime_root: Path, project: str, expected_sha: str, expected_schema: str
) -> None:
    metadata_path = runtime_root / "current" / ".release-metadata.json"
    if metadata_path.is_symlink() or not metadata_path.is_file():
        raise RuntimeCheckError("protected release metadata is unavailable")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeCheckError("protected release metadata is invalid") from exc
    if metadata.get("app_version") != expected_sha:
        raise RuntimeCheckError("protected runtime application identity mismatch")

    current = run_read_only(
        [
            "docker",
            "compose",
            "--project-name",
            project,
            "--file",
            str(runtime_root / "current" / "docker-compose.preview.yml"),
            "exec",
            "-T",
            "backend",
            "alembic",
            "current",
        ]
    )
    heads = re.findall(r"([a-z0-9][a-z0-9_-]{11,63}) \(head\)", current)
    if heads != [expected_schema]:
        raise RuntimeCheckError("protected runtime schema identity mismatch")


def check_postgres(
    runtime_root: Path, project: str, expected_sha: str, expected_schema: str
) -> dict[str, str]:
    verify_runtime_identity(runtime_root, project, expected_sha, expected_schema)
    base = compose_base(runtime_root, project)
    command = base + [
        "exec",
        "-T",
        "postgres",
        "sh",
        "-eu",
        "-c",
        'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null; PGPASSWORD="$POSTGRES_PASSWORD" psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atqc "SELECT current_user || \'|\' || current_database() || \'|\' || rolsuper::text FROM pg_roles WHERE rolname=current_user"',
    ]
    try:
        identity = run_read_only(command)
    except RuntimeCheckError as exc:
        raise RuntimeCheckError(
            "PostgreSQL authenticated health is unavailable"
        ) from exc
    parts = identity.split("|")
    if len(parts) != 3 or not all(parts):
        raise RuntimeCheckError("PostgreSQL authenticated identity is unavailable")
    if parts[2].lower() not in {"true", "false"}:
        raise RuntimeCheckError("PostgreSQL superuser state is invalid")
    return {
        "service": "postgres",
        "status": "PASS",
        "identity": f"{parts[0]}@{parts[1]}",
        "superuser": parts[2].lower(),
    }


def check_backend(
    runtime_root: Path, project: str, expected_sha: str, expected_schema: str
) -> dict[str, str]:
    verify_runtime_identity(runtime_root, project, expected_sha, expected_schema)
    base = compose_base(runtime_root, project)
    command = base + [
        "exec",
        "-T",
        "backend",
        "python",
        "-c",
        "import json,urllib.request; p=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)); assert p.get('status') == 'healthy'; assert p.get('version') == __import__('os').environ.get('APP_VERSION')",
    ]
    try:
        run_read_only(command)
    except RuntimeCheckError as exc:
        raise RuntimeCheckError(
            "backend API health or runtime version is unavailable"
        ) from exc
    return {"service": "backend", "status": "PASS", "identity": expected_sha}


def check_database_security(
    runtime_root: Path,
    project: str,
    expected_sha: str,
    expected_schema: str,
    expected_application_table_count: int = 429,
    expected_forced_rls_count: int = 411,
) -> dict[str, str]:
    verify_runtime_identity(runtime_root, project, expected_sha, expected_schema)
    base = compose_base(runtime_root, project)
    command = base + [
        "exec",
        "-T",
        "backend",
        "python",
        "scripts/protected-database-security-probe.py",
        "--expected-role",
        "acp_app",
        "--expected-application-table-count",
        str(expected_application_table_count),
        "--expected-forced-rls-count",
        str(expected_forced_rls_count),
    ]
    try:
        result = run_read_only(command)
    except RuntimeCheckError as exc:
        raise RuntimeCheckError("PostgreSQL security audit is unavailable") from exc
    try:
        payload = json.loads(result)
    except json.JSONDecodeError as exc:
        raise RuntimeCheckError(
            "application database security probe returned invalid evidence"
        ) from exc
    if not isinstance(payload, dict) or payload.get("role") != "acp_app":
        raise RuntimeCheckError(
            "PostgreSQL security audit returned incomplete evidence"
        )
    if (
        payload.get("application_table_count") != expected_application_table_count
        or payload.get("forced_rls_count") != expected_forced_rls_count
        or payload.get("tenant_tables_without_rls") != 0
        or payload.get("tenant_tables_without_forced_rls") != 0
    ):
        raise RuntimeCheckError(
            "PostgreSQL row-level security coverage does not match the release contract"
        )
    return {
        "service": "database-security",
        "status": "PASS",
        "identity": str(payload["role"]),
        "application_table_count": str(payload["application_table_count"]),
        "forced_rls_count": str(payload["forced_rls_count"]),
        "tenant_table_count": str(payload["tenant_table_count"]),
        "tenant_tables_without_rls": str(payload["tenant_tables_without_rls"]),
        "tenant_tables_without_forced_rls": str(
            payload["tenant_tables_without_forced_rls"]
        ),
    }


def check_redis(
    runtime_root: Path, project: str, expected_sha: str, expected_schema: str
) -> dict[str, str]:
    verify_runtime_identity(runtime_root, project, expected_sha, expected_schema)
    base = compose_base(runtime_root, project)
    command = base + [
        "exec",
        "-T",
        "redis",
        "sh",
        "-eu",
        "-c",
        'test -r /run/secrets/redis/health-password; REDISCLI_AUTH="$(cat /run/secrets/redis/health-password)"; export REDISCLI_AUTH; test "$(redis-cli --user acp-health PING)" = PONG',
    ]
    try:
        run_read_only(command)
    except RuntimeCheckError as exc:
        raise RuntimeCheckError(
            "Redis health credentials or connection are unavailable"
        ) from exc
    return {"service": "redis", "status": "PASS", "identity": "acp-health"}


def check_smoke(
    runtime_root: Path,
    project: str,
    expected_sha: str,
    expected_schema: str,
    smoke_check: str,
) -> dict[str, str]:
    verify_runtime_identity(runtime_root, project, expected_sha, expected_schema)
    credential_file = "/run/secrets/preview-smoke-token"
    base = compose_base(runtime_root, project)
    command = base + [
        "exec",
        "-T",
        "backend",
        "python",
        "-m",
        "scripts.protected_smoke_check",
        "--check",
        smoke_check,
        "--credential-file",
        credential_file,
    ]
    if smoke_check == "routes":
        command.extend(
            ["--route", "/health", "--route", "/api/v1/authorization/companies"]
        )
    try:
        result = run_read_only(command)
    except RuntimeCheckError as exc:
        raise RuntimeCheckError(
            f"protected {smoke_check} smoke is unavailable"
        ) from exc
    try:
        payload = json.loads(result)
    except json.JSONDecodeError as exc:
        raise RuntimeCheckError(
            f"protected {smoke_check} smoke returned invalid evidence"
        ) from exc
    if payload.get("check") != smoke_check or payload.get("status") != "PASS":
        raise RuntimeCheckError(f"protected {smoke_check} smoke did not pass")
    return {"service": smoke_check, "status": "PASS", "identity": "preview-smoke"}


def check_schema(
    runtime_root: Path, project: str, expected_sha: str, expected_schema: str
) -> dict[str, str]:
    verify_runtime_identity(runtime_root, project, expected_sha, expected_schema)
    return {"service": "schema", "status": "PASS", "identity": expected_schema}


def check_release_metadata(
    runtime_root: Path, project: str, expected_sha: str, expected_schema: str
) -> dict[str, str]:
    verify_runtime_identity(runtime_root, project, expected_sha, expected_schema)
    return {"service": "release-metadata", "status": "PASS", "identity": expected_sha}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--service",
        choices=(
            "backend",
            "database-security",
            "postgres",
            "redis",
            "authentication",
            "authorization",
            "tenant-isolation",
            "routes",
            "background-services",
            "accounting-readonly",
            "schema",
            "release-metadata",
        ),
        required=True,
    )
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--expected-schema-head", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.service == "backend":
            result = check_backend(
                args.runtime_root,
                args.project,
                args.expected_sha,
                args.expected_schema_head,
            )
        elif args.service == "database-security":
            result = check_database_security(
                args.runtime_root,
                args.project,
                args.expected_sha,
                args.expected_schema_head,
            )
        elif args.service == "postgres":
            result = check_postgres(
                args.runtime_root,
                args.project,
                args.expected_sha,
                args.expected_schema_head,
            )
        elif args.service in {
            "authentication",
            "authorization",
            "tenant-isolation",
            "routes",
            "background-services",
            "accounting-readonly",
        }:
            result = check_smoke(
                args.runtime_root,
                args.project,
                args.expected_sha,
                args.expected_schema_head,
                args.service,
            )
        elif args.service == "schema":
            result = check_schema(
                args.runtime_root,
                args.project,
                args.expected_sha,
                args.expected_schema_head,
            )
        elif args.service == "release-metadata":
            result = check_release_metadata(
                args.runtime_root,
                args.project,
                args.expected_sha,
                args.expected_schema_head,
            )
        else:
            result = check_redis(
                args.runtime_root,
                args.project,
                args.expected_sha,
                args.expected_schema_head,
            )
    except RuntimeCheckError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
