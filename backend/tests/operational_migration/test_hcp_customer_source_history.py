import json
from pathlib import Path

import pytest
from app.operational_migration.hcp_customer_source_history import (
    HcpCustomerSourceHistoryError,
    project_customer_source_history,
)


def _page(root: Path, family: str, rows: list[dict[str, object]]) -> None:
    target = root / "raw" / family
    target.mkdir(parents=True)
    (target / "page-0001.json").write_text(json.dumps({family: rows}))


def _source(root: Path) -> Path:
    (root / "acquisition-package-manifest.json").write_text(
        json.dumps(
            {
                "contract": "hcp-source-4-acquisition-package/v1",
                "request_methods": ["GET"],
            }
        )
    )
    _page(
        root,
        "estimates",
        [
            {
                "id": "estimate-1",
                "estimate_number": "100",
                "customer": {"id": "customer-1"},
                "work_status": "approved",
                "options": [
                    {"id": "option-1", "name": "Repair", "total_amount": 12500}
                ],
            },
            {
                "id": "estimate-other",
                "customer": {"id": "customer-other"},
                "options": [],
            },
        ],
    )
    _page(
        root,
        "jobs",
        [
            {"id": "job-1", "customer": {"id": "customer-1"}},
            {"id": "job-other", "customer": {"id": "customer-other"}},
        ],
    )
    _page(
        root,
        "invoices",
        [
            {
                "id": "invoice-1",
                "job_id": "job-1",
                "invoice_number": "200",
                "status": "paid",
                "amount": 12500,
                "due_amount": 0,
                "payments": [
                    {
                        "id": "payment-1",
                        "status": "succeeded",
                        "amount": 12500,
                        "payment_method": "imported_from_quickbooks",
                    }
                ],
            },
            {"id": "invoice-other", "job_id": "job-other", "payments": []},
        ],
    )
    return root


def test_projects_exact_customer_history_without_accounting_promotion(
    tmp_path: Path,
) -> None:
    result = project_customer_source_history(
        _source(tmp_path), source_customer_id="customer-1"
    )

    assert result["counts"] == {"estimates": 1, "invoices": 1, "payments": 1}
    assert result["accepted_as_acp_accounting"] is False
    assert result["mutation_authority"] == "none"
    assert result["estimates"][0]["source_id"] == "estimate-1"
    payment = result["invoices"][0]["payments"][0]
    assert payment["overlap_disposition"] == (
        "HOLD_FROM_AGGREGATION_PENDING_QBO_RECONCILIATION"
    )


def test_rejects_non_read_only_source_package(tmp_path: Path) -> None:
    root = _source(tmp_path)
    (root / "acquisition-package-manifest.json").write_text(
        json.dumps(
            {
                "contract": "hcp-source-4-acquisition-package/v1",
                "request_methods": ["GET", "POST"],
            }
        )
    )

    with pytest.raises(HcpCustomerSourceHistoryError, match="not_read_only"):
        project_customer_source_history(root, source_customer_id="customer-1")
