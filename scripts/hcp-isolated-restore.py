#!/usr/bin/env python3
"""Restore one Preview-isolated HCP dump into the private rehearsal Compose target.

This command deliberately has no arbitrary database URL option.  The only restore
target is the ``postgres`` service in docker-compose.migration-rehearsal.yml.  The
source dump is streamed to pg_restore and is never opened for writing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EXPECTED_DATABASE = "acp_hcp_rehearsal_import"
EXPECTED_USER = "acp_hcp_rehearsal"
EXPECTED_SCHEMA_HEAD = "yp8r0t2v4x6z"
COMPOSE_ENVIRONMENT = "migration_rehearsal"
MANIFEST_CONTRACT = "platform-resilience.backup.v1"
COMPOSE_FILE = Path(__file__).resolve().parents[1] / "docker-compose.migration-rehearsal.yml"
os.umask(0o077)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compose_prefix(compose_file: Path, project_name: str) -> list[str]:
    return [
        "docker",
        "compose",
        "-f",
        str(compose_file),
        "--project-name",
        project_name,
    ]


def run(command: list[str], *, input_bytes: bytes | None = None) -> str:
    result = subprocess.run(
        command,
        check=True,
        input=input_bytes,
        capture_output=True,
        text=input_bytes is None,
    )
    output = result.stdout
    return output.decode().strip() if isinstance(output, bytes) else output.strip()


def load_backup_manifest(backup: Path, expected_source_identity: str) -> dict[str, Any]:
    manifest_path = backup.with_suffix(backup.suffix + ".manifest.json")
    if not manifest_path.is_file():
        raise ValueError(f"Backup manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("contract_version") != MANIFEST_CONTRACT:
        raise ValueError("Unsupported backup manifest contract")
    if manifest.get("format") != "postgresql-custom":
        raise ValueError("Backup is not a PostgreSQL custom-format dump")
    if manifest.get("environment") != "preview-isolated":
        raise ValueError("Backup must be sourced from preview-isolated")
    if manifest.get("database_identity") != expected_source_identity:
        raise ValueError("Backup source database identity is not approved")
    actual_digest = sha256_file(backup)
    if manifest.get("sha256") != actual_digest:
        raise ValueError("Backup checksum does not match its manifest")
    if stat.S_IMODE(backup.stat().st_mode) & 0o077:
        raise ValueError("Backup permissions are not restrictive")
    if stat.S_IMODE(manifest_path.stat().st_mode) & 0o077:
        raise ValueError("Backup manifest permissions are not restrictive")
    return manifest


def validate_compose_config(config: dict[str, Any]) -> None:
    services = config.get("services")
    if not isinstance(services, dict) or set(services) != {"postgres", "exporter"}:
        raise ValueError("Rehearsal Compose must contain only postgres and exporter")
    postgres = services.get("postgres")
    if not isinstance(postgres, dict):
        raise ValueError("Rehearsal postgres service is missing")
    labels = postgres.get("labels", {})
    if not isinstance(labels, dict):
        raise ValueError("Rehearsal postgres labels are missing")
    if labels.get("acp.environment") != COMPOSE_ENVIRONMENT:
        raise ValueError("Rehearsal environment label is not migration_rehearsal")
    if labels.get("acp.production_access") not in {False, "false"}:
        raise ValueError("Rehearsal target must deny Production access")
    if labels.get("acp.preview_access") not in {False, "false"}:
        raise ValueError("Rehearsal target must deny Preview access")
    if postgres.get("ports"):
        raise ValueError("Rehearsal PostgreSQL must not publish a host port")
    networks = postgres.get("networks", {})
    if "migration_rehearsal" not in networks:
        raise ValueError("Rehearsal postgres is outside the private network")
    if config.get("networks", {}).get("migration_rehearsal", {}).get("internal") is not True:
        raise ValueError("Rehearsal network must be internal")


def inspect_compose_config(compose_file: Path, project_name: str) -> None:
    raw = run(
        compose_prefix(compose_file, project_name)
        + ["--profile", "export", "config", "--format", "json"]
    )
    validate_compose_config(json.loads(raw))


def inspect_running_target(compose_file: Path, project_name: str) -> None:
    container_id = run(
        compose_prefix(compose_file, project_name) + ["ps", "-q", "postgres"]
    )
    if not container_id:
        raise ValueError("Rehearsal postgres container is not running")
    raw = run(["docker", "inspect", container_id])
    container = json.loads(raw)[0]
    labels = container.get("Config", {}).get("Labels", {})
    if labels.get("acp.environment") != COMPOSE_ENVIRONMENT:
        raise ValueError("Running target is not labeled migration_rehearsal")
    if labels.get("acp.production_access") != "false":
        raise ValueError("Running target does not deny Production access")
    if labels.get("acp.preview_access") != "false":
        raise ValueError("Running target does not deny Preview access")
    published = container.get("NetworkSettings", {}).get("Ports") or {}
    if any(value for value in published.values()):
        raise ValueError("Running rehearsal PostgreSQL has a published port")


def sql(compose_file: Path, project_name: str, statement: str) -> str:
    return run(
        compose_prefix(compose_file, project_name)
        + [
            "exec",
            "-T",
            "postgres",
            "psql",
            "-Atq",
            "-U",
            EXPECTED_USER,
            "-d",
            EXPECTED_DATABASE,
            "-c",
            statement,
        ]
    )


def write_private_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    if path.exists():
        raise ValueError(f"Refusing to overwrite receipt: {path}")
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


def restore(args: argparse.Namespace) -> None:
    backup = Path(args.backup).resolve()
    compose_file = COMPOSE_FILE
    if args.expected_schema_head != EXPECTED_SCHEMA_HEAD:
        raise ValueError("canonical Alembic head is fixed to yp8r0t2v4x6z")
    if not backup.is_file():
        raise ValueError(f"Backup does not exist: {backup}")
    manifest = load_backup_manifest(backup, args.expected_source_identity)
    inspect_compose_config(compose_file, args.project_name)

    run(
        compose_prefix(compose_file, args.project_name)
        + ["up", "-d", "--wait", "postgres"]
    )
    inspect_running_target(compose_file, args.project_name)

    existing_tables = sql(
        compose_file,
        args.project_name,
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname NOT IN ('pg_catalog','information_schema') "
        "AND c.relkind IN ('r','p','v','m','f')",
    )
    if existing_tables != "0":
        raise ValueError("Rehearsal database is not empty; refusing to overwrite it")

    dump_bytes = backup.read_bytes()
    run(
        compose_prefix(compose_file, args.project_name)
        + ["exec", "-T", "postgres", "pg_restore", "--list", "-"],
        input_bytes=dump_bytes,
    )
    run(
        compose_prefix(compose_file, args.project_name)
        + [
            "exec",
            "-T",
            "postgres",
            "pg_restore",
            "--exit-on-error",
            "--single-transaction",
            "--no-owner",
            "--dbname",
            EXPECTED_DATABASE,
            "-",
        ],
        input_bytes=dump_bytes,
    )

    identity = sql(
        compose_file,
        args.project_name,
        "SELECT current_database() || E'\\t' || current_user",
    )
    if identity != f"{EXPECTED_DATABASE}\t{EXPECTED_USER}":
        raise ValueError(f"Restored database identity mismatch: {identity!r}")
    heads = sql(
        compose_file,
        args.project_name,
        "SELECT version_num FROM alembic_version ORDER BY version_num",
    ).splitlines()
    if heads != [args.expected_schema_head]:
        raise ValueError(
            f"Restored Alembic head mismatch: expected {args.expected_schema_head}, got {heads}"
        )

    receipt = {
        "contract": "hcp-isolated-restore-receipt/v1",
        "environment": COMPOSE_ENVIRONMENT,
        "compose_file_sha256": sha256_file(compose_file),
        "compose_project": args.project_name,
        "database": EXPECTED_DATABASE,
        "database_user": EXPECTED_USER,
        "database_identity_verified": True,
        "schema_head": args.expected_schema_head,
        "backup_file": backup.name,
        "backup_sha256": manifest["sha256"],
        "backup_source_database_identity": manifest["database_identity"],
        "backup_source_environment": manifest["environment"],
        "restored_at": datetime.now(timezone.utc).isoformat(),
        "source_backup_mutated": False,
    }
    write_private_json(Path(args.receipt_output).resolve(), receipt)
    print(json.dumps({"result": "ISOLATED_RESTORE_COMPLETED", **receipt}, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    root.add_argument("--backup", required=True)
    root.add_argument("--expected-source-identity", required=True)
    root.add_argument("--receipt-output", required=True)
    root.add_argument("--project-name", default="hcp-isolated-rehearsal")
    root.add_argument("--expected-schema-head", default=EXPECTED_SCHEMA_HEAD)
    root.set_defaults(action=restore)
    return root


def main() -> None:
    args = parser().parse_args()
    try:
        args.action(args)
    except (FileNotFoundError, json.JSONDecodeError, subprocess.CalledProcessError, ValueError) as error:
        print(json.dumps({"result": "BLOCKED", "reason": str(error)}), file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
