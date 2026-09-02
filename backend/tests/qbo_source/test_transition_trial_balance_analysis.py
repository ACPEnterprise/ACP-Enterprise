from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

from app.qbo_source.transition_trial_balance_analysis import _metrics


def test_transition_trial_balance_is_balanced_without_opening_equity(
    tmp_path: Path,
) -> None:
    workbook = tmp_path / "trial-balance.xlsx"
    shared = (
        "Trial Balance",
        "As of Feb 19, 2024",
        "Account Name",
        "Debit",
        "Credit",
        "Synthetic Cash",
        "Synthetic Equity",
    )
    strings = "".join(f"<si><t>{value}</t></si>" for value in shared)
    rows = (
        '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
        '<row r="2"><c r="A2" t="s"><v>1</v></c></row>'
        '<row r="3"><c r="A3" t="s"><v>2</v></c>'
        '<c r="B3" t="s"><v>3</v></c><c r="C3" t="s"><v>4</v></c></row>'
        '<row r="4"><c r="A4" t="s"><v>5</v></c>'
        '<c r="B4"><v>10.001</v></c></row>'
        '<row r="5"><c r="A5" t="s"><v>6</v></c>'
        '<c r="C5"><v>10.001</v></c></row>'
    )
    with ZipFile(workbook, "w") as archive:
        archive.writestr(
            "xl/sharedStrings.xml",
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"{strings}</sst>",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main">'
            f"<sheetData>{rows}</sheetData></worksheet>",
        )
    result = _metrics(workbook)
    assert Decimal(str(result["debit_total"])) == Decimal("10.00")
    assert result["debit_total"] == result["credit_total"]
    assert result["opening_balance_equity_rows"] == 0
