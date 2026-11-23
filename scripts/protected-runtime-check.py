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


def check_postgres(runtime_root: Path, project: str, expected_sha: str, expected_schema: str) -> dict[str, str]:
    verify_runtime_identity(runtime_root, project, expected_sha, expected_schema)
    base = compose_base(runtime_root, project)
    command = base + [
        "exec",
        "-T",
        "postgres",
        "sh",
        "-eu",
        "-c",
        "pg_isready -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" >/dev/null; PGPASSWORD=\"$POSTGRES_PASSWORD\" psql -X -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -Atqc \"SELECT current_user || '|' || current_database() || '|' || rolsuper::text FROM pg_roles WHERE rolname=current_user\"",
    ]
    try:
        identity = run_read_only(command)
    except RuntimeCheckError as exc:
        raise RuntimeCheckError("PostgreSQL authenticated health is unavailable") from exc
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


def check_backend(runtime_root: Path, project: str, expected_sha: str, expected_schema: str) -> dict[str, str]:
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
        raise RuntimeCheckError("backend API health or runtime version is unavailable") from exc
    return {"service": "backend", "status": "PASS", "identity": expected_sha}


def check_database_security(
    runtime_root: Path, project: str, expected_sha: str, expected_schema: str
) -> dict[str, str]:
    verify_runtime_identity(runtime_root, project, expected_sha, expected_schema)
    base = compose_base(runtime_root, project)
    query = (
        "WITH tenant_tables AS ("
        "SELECT c.oid, c.relrowsecurity, c.relforcerowsecurity "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' AND EXISTS ("
        "SELECT 1 FROM information_schema.columns col "
        "WHERE col.table_schema = n.nspname AND col.table_name = c.relname "
        "AND col.column_name IN ('company_id','branch_id'))) "
        "SELECT r.rolsuper::text || '|' || r.rolcreaterole::text || '|' || "
        "r.rolcreatedb::text || '|' || r.rolreplication::text || '|' || "
        "r.rolbypassrls::text || '|' || "
        "(SELECT count(*) FROM tenant_tables WHERE NOT relrowsecurity) || '|' || "
        "(SELECT count(*) FROM tenant_tables WHERE relrowsecurity AND NOT relforcerowsecurity) "
        "FROM pg_roles r WHERE r.rolname = current_user"
    )
    command = base + [
        "exec",
        "-T",
        "postgres",
        "sh",
        "-eu",
        "-c",
        f"PGPASSWORD=\"$POSTGRES_PASSWORD\" psql -X -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -Atqc \"{query}\"",
    ]
    try:
        result = run_read_only(command)
    except RuntimeCheckError as exc:
        raise RuntimeCheckError("PostgreSQL security audit is unavailable") from exc
    fields = result.split("|")
    if len(fields) != 7 or not all(fields):
        raise RuntimeCheckError("PostgreSQL security audit returned incomplete evidence")
    issues: list[str] = []
    if any(fields[index].lower() != "false" for index in range(5)):
        issues.append("application database identity retains elevated role privileges")
    if fields[5] != "0" or fields[6] != "0":
        issues.append(
            f"tenant tables lack required forced row-level security ({fields[5]} without RLS, {fields[6]} without FORCE)"
        )
    if issues:
        raise RuntimeCheckError("; ".join(issues))
    return {
        "service": "database-security",
        "status": "PASS",
        "identity": "application-role",
        "tenant_tables_without_rls": fields[5],
        "tenant_tables_without_forced_rls": fields[6],
    }


def check_redis(runtime_root: Path, project: str, expected_sha: str, expected_schema: str) -> dict[str, str]:
    verify_runtime_identity(runtime_root, project, expected_sha, expected_schema)
    base = compose_base(runtime_root, project)
    command = base + [
        "exec",
        "-T",
        "redis",
        "sh",
        "-eu",
        "-c",
        "test -r /run/secrets/redis/health-password; REDISCLI_AUTH=\"$(cat /run/secrets/redis/health-password)\"; export REDISCLI_AUTH; test \"$(redis-cli --user acp-health PING)\" = PONG",
    ]
    try:
        run_read_only(command)
    except RuntimeCheckError as exc:
        raise RuntimeCheckError("Redis health credentials or connection are unavailable") from exc
    return {"service": "redis", "status": "PASS", "identity": "acp-health"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--service", choices=("backend", "database-security", "postgres", "redis"), required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--expected-schema-head", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.service == "backend":
            result = check_backend(args.runtime_root, args.project, args.expected_sha, args.expected_schema_head)
        elif args.service == "database-security":
            result = check_database_security(args.runtime_root, args.project, args.expected_sha, args.expected_schema_head)
        elif args.service == "postgres":
            result = check_postgres(args.runtime_root, args.project, args.expected_sha, args.expected_schema_head)
        else:
            result = check_redis(args.runtime_root, args.project, args.expected_sha, args.expected_schema_head)
    except RuntimeCheckError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
