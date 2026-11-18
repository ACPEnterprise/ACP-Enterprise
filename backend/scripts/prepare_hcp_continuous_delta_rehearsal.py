"""Validate a sealed operational gate and prepare its clone-only delta packet."""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

from app.operational_migration.hcp_continuous_delta import (
    NativeObservation,
    ProviderObservation,
    build_continuous_delta,
)
from app.operational_migration.hcp_current_overlay import OverlayKey
from app.operational_migration.hcp_operational_gate import (
    canonical_digest,
    file_sha256,
    load_object,
    require_private_file,
    required_operational_holds,
    validate_final_policy,
    validate_gate_packet,
    verify_document_digest,
)

DEFAULT_WORKFORCE_AUTHORITY = (
    Path(__file__).resolve().parents[1]
    / "app/operational_migration/authorities/hcp-workforce-source-authority.v1.json"
)


def _write_once(root: Path, name: str, value: object) -> Path:
    path = root / name
    body = (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False).encode() + b"\n"
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as target:
        target.write(body)
    return path


def _native(path: Path) -> tuple[dict[OverlayKey, NativeObservation], str]:
    require_private_file(path)
    value = load_object(path)
    declared = value.get("digest")
    digest = (
        verify_document_digest(value, "isolated clone native observations")
        if declared
        else canonical_digest(value)
    )
    records: dict[OverlayKey, NativeObservation] = {}
    for row in value.get("records", []):
        if not isinstance(row, dict):
            raise TypeError("native observation row is invalid")
        key = OverlayKey(str(row.get("domain")), str(row.get("source_id")))
        if key in records or not key.domain or not key.source_id:
            raise ValueError("native observation identities are duplicate/invalid")
        records[key] = NativeObservation(
            source_digest=row["source_digest"],
            source_applied_at=row["source_applied_at"],
            native_updated_at=row["native_updated_at"],
        )
    return records, digest


def _provider(path: Path) -> tuple[dict[str, Any], tuple[ProviderObservation, ...]]:
    require_private_file(path)
    value = load_object(path)
    verify_document_digest(value, "provider observations")
    records = tuple(
        ProviderObservation(
            domain=row["domain"],
            source_id=row["source_id"],
            source_digest=row["source_digest"],
            acquired_at=row["acquired_at"],
            source_updated_at=row.get("source_updated_at"),
            payload=row["payload"],
            parent_keys=tuple(OverlayKey(**parent) for parent in row["parent_keys"]),
            native_fingerprint=row.get("native_fingerprint"),
        )
        for row in value["records"]
    )
    return value, records


