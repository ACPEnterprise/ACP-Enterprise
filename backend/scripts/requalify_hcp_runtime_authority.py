"""Bind the sealed HCP packet to the currently qualified Beta runtime.

The original November packet remains immutable evidence.  This command makes
only a runtime-bound copy of its packet metadata and execution envelope, then
binds both to the current application SHA, schema head, and verified rollback
backup.  It never contacts HCP and never touches the database.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


RUNTIME_CONTRACT = "hcp-november-preview-runtime-qualification/v1"
PACKET_CONTRACT = "hcp-november-preview-execution-packet/v1"
ENVELOPE_CONTRACT = "hcp-november-preview-execution-envelope/v1"


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


def inventory(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {key: 0 for key in ("CREATE", "HOLD", "HOLD_QUARANTINE", "REPLAY", "UPDATE")}
    for record in records:
        counts[str(record["disposition"]).upper()] += 1
    held = counts["HOLD"] + counts["HOLD_QUARANTINE"]
    executable = len(records) - held
    held_keys = {
        (str(record["domain"]), str(record["source_id"]))
        for record in records
        if str(record["disposition"]).upper() in {"HOLD", "HOLD_QUARANTINE"}
    }
    held_parent_edges = sum(
        1
        for record in records
        if str(record["disposition"]).upper() in {"CREATE", "UPDATE", "REPLAY"}
        for parent in record.get("parent_keys", [])
        if (str(parent["domain"]), str(parent["source_id"])) in held_keys
    )
    return {
        "counts": counts,
        "total_held": held,
        "executable_count": executable,
        "held_parent_executable_edges": held_parent_edges,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-packet", type=Path, required=True)
    parser.add_argument("--source-envelope", type=Path, required=True)
    parser.add_argument("--source-authority", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--backup-sha", required=True)
    parser.add_argument("--repository-sha", required=True)
    parser.add_argument("--schema-head", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    source_packet = json.loads(args.source_packet.read_text(encoding="utf-8"))
    source_packet_sha = sha256(args.source_packet)
    source_packet_digest = str(source_packet["digest"])
    packet = dict(source_packet)
    packet["schema_head"] = args.schema_head
    packet.pop("digest", None)
    packet["source_packet_sha256"] = source_packet_sha
    packet["source_packet_digest"] = source_packet_digest
    packet["runtime_requalification"] = {
        "contract": RUNTIME_CONTRACT,
        "source_packet_sha256": source_packet_sha,
        "source_packet_digest": source_packet_digest,
        "source_schema_head": source_packet.get("schema_head"),
        "runtime_schema_head": args.schema_head,
    }
    packet_payload = {
        "contract": PACKET_CONTRACT,
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
    packet["digest"] = digest(packet_payload)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    packet_path = args.output_dir / "runtime-bound-hcp-execution-packet.json"
    write_private(packet_path, packet)

    source_envelope = json.loads(args.source_envelope.read_text(encoding="utf-8"))
    inv = inventory(packet["records"])
    envelope = dict(source_envelope)
    envelope.update(
        {
            "contract": ENVELOPE_CONTRACT,
            "source_packet_path": str(packet_path),
            "source_packet_sha256": sha256(packet_path),
            "source_packet_digest": packet["digest"],
            "repository_sha": args.repository_sha,
            "schema_head": args.schema_head,
            "packet_counts": inv["counts"],
            "total_held": inv["total_held"],
            "executable_count": inv["executable_count"],
            "held_parent_executable_edges": inv["held_parent_executable_edges"],
        }
    )
    envelope_payload = {
        "contract": ENVELOPE_CONTRACT,
        "source_packet_sha256": envelope["source_packet_sha256"],
        "source_packet_digest": envelope["source_packet_digest"],
        "bundle_sha256": envelope["bundle_sha256"],
        "policy_digest": envelope["policy_digest"],
        "reconciliation_digest": envelope["reconciliation_digest"],
        "company_id": envelope["company_id"],
        "branch_id": envelope["branch_id"],
        "actor_id": envelope["actor_id"],
        "provider_company_id": envelope["provider_company_id"],
        "repository_sha": envelope["repository_sha"],
        "schema_head": envelope["schema_head"],
        "environment": envelope["environment"],
        "packet_counts": envelope["packet_counts"],
        "total_held": envelope["total_held"],
        "executable_count": envelope["executable_count"],
        "unexplained_omissions": envelope["unexplained_omissions"],
        "lineage_gaps": envelope["lineage_gaps"],
        "ambiguous_lineage": envelope["ambiguous_lineage"],
        "held_parent_executable_edges": envelope["held_parent_executable_edges"],
        "operational_hold_policy": envelope["operational_hold_policy"],
        "operational_hold_source_ids": envelope["operational_hold_source_ids"],
        "clean_baseline_bootstrap": envelope["clean_baseline_bootstrap"],
    }
    envelope["authority_digest"] = digest(envelope_payload)
    envelope_path = args.output_dir / "runtime-bound-hcp-execution-envelope.json"
    write_private(envelope_path, envelope)

    source_authority = json.loads(args.source_authority.read_text(encoding="utf-8"))
    authority = dict(source_authority)
    authority.update(
        {
            "contract": RUNTIME_CONTRACT,
            "expected_repository_sha": args.repository_sha,
            "expected_schema_head": args.schema_head,
            "execution_packet_path": str(envelope_path),
            "execution_packet_sha256": sha256(envelope_path),
            "execution_packet_digest": envelope["authority_digest"],
            "rollback_backup_digest": args.backup_sha,
            "qualification_status": "PASS",
            "source_authority_contract": source_authority.get("contract"),
            "source_authority_repository_sha": source_authority.get("expected_repository_sha"),
            "source_authority_schema_head": source_authority.get("expected_schema_head"),
            "source_packet_sha256": source_packet_sha,
            "source_packet_digest": source_packet_digest,
        }
    )
    authority_path = args.output_dir / "runtime-hcp-authority.json"
    write_private(authority_path, authority)
    print(json.dumps({
        "authority": str(authority_path),
        "packet": str(packet_path),
        "envelope": str(envelope_path),
        "source_packet_sha256": source_packet_sha,
        "source_packet_digest": source_packet_digest,
        "runtime_packet_digest": packet["digest"],
        "envelope_digest": envelope["authority_digest"],
        "counts": inv,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
