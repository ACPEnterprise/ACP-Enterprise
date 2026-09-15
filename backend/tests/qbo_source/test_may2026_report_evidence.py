from __future__ import annotations

import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile

import pytest

from app.qbo_source.accounting_evidence_projection import (
    project_latest_qbo_workspace,
)
from app.qbo_source.evidence import EvidenceStoreError
from app.qbo_source.may2026_report_evidence import (
    project_may_2026_source_report,
)


def _workbook(path: Path) -> bytes:
    values = [
        "All County Plumbing and Leak",
        "General Ledger",
        "Distribution account",
        "Transaction date",
        "Transaction type",
        "Num",
        "Name",
        "Amount",
        "Sales",
        "05/02/2026",
        "Invoice",
        "1001",
        "Customer A",
        "100.00",
        "Supplies & Material - COGS",
        "05/03/2026",
        "Expense",
        "E-1",
        "Vendor A",
        "20.00",
        "Software",
        "05/04/2026",
        "30.00",
        "Ask My Accountant",
        "05/05/2026",
        "5.00",
        "Checking",
        "05/06/2026",
        "Payment",
        "P-1",
        "Customer A",
        "99.00",
        "Sales of Product Income",
        "06/01/2026",
        "999.00",
    ]
    index = {value: position for position, value in enumerate(values)}

    def cell(column: str, row: int, value: str) -> str:
        return f'<c r="{column}{row}" t="s"><v>{index[value]}</v></c>'

    rows = [
        f'<row r="1">{cell("A", 1, values[0])}</row>',
        f'<row r="2">{cell("A", 2, values[1])}</row>',
        '<row r="3">'
        + "".join(cell(column, 3, value) for column, value in zip("ABCDEF", values[2:8]))
        + "</row>",
    ]
    data = [
        values[8:14],
        values[14:20],
        [values[20], values[21], values[16], "E-1", "Vendor A", values[22]],
        [values[23], values[24], values[16], "E-1", "Vendor A", values[25]],
        values[26:32],
        [values[32], values[33], values[10], values[11], values[12], values[34]],
    ]
    for number, record in enumerate(data, start=4):
        rows.append(
            f'<row r="{number}">'
            + "".join(cell(column, number, value) for column, value in zip("ABCDEF", record))
            + "</row>"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "xl/sharedStrings.xml",
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            + "".join(f"<si><t>{escape(value)}</t></si>" for value in values)
            + "</sst>",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            + "<sheetData>"
            + "".join(rows)
            + "</sheetData></worksheet>",
        )
    return path.read_bytes()


def _controls(tmp_path: Path) -> Path:
    root = tmp_path / "qbo-evidence"
    raw = _workbook(root / "staged.xlsx")
    digest = hashlib.sha256(raw).hexdigest()
    raw_path = root / "controls" / "raw" / f"{digest}.xlsx"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_bytes(raw)
    (root / "staged.xlsx").unlink()
    registration = {
        "schema_version": "qbo-control-registration/v1",
        "control_id": "general-ledger-v1",
        "kind": "general_ledger",
        "accounting_basis": "accrual",
        "report_end_date": "2026-08-31",
        "generated_at": None,
        "safe_report_parameters": {
            "start_date": "2022-01-01",
            "end_date": "2026-08-31",
        },
        "raw_sha256": digest,
    }
    (root / "controls" / "general-ledger.json").write_text(
        json.dumps(registration)
    )
    return root


def test_projects_may_accrual_report_without_promoting_accounting_truth(
    tmp_path: Path,
) -> None:
    report = project_may_2026_source_report(_controls(tmp_path))

    assert report is not None
    assert report["authority"] == "QBO_SOURCE_BACKED"
    assert report["accepted_as_acp_accounting"] is False
    assert report["values"] == {
        "revenue": "100.00",
        "cost_of_goods_sold": "20.00",
        "gross_profit": "80.00",
        "operating_expense": "30.00",
        "net_operating_income": "50.00",
        "other_income": "0.00",
        "other_expense": "5.00",
        "net_income": "45.00",
    }
    assert report["coverage"]["may_ledger_postings"] == 5
    assert report["coverage"]["classified_profit_loss_postings"] == 4
    assert report["coverage"]["excluded_non_profit_loss_postings"] == 1
    assert report["duplicate_boundary"]["hcp_amounts_composed"] is False
    assert report["mutation_authority"] == "none"


def test_report_only_fallback_is_accrual_and_never_relabelled_cash(
    tmp_path: Path,
) -> None:
    root = _controls(tmp_path)

    accrual = project_latest_qbo_workspace(evidence_root=root, basis="accrual")
    cash = project_latest_qbo_workspace(evidence_root=root, basis="cash")

    assert accrual["completeness"] == "report_only"
    assert accrual["reports"][0]["basis"] == "accrual"
    assert accrual["mutation_authority"] == "none"
    assert cash["mode"] == "blocked"
    assert cash["reports"] == []


def test_tampered_registered_workbook_fails_closed(tmp_path: Path) -> None:
    root = _controls(tmp_path)
    raw_path = next((root / "controls" / "raw").glob("*.xlsx"))
    raw_path.write_bytes(raw_path.read_bytes() + b"tampered")

    with pytest.raises(EvidenceStoreError, match="digest_mismatch"):
        project_may_2026_source_report(root)
