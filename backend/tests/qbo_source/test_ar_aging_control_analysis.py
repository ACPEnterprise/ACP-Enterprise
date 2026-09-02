from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from app.qbo_source.ar_aging_control_analysis import _metrics


def test_ar_aging_metrics_reconcile_open_items(tmp_path: Path) -> None:
    workbook = tmp_path / "ar-aging.xlsx"
    values = (
        "A/R Aging Detail Report",
        "As of Aug 31, 2026",
        "Date",
        "Transaction type",
        "Amount",
        "Open balance",
        "Customer full name",
        "CURRENT",
        "Invoice",
        "Synthetic Customer",
        "Payment",
        "TOTAL",
    )
    strings = "".join(f"<si><t>{value}</t></si>" for value in values)
    rows = (
        '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
        '<row r="2"><c r="A2" t="s"><v>1</v></c></row>'
        '<row r="3"><c r="B3" t="s"><v>2</v></c>'
        '<c r="C3" t="s"><v>3</v></c><c r="E3" t="s"><v>6</v></c>'
        '<c r="G3" t="s"><v>4</v></c><c r="H3" t="s"><v>5</v></c></row>'
        '<row r="4"><c r="A4" t="s"><v>7</v></c></row>'
        '<row r="5"><c r="B5"><v>08/31/2026</v></c>'
        '<c r="C5" t="s"><v>8</v></c><c r="E5" t="s"><v>9</v></c>'
        '<c r="G5"><v>1250</v></c><c r="H5"><v>1250</v></c></row>'
        '<row r="6"><c r="B6"><v>08/31/2026</v></c>'
        '<c r="C6" t="s"><v>10</v></c><c r="E6" t="s"><v>9</v></c>'
        '<c r="G6"><v>-250</v></c><c r="H6"><v>-250</v></c></row>'
        '<row r="7"><c r="A7" t="s"><v>11</v></c><c r="H7"><v>1000</v></c></row>'
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
    assert result["open_balance"] == "1000.00"
    assert result["negative_open_item_count"] == 1
    assert result["post_cutoff_rows"] == 0
    assert result["open_1250_item_count"] == 1
