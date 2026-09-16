from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timezone

from app.qbo_source.accounting_evidence_projection import QboEvidenceProjectionError


def project_aged_receivables(
    document: Mapping[str, object], *, realm_id: str, expected_company_name: str
) -> dict[str, object]:
    """Project QBO's net A/R total, including customer credits/payments."""
    header = document.get("Header")
    rows = document.get("Rows")
    if not isinstance(header, Mapping) or not isinstance(rows, Mapping):
        raise QboEvidenceProjectionError("qbo_aged_receivables_invalid")
    if header.get("ReportName") != "AgedReceivables":
        raise QboEvidenceProjectionError("qbo_aged_receivables_identity_invalid")
    total = _find_grand_total(rows.get("Row"))
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return {
        "contract_version": "qbo-source-backed-ar-summary/v1",
        "authority": "QBO_SOURCE_BACKED",
        "provider_environment": "production",
        "source": "QuickBooks Online A/R Aging Summary",
        "source_company": expected_company_name,
        "realm_id": realm_id,
        "report_date": _required_text(header, "EndPeriod"),
        "currency": _optional_text(header.get("Currency")),
        "source_as_of": _optional_text(header.get("Time")),
        "acquired_at": datetime.now(timezone.utc).isoformat(),
        "net_open_ar": total,
        "includes_customer_credits_and_unapplied_payments": True,
        "source_digest": hashlib.sha256(canonical).hexdigest(),
        "accepted_as_acp_accounting": False,
        "mutation_authority": "none",
    }


def _find_grand_total(value: object) -> str:
    if not isinstance(value, list):
        raise QboEvidenceProjectionError("qbo_aged_receivables_total_missing")
    for row in value:
        if not isinstance(row, Mapping) or row.get("group") != "GrandTotal":
            continue
        summary = row.get("Summary")
        if not isinstance(summary, Mapping):
            continue
        columns = summary.get("ColData")
        if isinstance(columns, list) and columns:
            final = columns[-1]
            if isinstance(final, Mapping):
                result = _optional_text(final.get("value"))
                if result is not None:
                    return result
    raise QboEvidenceProjectionError("qbo_aged_receivables_total_missing")


def project_profit_and_loss(
    document: Mapping[str, object],
    *,
    realm_id: str,
    expected_company_name: str,
) -> dict[str, object]:
    """Project a provider-authored report without promoting it into ACP Accounting."""
    header = document.get("Header")
    columns = document.get("Columns")
    rows = document.get("Rows")
    if (
        not isinstance(header, Mapping)
        or not isinstance(columns, Mapping)
        or not isinstance(rows, Mapping)
    ):
        raise QboEvidenceProjectionError("qbo_profit_and_loss_invalid")
    if header.get("ReportName") not in {"ProfitAndLoss", "Profit and Loss"}:
        raise QboEvidenceProjectionError("qbo_profit_and_loss_identity_invalid")
    column_items = columns.get("Column")
    if not isinstance(column_items, list):
        raise QboEvidenceProjectionError("qbo_profit_and_loss_columns_invalid")
    projected_columns = [
        str(item.get("ColTitle") or item.get("ColType") or "Value")
        for item in column_items
        if isinstance(item, Mapping)
    ]
    projected_rows: list[dict[str, object]] = []
    _append_rows(rows.get("Row"), projected_rows, depth=0)
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    return {
        "contract_version": "qbo-source-backed-financial-report/v1",
        "report_type": "profit_and_loss",
        "authority": "QBO_SOURCE_BACKED",
        "provider_environment": "production",
        "source": "QuickBooks Online",
        "source_company": expected_company_name,
        "realm_id": realm_id,
        "start_date": _required_text(header, "StartPeriod"),
        "end_date": _required_text(header, "EndPeriod"),
        "accounting_basis": _required_text(header, "ReportBasis").lower(),
        "currency": _optional_text(header.get("Currency")),
        "source_as_of": _optional_text(header.get("Time")),
        "acquired_at": datetime.now(timezone.utc).isoformat(),
        "columns": projected_columns,
        "rows": projected_rows,
        "source_digest": hashlib.sha256(canonical).hexdigest(),
        "accepted_as_acp_accounting": False,
        "mutation_authority": "none",
    }


def _append_rows(value: object, target: list[dict[str, object]], *, depth: int) -> None:
    if not isinstance(value, list):
        return
    for row in value:
        if not isinstance(row, Mapping):
            raise QboEvidenceProjectionError("qbo_profit_and_loss_row_invalid")
        row_type = str(row.get("type") or "Data")
        header = row.get("Header")
        summary = row.get("Summary")
        data = row.get("ColData")
        if isinstance(header, Mapping):
            _append_values(header.get("ColData"), target, depth, "section")
        if isinstance(data, list):
            _append_values(data, target, depth, row_type.lower())
        nested = row.get("Rows")
        if isinstance(nested, Mapping):
            _append_rows(nested.get("Row"), target, depth=depth + 1)
        if isinstance(summary, Mapping):
            _append_values(summary.get("ColData"), target, depth, "summary")


def _append_values(
    value: object, target: list[dict[str, object]], depth: int, kind: str
) -> None:
    if not isinstance(value, list):
        return
    target.append(
        {
            "kind": kind,
            "depth": depth,
            "values": [
                str(item.get("value", "")) if isinstance(item, Mapping) else ""
                for item in value
            ],
        }
    )


def _required_text(value: Mapping[str, object], key: str) -> str:
    result = _optional_text(value.get(key))
    if result is None:
        raise QboEvidenceProjectionError("qbo_profit_and_loss_header_invalid")
    return result


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