def _plan_value(plan: Any) -> dict[str, Any]:
    return {
        "contract": plan.contract,
        "cutoff": plan.cutoff,
        "digest": plan.digest,
        "decisions": [
            {
                "domain": row.key.domain,
                "source_id": row.key.source_id,
                "disposition": row.disposition.value,
                "reason": row.reason,
                "before_digest": row.before_digest,
                "after_digest": row.after_digest,
            }
            for row in plan.decisions
        ],
        "overlay_manifest_digest": plan.manifest.digest if plan.manifest else None,
    }


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    report, technicians = validate_gate_packet(
        args.gate_packet,
        workforce_authority_path=args.workforce_authority,
        final_policy_path=args.final_policy,
    )
    gate = load_object(args.gate_packet)
    provider_value, provider = _provider(Path(gate["provider_observations"]))
    final_policy, final_policy_digest = validate_final_policy(
        args.final_policy,
        gate=gate,
        gate_digest=report["gate_digest"],
    )
    required_holds = {
        OverlayKey(domain, source_id): reason
        for (domain, source_id), reason in required_operational_holds(
            gate=gate,
            provider=provider_value,
            final_policy=final_policy,
        ).items()
    }
    native, native_digest = _native(args.native_observations)
    provider_keys = {item.key for item in provider}
    unexpected_native = sorted(set(native) - provider_keys)
    if unexpected_native:
        key = unexpected_native[0]
        raise ValueError(
            f"native observation is outside provider scope: {key.domain}:{key.source_id}"
        )
    plan = build_continuous_delta(
        cutoff=args.cutoff,
        base_source4_digest=args.base_source4_digest,
        company_id=args.company_id,
        branch_id=args.branch_id,
        acquired_at=provider_value["acquired_at"],
        provider=provider,
        native=native,
        required_holds=required_holds,
    )
    if plan.manifest is None:
        raise ValueError("continuous delta contains no executable/held assertions")

    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(args.output, 0o700)
    validation_path = _write_once(args.output, "gate-validation.json", report)
    technician_path = _write_once(
        args.output, "technician-identity-dispositions.json", technicians
    )
    plan_value = _plan_value(plan)
    plan_path = _write_once(args.output, "continuous-delta-plan.json", plan_value)
    overlay_path = _write_once(
        args.output, "continuous-delta-overlay.json", plan.manifest.private_payload()
    )
    decision_counts: dict[str, int] = {}
    for row in plan.decisions:
        decision_counts[row.disposition.value] = (
            decision_counts.get(row.disposition.value, 0) + 1
        )
    manifest: dict[str, Any] = {
        "contract": "hcp-isolated-clone-continuous-delta-rehearsal/v1",
        "state": "PREPARED_FOR_ISOLATED_CLONE_REHEARSAL",
        "gate_packet": str(args.gate_packet.resolve()),
        "gate_digest": report["gate_digest"],
        "native_observations": str(args.native_observations.resolve()),
        "native_observations_digest": native_digest,
        "provider_observations_digest": report["provider_observations_digest"],
        "final_policy": str(args.final_policy.resolve()),
        "final_policy_digest": final_policy_digest,
        "required_operational_hold_count": len(required_holds),
        "operational_hold_set_digest": report["operational_hold_set_digest"],
        "base_source4_digest": args.base_source4_digest,
        "cutoff": args.cutoff,
        "company_id": args.company_id,
        "branch_id": args.branch_id,
        "delta_plan": str(plan_path.resolve()),
        "delta_plan_digest": plan.digest,
        "overlay": str(overlay_path.resolve()),
        "overlay_file_sha256": file_sha256(overlay_path),
        "overlay_manifest_digest": plan.manifest.digest,
        "validation": str(validation_path.resolve()),
        "technician_dispositions": str(technician_path.resolve()),
        "technician_disposition_digest": technicians["digest"],
        "decision_counts": dict(sorted(decision_counts.items())),
        "rehearsal_requirements": [
            "fresh clone backup and verified restore receipt",
            "mode-0600 clone execution authority",
            "TARGET_ENVIRONMENT=migration_rehearsal",
            "PREVIEW_ACCESS_ENABLED=false",
            "PRODUCTION_ACCESS_ENABLED=false",
            "loopback acp_hcp_rehearsal_import database only",
        ],
    }
    manifest["digest"] = canonical_digest(manifest)
    _write_once(args.output, "rehearsal-manifest.json", manifest)
    return manifest


def validate(args: argparse.Namespace) -> dict[str, Any]:
    report, technicians = validate_gate_packet(
        args.gate_packet,
        workforce_authority_path=args.workforce_authority,
        final_policy_path=args.final_policy,
    )
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.chmod(args.output, 0o700)
    _write_once(args.output, "gate-validation.json", report)
    _write_once(args.output, "technician-identity-dispositions.json", technicians)
    return {
        "status": report["status"],
        "gate_digest": report["gate_digest"],
        "counts": report["counts"],
        "technician_totals": technicians["totals"],
        "technician_disposition_digest": technicians["digest"],
        "final_policy_digest": report["final_policy_digest"],
        "operational_hold_count_with_parent_cascade": report[
            "operational_hold_count_with_parent_cascade"
        ],
    }


