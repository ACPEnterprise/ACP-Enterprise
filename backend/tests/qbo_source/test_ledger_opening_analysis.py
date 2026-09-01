from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from app.qbo_source.ledger_opening_analysis import _workbook_metrics


def test_ledger_metrics_distinguish_transfer_activity_from_opening(
    tmp_path: Path,
) -> None:
    workbook = tmp_path / "ledger.xlsx"
    shared = (
        "General Ledger", "July 7, 2021-December 31, 2022",
        "Transaction date", "Transaction type", "01/01/2022", "Transfer",
        "01/03/2022", "Deposit",
    )
    strings = "".join(f"<si><t>{value}</t></si>" for value in shared)
    rows = (
        '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
        '<row r="2"><c r="A2" t="s"><v>1</v></c></row>'
        '<row r="3"><c r="A3" t="s"><v>2</v></c>'
        '<c r="B3" t="s"><v>3</v></c></row>'
        '<row r="4"><c r="A4" t="s"><v>4</v></c>'
        '<c r="B4" t="s"><v>5</v></c></row>'
        '<row r="5"><c r="A5" t="s"><v>4</v></c>'
        '<c r="B5" t="s"><v>5</v></c></row>'
        '<row r="6"><c r="A6" t="s"><v>6</v></c>'
        '<c r="B6" t="s"><v>7</v></c></row>'
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
    result = _workbook_metrics(workbook)
    assert result["ledger_rows_2021"] == 0
    assert result["earliest_ledger_date"] == "2022-01-01"
    assert result["earliest_date_transfer_only"] is True
    assert result["first_non_transfer_date"] == "2022-01-03"
    assert result["explicit_opening_keyword_matches"] == 0
    assert result["basis_authority"] == "OWNER_SUPPLIED_EXPORT_SETTING"
