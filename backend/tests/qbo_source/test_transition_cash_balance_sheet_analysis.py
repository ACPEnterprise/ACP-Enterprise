from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from app.qbo_source.transition_cash_balance_sheet_analysis import _metrics


def test_cash_balance_sheet_balances_and_preserves_separate_controls(
    tmp_path: Path,
) -> None:
    workbook = tmp_path / "balance-sheet.xlsx"
    values = (
        "Balance Sheet",
        "As of Feb 19, 2024",
        "Total for Bank Accounts",
        "Total for Assets",
        "Total for Credit Cards",
        "Total for Liabilities",
        "Total for Equity",
        "Total for Liabilities and Equity",
    )
    strings = "".join(f"<si><t>{value}</t></si>" for value in values)
    rows = (
        '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
        '<row r="2"><c r="A2" t="s"><v>1</v></c></row>'
        + "".join(
            f'<row r="{index + 3}"><c r="A{index + 3}" t="s"><v>{index + 2}</v></c>'
            f'<c r="B{index + 3}"><v>{amount}</v></c></row>'
            for index, amount in enumerate(("10", "30", "-2", "20", "10", "30"))
        )
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
    assert result["assets"] == "30.00"
    assert result["liabilities_and_equity"] == "30.00"
    assert result["bank_accounts"] == "10.00"
    assert result["credit_cards"] == "-2.00"
