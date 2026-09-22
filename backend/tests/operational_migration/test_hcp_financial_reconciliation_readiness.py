import json
from pathlib import Path

import pytest
from app.operational_migration.hcp_financial_reconciliation_readiness import (
    build_financial_reconciliation_readiness,
)


def _page(root: Path, name: str, records: list[dict[str, object]]) -> None:
    target = root / "raw" / name
    target.mkdir(parents=True)
    (target / "page-0001.json").write_text(json.dumps({name: records}))


def _evidence(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source"
    source.mkdir()
    (source / "acquisition-package-manifest.json").write_text(
        json.dumps(
            {
                "contract": "hcp-source-4-acquisition-package/v1",
                "request_methods": ["GET"],
            }
        )
    )
    customers = [{"id": f"customer-{index:02d}"} for index in range(50)]
    jobs = [
        {"id": f"job-{index:02d}", "customer": {"id": f"customer-{index:02d}"}}
        for index in range(50)
    ]
    estimates = [
        {"id": f"estimate-{index:02d}", "customer": {"id": f"customer-{index:02d}"}}
        for index in range(50)
    ]
    invoices = [
        {
            "id": f"invoice-{index:02d}",
            "job_id": f"job-{index:02d}",
            "status": "open" if index == 0 else "paid",
            "due_amount": 1250 if index == 0 else 0,
            "payments": [
                {
                    "id": f"payment-{index:02d}",
                    "payment_method": "imported_from_quickbooks"
                    if index == 1
                    else "cash",
                }
            ],
            "refunds": [{"id": None}] if index == 2 else [],
        }
        for index in range(50)
    ]
    for name, records in (
        ("customers", customers),
        ("jobs", jobs),
        ("estimates", estimates),
        ("invoices", invoices),
    ):
        _page(source, name, records)

    controls = tmp_path / "controls"
    controls.mkdir()
    ar = {
        "schema_version": "qbo-ar-aging-control-analysis/v1",
        "open_balance": "80.00",
        "type_open_balances": {
            "Invoice": "100.00",
            "Payment": "-15.00",
            "Deposit": "-5.00",
        },
        "negative_open_item_count": 2,
        "cutoff_to_current_variance": "3.00",
    }
    from app.operational_migration.hcp_financial_reconciliation_readiness import _digest

    ar["evidence_digest"] = _digest(ar)
    (controls / "qbo-cutoff-ar-aging-control-2026-08-31-v1.json").write_text(
        json.dumps(ar)
    )
    (controls / "broad-pnl.json").write_text(
        json.dumps(
            {
                "schema_version": "qbo-control-registration/v1",
                "control_id": "broad-pnl",
                "kind": "profit_and_loss",
                "report_end_date": "2026-08-31",
                "accounting_basis": "cash",
                "safe_report_parameters": {
                    "start_date": "2022-01-01",
                    "end_date": "2026-08-31",
                },
            }
        )
    )
    return source, controls


def test_builds_exact_source_journeys_and_fail_closed_ar_readiness(
    tmp_path: Path,
) -> None:
    source, controls = _evidence(tmp_path)
    result = build_financial_reconciliation_readiness(
        source_root=source, qbo_controls_root=controls
    )
    result.verify()

    assert len(result.journeys) == 50
    assert result.journey_counts == {
        "COMPLETE_SOURCE_HISTORY": 49,
        "FINANCIAL_OVERLAP_HOLD": 1,
    }
    assert result.ar_readiness["gross_open_ready"] is True
    assert result.ar_readiness["gross_open_hcp_assertion_balance"] == "12.50"
    assert result.ar_readiness["net_ar_ready"] is False
    assert (
        result.may_report_evidence["provider_may_profit_and_loss_registered"] is False
    )
    assert result.authority["accepted_as_acp_accounting"] is False


def test_rejects_tampered_ar_control(tmp_path: Path) -> None:
    source, controls = _evidence(tmp_path)
    path = controls / "qbo-cutoff-ar-aging-control-2026-08-31-v1.json"
    value = json.loads(path.read_text())
    value["open_balance"] = "81.00"
    path.write_text(json.dumps(value))

    with pytest.raises(ValueError, match="semantic digest mismatch"):
        build_financial_reconciliation_readiness(
            source_root=source, qbo_controls_root=controls
        )
