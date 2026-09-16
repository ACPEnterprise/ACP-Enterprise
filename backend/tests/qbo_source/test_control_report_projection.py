from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from zipfile import ZipFile

import pytest

from app.qbo_source.control_report_projection import (
    discover_registered_control_reports,
    project_registered_general_ledger_period,
)
from app.qbo_source.evidence import EvidenceStoreError


def _evidence(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "evidence"
    raw_root = root / "controls" / "raw"
    raw_root.mkdir(parents=True)
    workbook = tmp_path / "ledger.xlsx"
    shared = (
        "General Ledger",
        "Distribution account",
        "Transaction date",
        "Transaction type",
        "Num",
        "Name",
        "Amount",
        "Sales",
        "Invoice",
        "100",
        "Customer A",
        "Payment",
        "Customer B",
    )
    strings = "".join(f"<si><t>{value}</t></si>" for value in shared)
    rows = (
        '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
        '<row r="2"><c r="B2" t="s"><v>1</v></c><c r="C2" t="s"><v>2</v></c>'
        '<c r="D2" t="s"><v>3</v></c><c r="E2" t="s"><v>4</v></c>'
        '<c r="F2" t="s"><v>5</v></c><c r="I2" t="s"><v>6</v></c></row>'
        '<row r="3"><c r="B3" t="s"><v>7</v></c>'
        '<c r="C3" t="inlineStr"><is><t>05/01/2026</t></is></c>'
        '<c r="D3" t="s"><v>8</v></c><c r="E3" t="s"><v>9</v></c>'
        '<c r="F3" t="s"><v>10</v></c><c r="I3"><v>125.50</v></c></row>'
        '<row r="4"><c r="B4" t="s"><v>7</v></c>'
        '<c r="C4" t="inlineStr"><is><t>05/31/2026</t></is></c>'
        '<c r="D4" t="s"><v>11</v></c><c r="F4" t="s"><v>12</v></c><c r="I4"><v>-25.50</v></c></row>'
        '<row r="5"><c r="B5" t="s"><v>7</v></c>'
        '<c r="C5" t="inlineStr"><is><t>06/01/2026</t></is></c>'
        '<c r="D5" t="s"><v>8</v></c><c r="I5"><v>10</v></c></row>'
    )
    with ZipFile(workbook, "w") as archive:
        archive.writestr(
            "xl/sharedStrings.xml",
            '<sst xmlns="http://schemas.openxmlformats.org/'
            f'spreadsheetml/2006/main">{strings}</sst>',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/'
            f'spreadsheetml/2006/main"><sheetData>{rows}</sheetData></worksheet>',
        )
    content = workbook.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    raw = raw_root / f"{digest}.xlsx"
    raw.write_bytes(content)
    registration = {
        "schema_version": "qbo-control-registration/v1",
        "control_id": "ledger-v1",
        "kind": "general_ledger",
        "raw_sha256": digest,
        "byte_size": len(content),
        "storage_reference": f"evidence://controls/raw/{digest}.xlsx",
        "report_end_date": "2026-08-31",
        "accounting_basis": "accrual",
        "generated_at": None,
        "safe_report_parameters": {"start_date": "2022-01-01", "end_date": "2026-08-31"},
    }
    (root / "controls" / "ledger-v1.json").write_text(json.dumps(registration))
    return root, raw


def test_discovers_and_projects_bounded_source_only_period(tmp_path: Path) -> None:
    root, _ = _evidence(tmp_path)
    reports = discover_registered_control_reports(evidence_root=root)
    assert len(reports) == 1
    result = project_registered_general_ledger_period(
        evidence_root=root, start_date=date(2026, 5, 1), end_date=date(2026, 5, 31)
    )
    assert result["ledger_row_count"] == 2
    assert result["transaction_type_counts"] == {"Invoice": 1, "Payment": 1}
    assert result["source_reported_row_amount_sum"] == "100.00"
    assert result["accepted_as_acp_accounting"] is False
    assert result["mutation_authority"] == "none"


def test_rejects_changed_raw_report(tmp_path: Path) -> None:
    root, raw = _evidence(tmp_path)
    raw.write_bytes(raw.read_bytes() + b"changed")
    with pytest.raises(EvidenceStoreError, match="size_mismatch"):
        discover_registered_control_reports(evidence_root=root)
