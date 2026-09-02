"""Sanctioned protected ingestion for owner-supplied QBO control reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .evidence import (
    ControlEvidenceRegistration,
    ControlEvidenceRegistry,
    ControlReportKind,
    EvidenceStoreError,
    ProtectedFilesystemEvidenceStore,
)

MAX_CONTROL_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True)
class RegisterControlReport:
    source_file: Path
    control_id: str
    kind: ControlReportKind
    basis: str
    start_date: date
    end_date: date


def register_control_report(
    *,
    command: RegisterControlReport,
    evidence_root: Path,
    repository_root: Path,
) -> dict[str, object]:
    if command.kind is ControlReportKind.AUDIT_LOG:
        if command.basis != "operational":
            raise EvidenceStoreError("audit_control_basis_invalid")
    elif command.basis not in {"cash", "accrual", "operational"}:
        raise EvidenceStoreError("control_basis_invalid")
    source = command.source_file.expanduser()
    if source.is_symlink() or not source.is_file():
        raise EvidenceStoreError("control_source_must_be_regular_file")
    resolved = source.resolve(strict=True)
    repository = repository_root.expanduser().resolve(strict=True)
    if resolved == repository or repository in resolved.parents:
        raise EvidenceStoreError("control_source_inside_repository")
    source_stat = resolved.stat()
    if source_stat.st_uid != os.getuid():
        raise EvidenceStoreError("control_source_owner_mismatch")
    if stat.S_IMODE(source_stat.st_mode) & 0o077:
        raise EvidenceStoreError("control_source_permissions_too_open")
    if source_stat.st_size < 1 or source_stat.st_size > MAX_CONTROL_BYTES:
        raise EvidenceStoreError("control_source_size_invalid")
    suffix = resolved.suffix.lower()
    expected_suffix = ".csv" if command.kind is ControlReportKind.AUDIT_LOG else ".xlsx"
    if suffix != expected_suffix:
        raise EvidenceStoreError("control_source_format_invalid")
    with resolved.open("rb") as source_handle:
        prefix = source_handle.read(4)
        if expected_suffix == ".xlsx" and prefix != b"PK\x03\x04":
            raise EvidenceStoreError("control_source_format_invalid")
        if expected_suffix == ".csv" and b"\x00" in prefix:
            raise EvidenceStoreError("control_source_format_invalid")
        source_handle.seek(0)
        content = source_handle.read()
        digest = hashlib.sha256(content).hexdigest()

    store = ProtectedFilesystemEvidenceStore(
        root=evidence_root, repository_root=repository
    )
    raw_root = store.root / "controls" / "raw"
    raw_root.mkdir(mode=0o700, exist_ok=True)
    os.chmod(raw_root, 0o700)
    target = raw_root / f"{digest}{expected_suffix}"
    store._store_named_immutable(target, content)
    registration_digest = ControlEvidenceRegistry(store).register(
        ControlEvidenceRegistration(
            control_id=command.control_id,
            kind=command.kind,
            raw_sha256=digest,
            byte_size=len(content),
            storage_reference=f"evidence://controls/raw/{digest}{expected_suffix}",
            report_end_date=command.end_date,
            accounting_basis=command.basis,
            generated_at=None,
            safe_report_parameters={
                "start_date": command.start_date.isoformat(),
                "end_date": command.end_date.isoformat(),
            },
        )
    )
    return {
        "state": "CONTROL_REPORT_REGISTERED",
        "control_id": command.control_id,
        "kind": command.kind.value,
        "basis": command.basis.lower(),
        "period": (
            command.start_date.isoformat(),
            command.end_date.isoformat(),
        ),
        "raw_sha256": digest,
        "byte_size": len(content),
        "registration_digest": registration_digest,
        "source_mutated": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Register an untouched QBO control report in protected custody"
    )
    parser.add_argument("--source-file", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--repository-root", required=True, type=Path)
    parser.add_argument("--control-id", required=True)
    parser.add_argument("--kind", required=True, choices=tuple(ControlReportKind))
    parser.add_argument(
        "--basis", required=True, choices=("cash", "accrual", "operational")
    )
    parser.add_argument("--start-date", required=True, type=date.fromisoformat)
    parser.add_argument("--end-date", required=True, type=date.fromisoformat)
    args = parser.parse_args()
    result = register_control_report(
        command=RegisterControlReport(
            source_file=args.source_file,
            control_id=args.control_id,
            kind=ControlReportKind(args.kind),
            basis=args.basis,
            start_date=args.start_date,
            end_date=args.end_date,
        ),
        evidence_root=args.evidence_root,
        repository_root=args.repository_root,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
