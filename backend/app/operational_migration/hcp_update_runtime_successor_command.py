"""Read-only runtime eligibility inventory for every current-overlay UPDATE."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import stat
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from uuid import UUID

from sqlalchemy import text

from app.core.config import settings
from app.database.session import AsyncSessionFactory
from app.operational_migration.hcp_current_overlay import CurrentOverlayManifest
from app.operational_migration.hcp_current_overlay_command import (
    CurrentOverlayExecutionAuthority,
)
from app.operational_migration.hcp_source4_native_binding import (
    BindingDisposition,
    HcpSource4NativeBindingBootstrap,
)

CONTRACT = "hcp-update-runtime-successor-inventory/v1"
COHORT_CONTRACT = "hcp-update-runtime-cohorts/v1"
COHORTS = {"CURRENT_OPERATIONAL", "SAFE_HISTORICAL", "SAFE_UPDATE", "OTHER_HELD"}
ADMISSIBLE = {
    BindingDisposition.BINDING_ALREADY_PRESENT,
    BindingDisposition.PROVABLE_NATIVE_SUCCESSOR_BINDING,
}


def _private_json(path: Path) -> dict[str, object]:
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError(f"{path.name} permissions must be 0600")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise TypeError(f"{path.name} must contain an object")
    return value


def _cohorts(path: Path) -> dict[tuple[str, str], str]:
    value = _private_json(path)
    if value.get("contract") != COHORT_CONTRACT:
        raise ValueError("runtime cohort contract mismatch")
    result: dict[tuple[str, str], str] = {}
    for item in value.get("records", []):
        key = (str(item["domain"]), str(item["source_id"]))
        cohort = str(item["cohort"])
        if key in result or cohort not in COHORTS:
            raise ValueError("runtime cohort evidence is invalid")
        result[key] = cohort
    return result


async def run(authority_path: Path, cohort_path: Path) -> dict[str, object]:
    authority = CurrentOverlayExecutionAuthority.load(authority_path)
    manifest: CurrentOverlayManifest = authority.verify_artifacts()
    repository_sha = subprocess.run(  # noqa: ASYNC221
        ("git", "rev-parse", "HEAD"), check=True, capture_output=True, text=True
    ).stdout.strip()
    if repository_sha != authority.expected_repository_sha:
        raise ValueError("runtime inventory protected authority mismatch")
    if (
        os.getenv("TARGET_ENVIRONMENT") != "preview"
        or os.getenv("PREVIEW_ACCESS_ENABLED") != "true"
        or os.getenv("PRODUCTION_ACCESS_ENABLED", "false") != "false"
    ):
        raise ValueError("runtime inventory requires the sanctioned Preview boundary")
    cohorts = _cohorts(cohort_path)
    updates = tuple(record for record in manifest.records if record.assertion.value == "update")
    update_keys = {(record.domain, record.source_id) for record in updates}
    if set(cohorts) != update_keys:
        raise ValueError("runtime cohorts must classify every UPDATE exactly once")
    service = HcpSource4NativeBindingBootstrap(
        company_id=authority.company_id,
        branch_id=authority.branch_id,
        master_run_id=UUID(int=0),
        customer_run_id=UUID(int=0),
        operational_run_id=UUID(int=0),
        package_digest=authority.expected_base_source4_digest,
    )
    async with AsyncSessionFactory() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        schemas = tuple(
            (await session.scalars(text("SELECT version_num FROM alembic_version"))).all()
        )
        if schemas != (authority.expected_schema_head,):
            raise ValueError("runtime inventory schema authority mismatch")
        candidates = await service.classify_inventory(session, manifest.records)
        await session.rollback()
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    cohort_counts: dict[str, Counter[str]] = defaultdict(Counter)
    records: list[dict[str, object]] = []
    current_blockers = 0
    for candidate in candidates:
        cohort = cohorts[(candidate.key.domain, candidate.key.source_id)]
        counts[candidate.key.domain][candidate.disposition.value] += 1
        cohort_counts[cohort][candidate.disposition.value] += 1
        if cohort == "CURRENT_OPERATIONAL" and candidate.disposition not in ADMISSIBLE:
            current_blockers += 1
        records.append(
            {
                "domain": candidate.key.domain,
                "source_id": candidate.key.source_id,
                "original_assertion": "update",
                "cohort": cohort,
                "disposition": candidate.disposition.value,
                "native_id": str(candidate.native_id) if candidate.native_id else None,
                "legacy_identity_id": (
                    str(candidate.legacy_identity_id)
                    if candidate.legacy_identity_id
                    else None
                ),
                "reason": candidate.reason,
                "evidence_digest": candidate.digest,
            }
        )
    return {
        "contract": CONTRACT,
        "mutation_authority": "none",
        "protected_authority": repository_sha,
        "schema_head": authority.expected_schema_head,
        "database": settings.database_url.rsplit("/", 1)[-1],
        "update_count": len(candidates),
        "counts_by_domain": {key: dict(value) for key, value in sorted(counts.items())},
        "counts_by_cohort": {
            key: dict(value) for key, value in sorted(cohort_counts.items())
        },
        "current_operational_graph_admittable": current_blockers == 0,
        "current_operational_blocker_count": current_blockers,
        "runtime_hold_contract": "not_authorized",
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority-file", required=True, type=Path)
    parser.add_argument("--cohort-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = asyncio.run(run(args.authority_file, args.cohort_file))
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    args.output.chmod(0o600)
    print(json.dumps({"status": "classified", "updates": result["update_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
