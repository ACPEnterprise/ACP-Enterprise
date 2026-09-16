"""Acquire and seal one provider-authored Production QBO report.

This command is deliberately report-specific and GET-only.  It registers the
provider document as source evidence; it never creates ACP Accounting truth.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
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
    ProductionProfitAndLossRequest,
    read_production_profit_and_loss,
)
from .source_report import project_profit_and_loss

ReportReader = Callable[
    [ProductionProfitAndLossRequest, Settings],
    Awaitable[tuple[dict[str, object], dict[str, object]]],
]


@dataclass(frozen=True)
class AcquireProductionProfitAndLoss:
    control_id: str
    start_date: date
    end_date: date
    basis: str


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _required_text(value: Mapping[str, object], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise EvidenceStoreError("provider_report_header_invalid")
    return result


def _provider_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EvidenceStoreError("provider_report_time_invalid") from error


async def acquire_production_profit_and_loss(
    command: AcquireProductionProfitAndLoss,
    *,
    configuration: Settings = settings,
    reader: ReportReader = read_production_profit_and_loss,
    acquired_at: datetime | None = None,
) -> dict[str, object]:
    """Read, validate, and immutably register one exact provider P&L."""
    basis = command.basis.lower()
    if basis not in {"cash", "accrual"}:
        raise ValueError("cash or accrual report basis is required")
    if command.start_date > command.end_date:
        raise ValueError("report start date must not follow end date")
    if not configuration.qbo_production_evidence_root:
        raise EvidenceStoreError("production_evidence_root_unavailable")

    document, marker = await reader(
        ProductionProfitAndLossRequest(
            command.start_date, command.end_date, basis
        ),
        configuration,
    )
    realm_id = _required_text(marker, "realm_id")
    company_name = _required_text(marker, "company_name")
    if marker.get("environment") not in {None, "production"}:
        raise EvidenceStoreError("provider_environment_not_production")
    projection = project_profit_and_loss(
        document, realm_id=realm_id, expected_company_name=company_name
    )
    if (
        projection["start_date"] != command.start_date.isoformat()
        or projection["end_date"] != command.end_date.isoformat()
        or projection["accounting_basis"] != basis
        or projection["authority"] != "QBO_SOURCE_BACKED"
    ):
        raise EvidenceStoreError("provider_report_scope_mismatch")

    raw = _canonical_json(document)
    raw_digest = hashlib.sha256(raw).hexdigest()
    repository = Path(configuration.qbo_repository_root).resolve()
    store = ProtectedFilesystemEvidenceStore(
        root=Path(str(configuration.qbo_production_evidence_root)),
        repository_root=repository,
    )
    raw_root = store.root / "controls" / "raw"
    raw_root.mkdir(mode=0o700, exist_ok=True)
    raw_path = raw_root / f"{raw_digest}.json"
    store._store_named_immutable(raw_path, raw)

    observed_at = acquired_at or datetime.now(timezone.utc)
    header = document.get("Header")
    if not isinstance(header, Mapping):
        raise EvidenceStoreError("provider_report_header_invalid")
    generated_at = _provider_time(header.get("Time"))
    registration = ControlEvidenceRegistration(
        control_id=command.control_id,
        kind=ControlReportKind.PROFIT_AND_LOSS,
        raw_sha256=raw_digest,
        byte_size=len(raw),
        storage_reference=f"evidence://controls/raw/{raw_digest}.json",
        report_end_date=command.end_date,
        accounting_basis=basis,
        generated_at=generated_at,
        safe_report_parameters={
            "start_date": command.start_date.isoformat(),
            "end_date": command.end_date.isoformat(),
            "report_name": _required_text(header, "ReportName"),
            "realm_id": realm_id,
            "company_name": company_name,
            "currency": str(projection.get("currency") or ""),
            "acquired_at": observed_at.isoformat(),
            "provider_environment": "production",
        },
    )
    registry = ControlEvidenceRegistry(store)
    registration_digest = registry.register(registration)
    rows = projection.get("rows")
    if not isinstance(rows, list):
        raise EvidenceStoreError("provider_report_rows_invalid")
    report_totals = [
        {"label": values[0], "value": values[-1]}
        for row in rows
        if isinstance(row, Mapping)
        and row.get("kind") == "summary"
        and isinstance((values := row.get("values")), list)
        and len(values) >= 2
        and all(isinstance(value, str) for value in values)
    ]
    projection_document = {
        **projection,
        "raw_sha256": raw_digest,
        "registration_digest": registration_digest,
        "acquired_at": observed_at.isoformat(),
        "control_id": command.control_id,
    }
    projection_digest = registry.register_authority_document(
        authority_id=f"{command.control_id}-source-projection",
        document=projection_document,
    )
    return {
        "state": "QBO_SOURCE_BACKED_REPORT_REGISTERED",
        "control_id": command.control_id,
        "provider_environment": "production",
        "realm_id": realm_id,
        "company_name": company_name,
        "period": {
            "start_date": command.start_date.isoformat(),
            "end_date": command.end_date.isoformat(),
        },
        "basis": basis,
        "currency": projection.get("currency"),
        "source_as_of": projection.get("source_as_of"),
        "acquired_at": observed_at.isoformat(),
        "raw_path": str(raw_path),
        "raw_sha256": raw_digest,
        "registration_digest": registration_digest,
        "projection_digest": projection_digest,
        "report_row_count": len(rows),
        "report_totals": report_totals,
        "provider_pagination_applicable": False,
        "provider_report_complete": True,
        "authority": "QBO_SOURCE_BACKED",
        "accepted_as_acp_accounting": False,
        "mutation_authority": "none",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Acquire and seal one GET-only Production QBO P&L"
    )
    parser.add_argument("--control-id", required=True)
    parser.add_argument("--start-date", required=True, type=date.fromisoformat)
    parser.add_argument("--end-date", required=True, type=date.fromisoformat)
    parser.add_argument("--basis", choices=("cash", "accrual"), required=True)
    arguments = parser.parse_args(argv)
    result = asyncio.run(
        acquire_production_profit_and_loss(
            AcquireProductionProfitAndLoss(
                arguments.control_id,
                arguments.start_date,
                arguments.end_date,
                arguments.basis,
            )
        )
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
