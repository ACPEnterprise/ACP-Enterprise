"""Seal the bounded HCP/QBO accountant exception packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Final

from app.operational_migration.hcp_financial_reconciliation_readiness import (
    build_financial_reconciliation_readiness,
)

CONTRACT: Final = "hcp-qbo-accountant-reconciliation-packet/v1"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def build_packet(*, source_root: Path, qbo_controls_root: Path) -> dict[str, Any]:
    readiness = build_financial_reconciliation_readiness(
        source_root=source_root,
        qbo_controls_root=qbo_controls_root,
    )
    readiness.verify()
    packet: dict[str, Any] = {
        "contract": CONTRACT,
        "readiness_contract": readiness.contract,
        "readiness_digest": readiness.digest,
        "source_manifest_sha256": readiness.source_manifest_sha256,
        "ar_control_sha256": readiness.ar_control_sha256,
        "accountant_exceptions": readiness.accountant_exceptions,
        "ar_readiness": readiness.ar_readiness,
        "may_report_evidence": readiness.may_report_evidence,
        "authority": readiness.authority,
        "instructions": {
            "review_scope": "exceptions_only",
            "mechanically_proven_rows_excluded": True,
            "mutation_authority": "none",
            "accounting_posting_authorized": False,
            "weak_field_matching_permitted": False,
        },
    }
    packet["digest"] = hashlib.sha256(_canonical_bytes(packet)).hexdigest()
    return packet


def write_packet(*, packet: dict[str, Any], output: Path) -> str:
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.parent.chmod(0o700)
    payload = _canonical_bytes(packet)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    output.chmod(0o600)
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--qbo-controls-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    packet = build_packet(
        source_root=args.source_root,
        qbo_controls_root=args.qbo_controls_root,
    )
    file_sha256 = write_packet(packet=packet, output=args.output)
    print(json.dumps({"digest": packet["digest"], "file_sha256": file_sha256}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
