"""Emit a value-free Payroll capability inventory for a sealed QBO snapshot."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path

from app.payroll.qbo_employee_input_migration import classify_accounting_catalog
from app.qbo_source.bounded_evidence import (
    BoundedEvidenceError,
    latest_bounded_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", required=True, type=Path)
    arguments = parser.parse_args()
    try:
        packet = latest_bounded_evidence(arguments.evidence_root)
    except BoundedEvidenceError as error:
        print(json.dumps({"state": "BLOCKED", "reason": str(error)}, sort_keys=True))
        return 2
    if packet is None:
        print(
            json.dumps(
                {"state": "BLOCKED", "reason": "sealed_snapshot_unavailable"},
                sort_keys=True,
            )
        )
        return 2
    counts = packet.manifest.get("entity_counts")
    if not isinstance(counts, dict) or any(
        not isinstance(key, str) or not isinstance(value, int) or value < 0
        for key, value in counts.items()
    ):
        print(
            json.dumps(
                {"state": "BLOCKED", "reason": "entity_counts_invalid"},
                sort_keys=True,
            )
        )
        return 2
    snapshot = packet.manifest.get("snapshot")
    classification = classify_accounting_catalog(entity_counts=counts)
    print(
        json.dumps(
            {
                "contract_version": "payroll.qbo-employee-input-inventory.v1",
                "state": "COMPLETE",
                "source_manifest_sha256": packet.manifest_sha256,
                "snapshot_environment": snapshot.get("environment")
                if isinstance(snapshot, Mapping)
                else None,
                "acquisition_state": packet.manifest.get("state"),
                "entity_counts": counts,
                "fields": [
                    {
                        "field": item.field,
                        "classification": item.classification.value,
                    }
                    for item in classification
                ],
                "limitations": [
                    "values_and_employee_identifiers_not_emitted",
                    "catalog_presence_does_not_create_payroll_authority",
                    "missing_values_are_not_zero",
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
