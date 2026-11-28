"""Build a human-readable workbook from verified QBO historical custody.

The workbook is an offline review artifact. It never calls QuickBooks and has
no accounting-posting authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, cast

import xlsxwriter  # type: ignore[import-untyped]
from app.qbo_source.historical_archive import (
    historical_archive_catalog,
    transaction_type_counts,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cell(value: object) -> str | int | float:
    if value is None:
        return ""
    if isinstance(value, (str, int, float)):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def build_workbook(*, archive_root: Path, output: Path) -> dict[str, object]:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing evidence: {output}")
    catalog = historical_archive_catalog(root=archive_root)
    catalog_datasets = cast(list[dict[str, object]], catalog["datasets"])
    catalog_exceptions = cast(list[dict[str, object]], catalog["exceptions"])
    reconciliation_controls = cast(
        dict[str, object], catalog["reconciliation_controls"]
    )
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(output, {"constant_memory": True})
    header = workbook.add_format({"bold": True, "bg_color": "#E7E6E6"})
    money = workbook.add_format({"num_format": "$#,##0.00;[Red]-$#,##0.00"})
    wrap = workbook.add_format({"text_wrap": True, "valign": "top"})

    summary = workbook.add_worksheet("Summary")
    summary.set_column("A:A", 34)
    summary.set_column("B:B", 76)
    summary.write_row(0, 0, ["Control", "Verified value"], header)
    controls = (
        ("Source company", catalog["source_company"]),
        ("Source cutoff", catalog["source_cutoff"]),
        ("Historical basis", catalog["historical_basis"]),
        ("Currency", catalog["currency"]),
        ("API source population", catalog["source_record_count"]),
        ("Relationship identities", catalog["relationship_identity_count"]),
        ("Sealed custody datasets", len(catalog_datasets)),
        ("Disclosed exceptions", catalog["exception_count"]),
        ("Custody set SHA-256", catalog["custody_set_sha256"]),
        ("Mutation authority", catalog["mutation_authority"]),
        (
            "Acceptance state",
            "REQUIRES FINANCE AND OWNER DISPOSITION; no source record was posted",
        ),
    )
    for row, control_values in enumerate(controls, 1):
        summary.write_row(row, 0, control_values)

    exceptions = workbook.add_worksheet("Exceptions")
    exception_columns = [
        "id",
        "classification",
        "description",
        "count",
        "count_difference",
        "dollar_difference",
        "total",
        "gross_difference",
        "net_difference",
        "next_action",
        "owner_disposition",
    ]
    exceptions.set_column("A:B", 30)
    exceptions.set_column("C:C", 72, wrap)
    exceptions.set_column("D:I", 20)
    exceptions.set_column("J:K", 72, wrap)
    exceptions.write_row(0, 0, exception_columns, header)
    for row, item in enumerate(catalog_exceptions, 1):
        exception_values = [
            item.get(column, "") for column in exception_columns[:-1]
        ] + [""]
        exceptions.write_row(row, 0, [_cell(value) for value in exception_values])
        for column in range(5, 9):
            value = exception_values[column]
            if value not in {None, ""}:
                try:
                    exceptions.write_number(row, column, float(str(value)), money)
                except ValueError:
                    pass

    datasets = workbook.add_worksheet("Source populations")
    dataset_columns = [
        "key",
        "label",
        "category",
        "record_count",
        "starts_on",
        "ends_on",
        "source_file",
        "source_sha256",
        "source_bytes",
    ]
    datasets.set_column("A:C", 28)
    datasets.set_column("D:F", 16)
    datasets.set_column("G:G", 70)
    datasets.set_column("H:H", 68)
    datasets.write_row(0, 0, dataset_columns, header)
    for row, item in enumerate(catalog_datasets, 1):
        datasets.write_row(
            row, 0, [_cell(item.get(column)) for column in dataset_columns]
        )

    reconciliation = workbook.add_worksheet("Reconciliation controls")
    reconciliation.set_column("A:A", 46)
    reconciliation.set_column("B:B", 80)
    reconciliation.write_row(0, 0, ["Control", "Verified source value"], header)
    flat_controls: list[tuple[str, Any]] = []
    for group, reconciliation_value in reconciliation_controls.items():
        if isinstance(reconciliation_value, dict):
            flat_controls.extend(
                (f"{group}.{key}", value) for key, value in reconciliation_value.items()
            )
        else:
            flat_controls.append((str(group), reconciliation_value))
    for row, control_values in enumerate(flat_controls, 1):
        reconciliation.write_row(row, 0, [_cell(value) for value in control_values])

    types = workbook.add_worksheet("GL transaction populations")
    types.write_row(0, 0, ["Transaction type", "Record count"], header)
    for row, type_values in enumerate(
        transaction_type_counts(root=archive_root).items(), 1
    ):
        types.write_row(row, 0, type_values)

    workbook.close()
    os.chmod(output, 0o600)
    receipt = {
        "contract": "qbo-historical-exception-workbook-receipt/v1",
        "workbook": output.name,
        "workbook_sha256": _sha256(output),
        "workbook_bytes": output.stat().st_size,
        "source_custody_set_sha256": catalog["custody_set_sha256"],
        "source_dataset_count": len(catalog_datasets),
        "exception_count": catalog["exception_count"],
        "mutation_authority": "none",
    }
    receipt_path = output.with_suffix(output.suffix + ".receipt.json")
    descriptor = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            build_workbook(archive_root=args.archive_root, output=args.output),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
