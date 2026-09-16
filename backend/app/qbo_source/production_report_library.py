"""Seal allowlisted Production QBO reports as source-backed evidence."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from app.core.config import Settings, settings

from .evidence import (
    ControlEvidenceRegistration,
    ControlEvidenceRegistry,
    ControlReportKind,
    EvidenceStoreError,
    ProtectedFilesystemEvidenceStore,
)
from .production import (
    ProductionFinancialReportRequest,
    read_production_financial_report,
)

REPORT_KINDS = {
    "BalanceSheet": ControlReportKind.BALANCE_SHEET,
    "TrialBalance": ControlReportKind.TRIAL_BALANCE,
    "GeneralLedger": ControlReportKind.GENERAL_LEDGER,
    "AgedReceivables": ControlReportKind.AR_AGING_SUMMARY,
    "AgedPayables": ControlReportKind.AP_AGING_SUMMARY,
    "CustomerBalance": ControlReportKind.CUSTOMER_BALANCE,
    "VendorBalance": ControlReportKind.VENDOR_BALANCE,
}


@dataclass(frozen=True)
class AcquireProductionFinancialReport:
    control_id: str
    report_name: str
    start_date: date
    end_date: date
    basis: str


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _text(value: Mapping[str, object], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise EvidenceStoreError("provider_report_header_invalid")
    return result


def _summaries(value: object) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    if not isinstance(value, list):
        return result
    for row in value:
        if not isinstance(row, Mapping):
            raise EvidenceStoreError("provider_report_row_invalid")
        summary = row.get("Summary")
        if isinstance(summary, Mapping):
            columns = summary.get("ColData")
            if isinstance(columns, list):
                values = [
                    str(item.get("value", ""))
                    for item in columns
                    if isinstance(item, Mapping)
                ]
                if len(values) >= 2:
                    result.append({"label": values[0], "value": values[-1]})
        nested = row.get("Rows")
        if isinstance(nested, Mapping):
            result.extend(_summaries(nested.get("Row")))
    return result


async def acquire_production_financial_report(
    command: AcquireProductionFinancialReport,
    *,
    configuration: Settings = settings,
    acquired_at: datetime | None = None,
) -> dict[str, object]:
    kind = REPORT_KINDS.get(command.report_name)
    if kind is None:
        raise ValueError("unsupported financial report")
    basis = command.basis.lower()
    if basis not in {"cash", "accrual"}:
        raise ValueError("cash or accrual report basis is required")
    if not configuration.qbo_production_evidence_root:
        raise EvidenceStoreError("production_evidence_root_unavailable")
    document, marker = await read_production_financial_report(
        ProductionFinancialReportRequest(
            command.report_name,
            command.start_date,
            command.end_date,
            basis,
        ),
        configuration,
    )
    header = document.get("Header")
    rows = document.get("Rows")
    if not isinstance(header, Mapping) or not isinstance(rows, Mapping):
        raise EvidenceStoreError("provider_report_invalid")
    if (
        _text(header, "ReportName") != command.report_name
        or _text(header, "StartPeriod") != command.start_date.isoformat()
        or _text(header, "EndPeriod") != command.end_date.isoformat()
        or _text(header, "ReportBasis").lower() != basis
    ):
        raise EvidenceStoreError("provider_report_scope_mismatch")
    realm_id = _text(marker, "realm_id")
    company_name = _text(marker, "company_name")
    raw = _canonical(document)
    raw_digest = hashlib.sha256(raw).hexdigest()
    store = ProtectedFilesystemEvidenceStore(
        root=Path(str(configuration.qbo_production_evidence_root)),
        repository_root=Path(configuration.qbo_repository_root),
    )
    raw_root = store.root / "controls" / "raw"
    raw_root.mkdir(mode=0o700, exist_ok=True)
    raw_path = raw_root / f"{raw_digest}.json"
    store._store_named_immutable(raw_path, raw)
    observed_at = acquired_at or datetime.now(timezone.utc)
    generated = header.get("Time")
    generated_at = (
        datetime.fromisoformat(generated.replace("Z", "+00:00"))
        if isinstance(generated, str) and generated
        else None
    )
    registry = ControlEvidenceRegistry(store)
    registration_digest = registry.register(
        ControlEvidenceRegistration(
            control_id=command.control_id,
            kind=kind,
            raw_sha256=raw_digest,
            byte_size=len(raw),
            storage_reference=f"evidence://controls/raw/{raw_digest}.json",
            report_end_date=command.end_date,
            accounting_basis=basis,
            generated_at=generated_at,
            safe_report_parameters={
                "start_date": command.start_date.isoformat(),
                "end_date": command.end_date.isoformat(),
                "report_name": command.report_name,
                "realm_id": realm_id,
                "company_name": company_name,
                "currency": str(header.get("Currency") or ""),
                "acquired_at": observed_at.isoformat(),
                "provider_environment": "production",
            },
        )
    )
    summary_totals = _summaries(rows.get("Row"))
    projection = {
        "contract_version": "qbo-source-backed-report-library/v1",
        "control_id": command.control_id,
        "report_name": command.report_name,
        "authority": "QBO_SOURCE_BACKED",
        "accepted_as_acp_accounting": False,
        "mutation_authority": "none",
        "realm_id": realm_id,
        "company_name": company_name,
        "start_date": command.start_date.isoformat(),
        "end_date": command.end_date.isoformat(),
        "basis": basis,
        "currency": header.get("Currency"),
        "source_as_of": header.get("Time"),
        "acquired_at": observed_at.isoformat(),
        "raw_sha256": raw_digest,
        "registration_digest": registration_digest,
        "summary_totals": summary_totals,
        "provider_pagination_applicable": False,
    }
    projection_digest = registry.register_authority_document(
        authority_id=f"{command.control_id}-source-projection", document=projection
    )
    return {
        **projection,
        "raw_path": str(raw_path),
        "projection_digest": projection_digest,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-id", required=True)
    parser.add_argument("--report", choices=tuple(REPORT_KINDS), required=True)
    parser.add_argument("--start-date", required=True, type=date.fromisoformat)
    parser.add_argument("--end-date", required=True, type=date.fromisoformat)
    parser.add_argument("--basis", choices=("cash", "accrual"), required=True)
    args = parser.parse_args(argv)
    result = asyncio.run(
        acquire_production_financial_report(
            AcquireProductionFinancialReport(
                args.control_id, args.report, args.start_date, args.end_date, args.basis
            )
        )
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
