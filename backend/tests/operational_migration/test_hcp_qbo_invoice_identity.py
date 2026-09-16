import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from app.operational_migration.hcp_qbo_invoice_identity import (
    build_invoice_identity_inventory,
    classify_payment_control_invoice_links,
)


def _page(root: Path, name: str, values: list[dict[str, object]]) -> None:
    target = root / "raw" / name
    target.mkdir(parents=True)
    (target / "page-0001.json").write_text(json.dumps({name: values}))


def _workbook(path: Path, rows: list[list[str]]) -> None:
    strings = [value for row in rows for value in row]
    indexes = iter(range(len(strings)))
    sheet_rows = []
    for row_number, row in enumerate(rows, start=1):
        cells = []
        for column, _value in enumerate(row, start=1):
            letter = chr(64 + column)
            cells.append(f'<c r="{letter}{row_number}" t="s"><v>{next(indexes)}</v></c>')
        sheet_rows.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    shared = "".join(f"<si><t>{value}</t></si>" for value in strings)
    with ZipFile(path, "w", ZIP_DEFLATED) as workbook:
        workbook.writestr(
            "xl/sharedStrings.xml",
            f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{shared}</sst>',
        )
        workbook.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            + "".join(sheet_rows)
            + "</sheetData></worksheet>",
        )


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    hcp = tmp_path / "hcp"
    hcp.mkdir()
    (hcp / "acquisition-package-manifest.json").write_text(
        json.dumps({"contract": "hcp-source-4-acquisition-package/v1", "request_methods": ["GET"]})
    )
    _page(hcp, "jobs", [{"id": "job-1", "customer": {"id": "customer-1"}, "address": {"id": "address-1"}}])
    _page(
        hcp,
        "invoices",
        [
            {"id": "invoice_11111111111111111111111111111111", "job_id": "job-1", "invoice_number": "10"},
            {"id": "invoice_22222222222222222222222222222222", "job_id": "missing", "invoice_number": "20"},
        ],
    )
    raw = tmp_path / "qbo.xlsx"
    _workbook(
        raw,
        [
            ["Distribution account", "Transaction date", "Transaction type", "Num", "Name", "Description", "Amount"],
            ["Income", "2026-05-01", "Invoice", "10", "Same Name", "invoice_11111111111111111111111111111111", "100.00"],
            ["Income", "2026-05-01", "Invoice", "20", "Same Name", "same date and amount are insufficient", "100.00"],
            ["Bank", "2026-05-01", "Payment", "30", "Same Name", "ignored", "100.00"],
        ],
    )
    content = raw.read_bytes()
    registration = tmp_path / "registration.json"
    registration.write_text(
        json.dumps(
            {
                "schema_version": "qbo-control-registration/v1",
                "raw_sha256": hashlib.sha256(content).hexdigest(),
                "byte_size": len(content),
            }
        )
    )
    return hcp, registration, raw


def test_exact_reference_only_and_parent_readiness(tmp_path: Path) -> None:
    hcp, registration, raw = _inputs(tmp_path)
    result = build_invoice_identity_inventory(
        hcp_source_root=hcp,
        qbo_registration_path=registration,
        qbo_raw_path=raw,
    )
    result.verify()

    assert result.counts == {
        "hcp_invoice_count": 2,
        "hcp_exact_source_job_parent": 1,
        "hcp_source_job_parent_missing": 1,
        "hcp_missing_parent_customer_history_exact": 0,
        "hcp_missing_parent_legacy_only": 1,
        "qbo_invoice_control_row_count": 2,
        "exact_provider_reference": 1,
        "no_exact_binding": 1,
        "conflicting_binding": 0,
    }
    assert result.authority["aggregation_safe"] is False


def test_rejects_changed_control_bytes(tmp_path: Path) -> None:
    hcp, registration, raw = _inputs(tmp_path)
    raw.write_bytes(raw.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="raw digest mismatch"):
        build_invoice_identity_inventory(
            hcp_source_root=hcp,
            qbo_registration_path=registration,
            qbo_raw_path=raw,
        )


def test_private_control_invoice_number_is_never_exact_identity(tmp_path: Path) -> None:
    hcp, _registration, _raw = _inputs(tmp_path)
    controls = tmp_path / "controls"
    incoming = controls / "incoming"
    incoming.mkdir(parents=True)
    content = (
        b"Job ID,Customer ID,Invoice Number,Payment Type\n"
        b"private-job,private-customer,10,payment imported from quickbooks\n"
    )
    (incoming / "payments.csv").write_bytes(content)
    (controls / "hcp-control-manifest-v1.json").write_text(
        json.dumps(
            {
                "contract_version": "hcp-controls-intake/1",
                "entries": [
                    {
                        "classification": "PAYMENTS_DETAIL",
                        "protected_reference": "incoming/payments.csv",
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "row_count": 1,
                    }
                ],
            }
        )
    )

    result = classify_payment_control_invoice_links(
        control_root=controls, hcp_source_root=hcp
    )

    assert result["record_count"] == 1
    assert result["counts"] == {
        "EXACT_LINK": 0,
        "MULTIPLE_EXACT_CANDIDATES": 0,
        "NO_BINDING_EVIDENCE": 1,
        "CONFLICTING": 0,
        "NOT_INVOICE_RELATED": 0,
    }
    assert result["records"][0]["invoice_number_api_candidate_count"] == 1
