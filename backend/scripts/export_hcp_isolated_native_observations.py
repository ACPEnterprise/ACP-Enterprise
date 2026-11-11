#!/usr/bin/env python3
"""Read-only, fail-closed native HCP observation export for migration rehearsal."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.customers.models import Customer, ServiceLocation
from app.jobs.models import Job
from app.operational_migration.models import (
    HcpMigrationMasterRun,
    HcpSource4NativeBindingEvidence,
)
from app.platform.branch.models import Branch
from app.platform.company.models import Company
from app.scheduling.models import Appointment

EXPECTED_ENVIRONMENT = "migration_rehearsal"
EXPECTED_DATABASE = "acp_hcp_rehearsal_import"
EXPECTED_SCHEMA_HEAD = "yp8r0t2v4x6z"
RECEIPT_CONTRACT = "hcp-isolated-restore-receipt/v1"
EXPORT_CONTRACT = "hcp-isolated-native-observations/v1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
READ_ONLY_TRANSACTION = "SET TRANSACTION READ ONLY"


@dataclass(frozen=True)
class Observation:
    domain: str
    source_id: str
    native_id: str
    source_digest: str
    applied_at: str
    binding_digest: str
    package_digest: str
    overlay_manifest_digest: str
    overlay_receipt_digest: str

    def as_dict(self) -> dict[str, str]:
        return {
            "applied_at": self.applied_at,
            "binding_digest": self.binding_digest,
            "domain": self.domain,
            "native_id": self.native_id,
            "overlay_manifest_digest": self.overlay_manifest_digest,
            "overlay_receipt_digest": self.overlay_receipt_digest,
            "package_digest": self.package_digest,
            "source_digest": self.source_digest,
            "source_id": self.source_id,
        }


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def verify_repository_sha(actual: str, expected: str) -> str:
    if not HEX40.fullmatch(actual) or not HEX40.fullmatch(expected):
        raise ValueError("repository SHA must be a full 40-character hexadecimal SHA")
    if actual != expected:
        raise ValueError("repository SHA does not match expected authority")
    return actual


def reject_database_url(database_url: str) -> None:
    parsed = urlsplit(database_url.replace("postgresql+asyncpg://", "postgresql://", 1))
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname != "postgres":
        raise ValueError("database URL must target the private migration_rehearsal postgres service")
    if parsed.path.removeprefix("/") != EXPECTED_DATABASE:
        raise ValueError("database URL does not target the rehearsal database")
    forbidden = ("preview", "production", "prod", "beta", "live")
    identity = f"{parsed.hostname}/{parsed.path}".casefold()
    if any(marker in identity for marker in forbidden):
        raise ValueError("Preview/Production database URL is forbidden")


def verify_schema_head(heads: list[str], expected: str = EXPECTED_SCHEMA_HEAD) -> str:
    if expected != EXPECTED_SCHEMA_HEAD:
        raise ValueError("canonical Alembic head is fixed to yp8r0t2v4x6z")
    if heads != [expected]:
        raise ValueError(f"Alembic head mismatch: expected [{expected!r}], got {heads!r}")
    return expected


def verify_scope(company_rows: list[str], branch_rows: list[tuple[str, str]], company_id: str, branch_id: str) -> None:
    if company_rows != [company_id]:
        raise ValueError("scope must resolve exactly one Company")
    if branch_rows != [(branch_id, company_id)]:
        raise ValueError("scope must resolve exactly one Branch belonging to Company")


def validate_observations(observations: list[Observation]) -> tuple[Observation, ...]:
    if not observations:
        raise ValueError("no native HCP observations were found")
    source_keys = [(item.domain, item.source_id) for item in observations]
    if len(source_keys) != len(set(source_keys)):
        raise ValueError("duplicate HCP source bindings")
    native_keys = [(item.domain, item.native_id) for item in observations]
    if len(native_keys) != len(set(native_keys)):
        raise ValueError("duplicate native bindings")
    for item in observations:
        if not HEX64.fullmatch(item.source_digest):
            raise ValueError("observation source digest is invalid")
        if not HEX64.fullmatch(item.binding_digest):
            raise ValueError("observation binding digest is invalid")
        if not HEX64.fullmatch(item.package_digest):
            raise ValueError("observation package digest is invalid")
        if not HEX64.fullmatch(item.overlay_manifest_digest):
            raise ValueError("observation overlay manifest digest is invalid")
        if not HEX64.fullmatch(item.overlay_receipt_digest):
            raise ValueError("observation overlay receipt digest is invalid")
    return tuple(sorted(observations, key=lambda item: (item.domain, item.source_id)))


def build_export_document(
    *,
    repository_sha: str,
    schema_head: str,
    company_id: str,
    branch_id: str,
    database: str,
    database_user: str,
    observations: list[Observation],
) -> dict[str, object]:
    verify_schema_head([schema_head])
    ordered = validate_observations(observations)
    return {
        "contract": EXPORT_CONTRACT,
        "database_identity": {"database": database, "user": database_user},
        "environment": EXPECTED_ENVIRONMENT,
        "observations": [item.as_dict() for item in ordered],
        "repository_sha": repository_sha,
        "schema_head": schema_head,
        "scope": {"branch_id": branch_id, "company_id": company_id},
    }


async def set_read_only_transaction(connection: Any) -> None:
    await connection.execute(text(READ_ONLY_TRANSACTION))


def resolve_lineage(
    *,
    domain: str,
    source_id: str,
    native_id: str,
    candidates: list[Mapping[str, str]],
) -> Mapping[str, str]:
    matches = [
        item
        for item in candidates
        if item.get("domain") == domain and item.get("source_id") == source_id
    ]
    if not matches:
        raise ValueError(f"missing durable overlay lineage for {domain}:{source_id}")
    if len(matches) != 1:
        raise ValueError(f"ambiguous durable overlay lineage for {domain}:{source_id}")
    match = matches[0]
    if match.get("native_id") != native_id:
        raise ValueError(f"overlay lineage native target mismatch for {domain}:{source_id}")
    if not match.get("source_digest") or not match.get("applied_at"):
        raise ValueError(f"incomplete durable overlay lineage for {domain}:{source_id}")
    return match


def verify_restore_receipt(path: Path, expected_schema_head: str) -> None:
    value = json.loads(path.read_bytes())
    if value.get("contract") != RECEIPT_CONTRACT:
        raise ValueError("restore receipt contract is invalid")
    if value.get("environment") != EXPECTED_ENVIRONMENT:
        raise ValueError("restore receipt is not for migration_rehearsal")
    if value.get("database") != EXPECTED_DATABASE:
        raise ValueError("restore receipt database identity is invalid")
    if value.get("schema_head") != expected_schema_head:
        raise ValueError("restore receipt schema head is invalid")
    if value.get("database_identity_verified") is not True:
        raise ValueError("restore receipt lacks database identity verification")
    if value.get("source_backup_mutated") is not False:
        raise ValueError("restore receipt does not prove source immutability")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("restore receipt permissions are not restrictive")


def _receipt_lineage(master: HcpMigrationMasterRun) -> list[Mapping[str, str]]:
    replay = master.replay_state or {}
    overlay = replay.get("hcp_current_overlay")
    if not isinstance(overlay, dict):
        return []
    receipts = overlay.get("receipts")
    if not isinstance(receipts, dict):
        return []
    candidates: list[Mapping[str, str]] = []
    for manifest_digest, receipt in receipts.items():
        if not isinstance(receipt, dict):
            raise ValueError("durable overlay receipt is malformed")
        if receipt.get("contract") != "hcp-current-overlay-executor/v1":
            raise ValueError("durable overlay receipt contract is invalid")
        if receipt.get("manifest_digest") != str(manifest_digest):
            raise ValueError("durable overlay receipt manifest identity is invalid")
        journal = receipt.get("journal")
        if not isinstance(journal, list):
            raise ValueError("durable overlay receipt journal is missing")
        receipt_digest = str(receipt.get("digest") or "")
        receipt_payload = {
            "contract": receipt.get("contract"),
            "manifest_digest": receipt.get("manifest_digest"),
            "rollback_backup_digest": receipt.get("rollback_backup_digest"),
            "counts": receipt.get("counts"),
            "journal": journal,
        }
        if (
            not HEX64.fullmatch(receipt_digest)
            or canonical_sha256(receipt_payload) != receipt_digest
        ):
            raise ValueError("durable overlay receipt digest is invalid")
        for item in journal:
            if not isinstance(item, dict) or not isinstance(item.get("key"), dict):
                raise ValueError("durable overlay journal entry is malformed")
            key = item["key"]
            if item.get("outcome") not in {"created", "updated", "idempotent_replay"}:
                continue
            applied_at = master.completed_at.isoformat() if master.completed_at else ""
            candidates.append(
                {
                    "domain": str(key.get("domain") or ""),
                    "source_id": str(key.get("source_id") or ""),
                    "native_id": str(item.get("native_id") or ""),
                    "source_digest": str(item.get("after_digest") or ""),
                    "applied_at": applied_at,
                    "overlay_manifest_digest": str(manifest_digest),
                    "overlay_receipt_digest": receipt_digest,
                }
            )
    return candidates


async def _native_exists(session: AsyncSession, domain: str, native_id: Any, company_id: Any, branch_id: Any) -> bool:
    if domain == "customer":
        statement = select(Customer.id).where(Customer.id == native_id, Customer.company_id == company_id)
    elif domain == "service_location":
        statement = (
            select(ServiceLocation.id)
            .join(Customer, Customer.id == ServiceLocation.customer_id)
            .where(ServiceLocation.id == native_id, Customer.company_id == company_id)
        )
    elif domain == "job":
        statement = select(Job.id).where(Job.id == native_id, Job.company_id == company_id, Job.branch_id == branch_id)
    elif domain == "appointment":
        statement = select(Appointment.id).where(Appointment.id == native_id, Appointment.company_id == company_id, Appointment.branch_id == branch_id)
    else:
        raise ValueError(f"unsupported HCP binding domain: {domain}")
    return len((await session.execute(statement)).scalars().all()) == 1


async def export(args: argparse.Namespace) -> dict[str, object]:
    database_url = args.database_url or os.environ.get("DATABASE_URL", "")
    reject_database_url(database_url)
    verify_repository_sha(args.repository_sha, args.expected_repository_sha)
    verify_restore_receipt(Path(args.restore_receipt).resolve(), args.expected_schema_head)

    engine = create_async_engine(database_url, pool_pre_ping=False)
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                await set_read_only_transaction(connection)
                async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                    identity = (await session.execute(text("SELECT current_database(), current_user"))).one()
                    if identity[0] != EXPECTED_DATABASE or identity[1] != "acp_hcp_rehearsal":
                        raise ValueError("database identity does not match migration_rehearsal")
                    heads = list((await session.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num"))).scalars().all())
                    verify_schema_head(heads, args.expected_schema_head)
                    company_rows = [
                        str(value)
                        for value in (
                            await session.execute(
                                select(Company.id).where(Company.id == args.company_id)
                            )
                        )
                        .scalars()
                        .all()
                    ]
                    branch_rows = [
                        (str(row[0]), str(row[1]))
                        for row in (
                            await session.execute(
                                select(Branch.id, Branch.company_id).where(
                                    Branch.id == args.branch_id
                                )
                            )
                        ).all()
                    ]
                    verify_scope(company_rows, branch_rows, args.company_id, args.branch_id)

                    result = await session.execute(
                        select(HcpSource4NativeBindingEvidence, HcpMigrationMasterRun)
                        .join(HcpMigrationMasterRun, HcpMigrationMasterRun.id == HcpSource4NativeBindingEvidence.master_run_id)
                        .where(
                            HcpSource4NativeBindingEvidence.company_id == args.company_id,
                            HcpSource4NativeBindingEvidence.branch_id == args.branch_id,
                            HcpMigrationMasterRun.company_id == args.company_id,
                            HcpMigrationMasterRun.branch_id == args.branch_id,
                            HcpMigrationMasterRun.status == "completed_current_operational",
                        )
                        .order_by(
                            HcpSource4NativeBindingEvidence.domain,
                            HcpSource4NativeBindingEvidence.source4_source_id,
                        )
                    )
                    observations: list[Observation] = []
                    for binding, master in result.all():
                        if not await _native_exists(session, binding.domain, binding.native_id, args.company_id, args.branch_id):
                            raise ValueError(f"native row missing or outside scope for {binding.domain}:{binding.source4_source_id}")
                        lineage = resolve_lineage(
                            domain=binding.domain,
                            source_id=binding.source4_source_id,
                            native_id=str(binding.native_id),
                            candidates=list(_receipt_lineage(master)),
                        )
                        observations.append(
                            Observation(
                                domain=binding.domain,
                                source_id=binding.source4_source_id,
                                native_id=str(binding.native_id),
                                source_digest=str(lineage["source_digest"]),
                                applied_at=str(lineage["applied_at"]),
                                binding_digest=binding.binding_digest,
                                package_digest=binding.package_digest,
                                overlay_manifest_digest=str(lineage["overlay_manifest_digest"]),
                                overlay_receipt_digest=str(lineage["overlay_receipt_digest"]),
                            )
                        )
                    document = build_export_document(
                        repository_sha=args.repository_sha,
                        schema_head=args.expected_schema_head,
                        company_id=args.company_id,
                        branch_id=args.branch_id,
                        database=identity[0],
                        database_user=identity[1],
                        observations=observations,
                    )
    finally:
        await engine.dispose()
    write_private_json(Path(args.output).resolve(), document)
    return document


def write_private_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.chmod(path, 0o600)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    root.add_argument("--database-url")
    root.add_argument("--environment", default=EXPECTED_ENVIRONMENT)
    root.add_argument("--repository-sha", required=True)
    root.add_argument("--expected-repository-sha", required=True)
    root.add_argument("--expected-schema-head", default=EXPECTED_SCHEMA_HEAD)
    root.add_argument("--expected-database-identity", default=EXPECTED_DATABASE)
    root.add_argument("--company-id", required=True)
    root.add_argument("--branch-id", required=True)
    root.add_argument("--restore-receipt", required=True)
    root.add_argument("--output", required=True)
    return root


def main() -> None:
    args = parser().parse_args()
    if args.environment != EXPECTED_ENVIRONMENT:
        raise SystemExit("environment must be migration_rehearsal")
    if args.expected_database_identity != EXPECTED_DATABASE:
        raise SystemExit("expected database identity must be the rehearsal database")
    asyncio.run(export(args))


if __name__ == "__main__":
    main()