def authority(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_object(args.rehearsal_manifest)
    manifest_digest = verify_document_digest(manifest, "rehearsal manifest")
    validation_path = Path(manifest["validation"])
    native_path = Path(manifest["native_observations"])
    overlay_path = Path(manifest["overlay"])
    final_policy_path = Path(manifest["final_policy"])
    for path in (
        args.rehearsal_manifest,
        validation_path,
        native_path,
        overlay_path,
        final_policy_path,
        args.backup,
        args.restore_receipt,
    ):
        require_private_file(path)
    validation = load_object(validation_path)
    native = load_object(native_path)
    final_policy = load_object(final_policy_path)
    validation_digest = verify_document_digest(validation, "gate validation")
    native_digest = (
        verify_document_digest(native, "native observations")
        if native.get("digest")
        else canonical_digest(native)
    )
    final_policy_digest = verify_document_digest(
        final_policy, "final operational policy"
    )
    if final_policy_digest != manifest.get("final_policy_digest"):
        raise ValueError("rehearsal final-policy lineage mismatch")
    backup_digest = file_sha256(args.backup)
    restore_digest = file_sha256(args.restore_receipt)
    repository_sha = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    idempotency = canonical_digest(
        {
            "contract": "hcp-isolated-clone-continuous-delta-execution/v1",
            "overlay": manifest["overlay_manifest_digest"],
            "backup": backup_digest,
            "company": manifest["company_id"],
            "branch": manifest["branch_id"],
        }
    )
    value = {
        "contract": "hcp-isolated-clone-continuous-delta-execution/v1",
        "expected_repository_sha": repository_sha,
        "expected_schema_head": args.expected_schema_head,
        "expected_database": "acp_hcp_rehearsal_import",
        "company_id": manifest["company_id"],
        "branch_id": manifest["branch_id"],
        "actor_id": args.actor_id,
        "base_source4_digest": manifest["base_source4_digest"],
        "overlay_path": str(overlay_path.resolve()),
        "overlay_file_sha256": file_sha256(overlay_path),
        "overlay_manifest_digest": manifest["overlay_manifest_digest"],
        "gate_validation_path": str(validation_path.resolve()),
        "gate_validation_digest": validation_digest,
        "native_observations_path": str(native_path.resolve()),
        "native_observations_digest": native_digest,
        "final_policy_path": str(final_policy_path.resolve()),
        "final_policy_digest": final_policy_digest,
        "rehearsal_manifest_path": str(args.rehearsal_manifest.resolve()),
        "rehearsal_manifest_digest": manifest_digest,
        "backup_path": str(args.backup.resolve()),
        "backup_digest": backup_digest,
        "restore_receipt_path": str(args.restore_receipt.resolve()),
        "restore_receipt_digest": restore_digest,
        "idempotency_identity": idempotency,
    }
    if (
        not args.output.parent.is_dir()
        or stat.S_IMODE(args.output.parent.stat().st_mode) != 0o700
    ):
        raise ValueError(
            "authority output parent must be an existing mode-0700 directory"
        )
    body = json.dumps(value, sort_keys=True, indent=2).encode() + b"\n"
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as target:
        target.write(body)
    return {
        "status": "AUTHORITY_PREPARED",
        "authority": str(args.output.resolve()),
        "authority_file_sha256": file_sha256(args.output),
        "idempotency_identity": idempotency,
        "repository_sha": repository_sha,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    gate = commands.add_parser("validate-gate")
    gate.add_argument("--gate-packet", required=True, type=Path)
    gate.add_argument("--final-policy", required=True, type=Path)
    gate.add_argument(
        "--workforce-authority", type=Path, default=DEFAULT_WORKFORCE_AUTHORITY
    )
    gate.add_argument("--output", required=True, type=Path)
    delta = commands.add_parser("consume-native")
    delta.add_argument("--gate-packet", required=True, type=Path)
    delta.add_argument("--final-policy", required=True, type=Path)
    delta.add_argument("--native-observations", required=True, type=Path)
    delta.add_argument("--cutoff", required=True)
    delta.add_argument("--base-source4-digest", required=True)
    delta.add_argument("--company-id", required=True)
    delta.add_argument("--branch-id", required=True)
    delta.add_argument(
        "--workforce-authority", type=Path, default=DEFAULT_WORKFORCE_AUTHORITY
    )
    delta.add_argument("--output", required=True, type=Path)
    auth = commands.add_parser("prepare-authority")
    auth.add_argument("--rehearsal-manifest", required=True, type=Path)
    auth.add_argument("--backup", required=True, type=Path)
    auth.add_argument("--restore-receipt", required=True, type=Path)
    auth.add_argument("--expected-schema-head", required=True)
    auth.add_argument("--actor-id", required=True)
    auth.add_argument("--output", required=True, type=Path)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.command == "validate-gate":
        value = validate(args)
    elif args.command == "consume-native":
        value = prepare(args)
    else:
        value = authority(args)
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
