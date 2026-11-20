"""Derive an HCP packet that holds only unresolved native bindings.

This is a read-only classifier plus custody transformation.  It never edits
the source packet or the database.  A held record retains its source
disposition and payload in discrepancy evidence, while its executable payload
is removed from the runtime packet so an unresolved relationship cannot be
materialized accidentally.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import UUID

from app.database.session import AsyncSessionFactory
from app.operational_migration.hcp_november_bundle import NovemberQualificationAuthority
from app.operational_migration.hcp_november_executor import NovemberExecutionEnvelope
from app.operational_migration.hcp_source4_native_binding import (
    BindingDisposition,
    HcpSource4NativeBindingBootstrap,
)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_private(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    os.chmod(path, 0o600)


def packet_inventory(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(item["disposition"]).upper() for item in records)
    held = counts["HOLD"] + counts["HOLD_QUARANTINE"]
    held_keys = {
        (str(item["domain"]), str(item["source_id"]))
        for item in records
        if str(item["disposition"]).upper() in {"HOLD", "HOLD_QUARANTINE"}
    }
    edges = sum(
        1
        for item in records
        if str(item["disposition"]).upper() in {"CREATE", "UPDATE", "REPLAY"}
        for parent in item.get("parent_keys", [])
        if (str(parent["domain"]), str(parent["source_id"])) in held_keys
    )
    return {
        "counts": {key: counts.get(key, 0) for key in ("CREATE", "HOLD", "HOLD_QUARANTINE", "REPLAY", "UPDATE")},
        "total_held": held,
        "executable_count": len(records) - held,
        "held_parent_executable_edges": edges,
    }


def packet_payload(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract": packet["contract"],
        "qualification_digest": packet["qualification_digest"],
        "bundle_sha256": packet["bundle_sha256"],
        "policy_digest": packet["policy_digest"],
        "reconciliation_digest": packet["reconciliation_digest"],
        "company_id": packet["company_id"],
        "branch_id": packet["branch_id"],
        "actor_id": packet["actor_id"],
        "provider_company_id": packet["provider_company_id"],
        "schema_head": packet["schema_head"],
        "environment": packet["environment"],
        "records": packet["records"],
        "acquired_at": packet["acquired_at"],
    }


def envelope_payload(envelope: dict[str, Any]) -> dict[str, Any]:
    return {
        key: envelope[key]
        for key in (
            "contract", "source_packet_sha256", "source_packet_digest", "bundle_sha256",
            "policy_digest", "reconciliation_digest", "company_id", "branch_id",
            "actor_id", "provider_company_id", "repository_sha", "schema_head",
            "environment", "packet_counts", "total_held", "executable_count",
            "unexplained_omissions", "lineage_gaps", "ambiguous_lineage",
            "held_parent_executable_edges", "operational_hold_policy",
            "operational_hold_source_ids", "clean_baseline_bootstrap",
        )
    }


async def classify(authority_path: Path) -> tuple[NovemberQualificationAuthority, NovemberExecutionEnvelope, list[Any]]:
    authority = NovemberQualificationAuthority.load(authority_path)
    envelope = NovemberExecutionEnvelope.load(authority.execution_packet_path)
    updates = tuple(record for record in envelope.packet.overlay_manifest.records if record.assertion.value == "update")
    async with AsyncSessionFactory() as session:
        bootstrap = HcpSource4NativeBindingBootstrap(
            company_id=authority.company_id,
            branch_id=authority.branch_id,
            master_run_id=UUID("00000000-0000-0000-0000-000000000001"),
            customer_run_id=UUID("00000000-0000-0000-0000-000000000002"),
            operational_run_id=UUID("00000000-0000-0000-0000-000000000003"),
            package_digest=authority.runtime_package_digest or authority.bundle_sha256,
        )
        candidates = list(await bootstrap.classify_inventory(session, updates))
    return authority, envelope, candidates


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    authority, envelope, candidates = await classify(args.authority_file)
    records = [dict(item) for item in envelope.packet.records]
    candidate_by_key = {(item.key.domain, item.key.source_id): item for item in candidates}
    blocked = {
        key for key, candidate in candidate_by_key.items()
        if candidate.disposition not in {
            BindingDisposition.BINDING_ALREADY_PRESENT,
            BindingDisposition.PROVABLE_NATIVE_SUCCESSOR_BINDING,
        }
    }
    # Financial and dispatch records require a native Job parent.  The source
    # packet contains some historical records with only customer/location
    # locators; hold those records explicitly instead of allowing the native
    # adapter to fail mid-transaction.
    for item in records:
        disposition = str(item.get("disposition", "")).upper()
        if disposition not in {"CREATE", "UPDATE", "REPLAY"}:
            continue
        domain = str(item.get("domain", ""))
        if domain in {"appointment", "estimate", "invoice"} and not any(
            str(parent.get("domain")) == "job" for parent in item.get("parent_keys", [])
        ):
            blocked.add((domain, str(item["source_id"])))
        if domain == "job" and not {
            str(parent.get("domain")) for parent in item.get("parent_keys", [])
        }.issuperset({"customer", "service_location"}):
            blocked.add((domain, str(item["source_id"])))
    changed = True
    while changed:
        changed = False
        for item in records:
            key = (str(item["domain"]), str(item["source_id"]))
            if str(item.get("disposition", "")).upper() not in {"CREATE", "UPDATE", "REPLAY"}:
                continue
            if any((str(parent["domain"]), str(parent["source_id"])) in blocked for parent in item.get("parent_keys", [])) and key not in blocked:
                blocked.add(key)
                changed = True
    held_by_key = {key: candidate_by_key.get(key) for key in blocked}
    for item in records:
        key = (str(item["domain"]), str(item["source_id"]))
        if key not in blocked or str(item.get("disposition", "")).upper() not in {"CREATE", "UPDATE", "REPLAY"}:
            continue
        original = str(item["disposition"]).upper()
        candidate = held_by_key[key]
        item["discrepancy_evidence"] = {
            "source_payload": item.get("payload", {}),
            "source_disposition": original,
            "source_digest": item.get("source_digest"),
            "binding_disposition": candidate.disposition.value if candidate else "HELD_PARENT",
            "binding_reason": candidate.reason if candidate else "dependent_on_held_parent",
        }
        item["source_disposition"] = original
        item["payload"] = {}
        item["disposition"] = "HOLD"
        item["assertion"] = "hold"
        item["reason"] = "native_successor_binding_unresolved"
    packet = json.loads(json.dumps({
        "contract": envelope.packet.packet_contract if hasattr(envelope.packet, "packet_contract") else "hcp-november-preview-execution-packet/v1",
        "qualification_digest": envelope.packet.qualification_digest,
        "bundle_sha256": envelope.packet.bundle_sha256,
        "policy_digest": envelope.packet.policy_digest,
        "reconciliation_digest": envelope.packet.reconciliation_digest,
        "company_id": envelope.packet.company_id,
        "branch_id": envelope.packet.branch_id,
        "actor_id": envelope.packet.actor_id,
        "provider_company_id": envelope.packet.provider_company_id,
        "schema_head": envelope.packet.schema_head,
        "environment": envelope.packet.environment,
        "records": records,
        "acquired_at": envelope.packet.overlay_manifest.acquired_at,
    }))
    packet["source_packet_digest"] = envelope.packet.digest
    packet["source_packet_sha256"] = sha256(envelope.source_packet_path)
    packet["digest"] = digest(packet_payload(packet))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    packet_path = args.output_dir / "runtime-binding-quarantined-packet.json"
    write_private(packet_path, packet)
    inv = packet_inventory(records)
    new_package_digest = digest({"contract": "hcp-runtime-binding-quarantine/v1", "source": envelope.packet.digest, "packet": packet["digest"]})
    old_envelope = json.loads(envelope.source_packet_path.parent.joinpath("runtime-bound-hcp-execution-envelope.json").read_text()) if False else json.loads(args.authority_file.parent.joinpath("runtime-bound-hcp-execution-envelope.json").read_text())
    new_envelope = dict(old_envelope)
    new_envelope.update({"source_packet_path": str(packet_path), "source_packet_sha256": sha256(packet_path), "source_packet_digest": packet["digest"], "packet_counts": inv["counts"], "total_held": inv["total_held"], "executable_count": inv["executable_count"], "held_parent_executable_edges": inv["held_parent_executable_edges"], "repository_sha": authority.expected_repository_sha, "schema_head": authority.expected_schema_head})
    new_envelope["authority_digest"] = digest(envelope_payload(new_envelope))
    envelope_path = args.output_dir / "runtime-binding-quarantined-envelope.json"
    write_private(envelope_path, new_envelope)
    new_authority = json.loads(args.authority_file.read_text())
    new_authority.update({"execution_packet_path": str(envelope_path), "execution_packet_sha256": sha256(envelope_path), "execution_packet_digest": new_envelope["authority_digest"], "runtime_package_digest": new_package_digest})
    authority_path = args.output_dir / "runtime-binding-quarantined-authority.json"
    write_private(authority_path, new_authority)
    print(json.dumps({"authority": str(authority_path), "blocked_initial": len(candidate_by_key) - sum(c.disposition in {BindingDisposition.BINDING_ALREADY_PRESENT, BindingDisposition.PROVABLE_NATIVE_SUCCESSOR_BINDING} for c in candidates), "held_total": len(blocked), "counts": inv, "runtime_package_digest": new_package_digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
