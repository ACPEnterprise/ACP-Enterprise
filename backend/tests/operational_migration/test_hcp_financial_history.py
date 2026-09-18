import json
from pathlib import Path

import pytest
from app.operational_migration.hcp_financial_history import (
    classify_financial_history,
)


def _write_page(root: Path, name: str, records: list[dict[str, object]]) -> None:
    target = root / "raw" / name
    target.mkdir(parents=True)
    (target / "page-0001.json").write_text(json.dumps({name: records}))


def _source(tmp_path: Path) -> Path:
    (tmp_path / "acquisition-package-manifest.json").write_text(
        json.dumps(
            {
                "contract": "hcp-source-4-acquisition-package/v1",
                "request_methods": ["GET"],
            }
        )
    )
    _write_page(tmp_path, "jobs", [{"id": "job-1"}])
    _write_page(
        tmp_path,
        "invoices",
        [
            {
                "id": "invoice-1",
                "job_id": "job-1",
                "status": "paid",
                "payments": [
                    {
                        "id": "payment-1",
                        "status": "succeeded",
                        "payment_method": "imported_from_quickbooks",
                    },
                    {
                        "id": "payment-2",
                        "status": "failed",
                        "payment_method": "credit_card",
                    },
                ],
                "refunds": [{"id": "refund-1"}, {"id": None}],
            },
            {
                "id": "invoice-2",
                "job_id": "missing-job",
                "status": "open",
                "payments": [],
                "refunds": [],
            },
        ],
    )
    return tmp_path


def test_classifies_source_history_without_promoting_accounting(tmp_path: Path) -> None:
    result = classify_financial_history(_source(tmp_path))
    result.verify()

    assert result.invoice_counts == {
        "source_acquired": 2,
        "source_graph_complete": 1,
        "source_parent_missing": 1,
        "status_open": 1,
        "status_paid": 1,
    }
    assert result.payment_counts == {
        "source_acquired": 2,
        "source_invoice_exact": 2,
        "source_backed_displayable": 1,
        "failed_assertion": 1,
        "qbo_overlap_hold": 1,
        "hcp_only_displayable": 0,
        "exact_qbo_overlap": 0,
        "qbo_only": 0,
        "source_displayable_nonaggregated": 1,
        "conflicting": 0,
        "unresolved": 1,
    }
    assert result.payment_records[0]["aggregation_safe"] is False
    assert result.payment_records[0]["exact_qbo_provider_identity"] is None
    assert (
        result.payment_records[0]["disposition"] == "SOURCE_DISPLAYABLE_NONAGGREGATED"
    )
    assert result.payment_records[1]["disposition"] == "UNRESOLVED"
    assert result.refund_counts == {
        "source_acquired": 2,
        "exact_refund": 1,
        "source_backed_unlinked_refund": 1,
        "conflicting": 0,
        "source_missing": 0,
    }
    assert {record["disposition"] for record in result.refund_records} == {
        "EXACT_REFUND",
        "SOURCE_BACKED_UNLINKED_REFUND",
    }
    assert result.authority["mutation_authority"] == "none"


def test_payment_and_refund_records_are_digest_stable(tmp_path: Path) -> None:
    source = _source(tmp_path)
    first = classify_financial_history(source)
    second = classify_financial_history(source)

    assert first == second
    first.verify()
    assert all(record["aggregation_safe"] is False for record in first.payment_records)
    assert all(record["aggregation_safe"] is False for record in first.refund_records)


def test_rejects_duplicate_payment_source_identity(tmp_path: Path) -> None:
    source = _source(tmp_path)
    path = source / "raw" / "invoices" / "page-0001.json"
    value = json.loads(path.read_text())
    value["invoices"][1]["payments"] = [
        {
            "id": "payment-1",
            "status": "succeeded",
            "payment_method": "cash",
        }
    ]
    path.write_text(json.dumps(value))

    with pytest.raises(ValueError, match="duplicate HCP Payment"):
        classify_financial_history(source)
