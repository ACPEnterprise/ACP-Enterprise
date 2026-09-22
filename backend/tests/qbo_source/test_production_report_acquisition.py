from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.qbo_source.evidence import EvidenceStoreError
from app.qbo_source.production_report_acquisition import (
    AcquireProductionProfitAndLoss,
    acquire_production_profit_and_loss,
)


def _settings(tmp_path: Path) -> SimpleNamespace:
    repository = tmp_path / "repository"
    evidence = tmp_path / "evidence"
    repository.mkdir()
    evidence.mkdir(mode=0o700)
    return SimpleNamespace(
        qbo_production_evidence_root=str(evidence),
        qbo_repository_root=str(repository),
    )


def _report(*, start: str = "2026-05-01", basis: str = "Cash") -> dict[str, object]:
    return {
        "Header": {
            "ReportName": "ProfitAndLoss",
            "StartPeriod": start,
            "EndPeriod": "2026-05-31",
            "ReportBasis": basis,
            "Currency": "USD",
            "Time": "2026-09-15T14:00:00Z",
        },
        "Columns": {"Column": [{"ColTitle": "Account"}, {"ColTitle": "Total"}]},
        "Rows": {
            "Row": [
                {
                    "type": "Section",
                    "Header": {"ColData": [{"value": "Income"}, {"value": ""}]},
                    "Summary": {
                        "ColData": [{"value": "Total Income"}, {"value": "100.00"}]
                    },
                }
            ]
        },
    }


@pytest.mark.asyncio
async def test_acquires_and_registers_exact_source_backed_report(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)

    async def reader(request, configuration):
        assert request.start_date == date(2026, 5, 1)
        assert request.end_date == date(2026, 5, 31)
        assert request.accounting_method == "cash"
        assert configuration is settings
        return _report(), {
            "realm_id": "123456789",
            "company_name": "All County Plumbing and Leak",
            "environment": "production",
        }

    result = await acquire_production_profit_and_loss(
        AcquireProductionProfitAndLoss(
            "qbo-may-2026-profit-loss-cash-v1",
            date(2026, 5, 1),
            date(2026, 5, 31),
            "cash",
        ),
        configuration=settings,
        reader=reader,
        acquired_at=datetime(2026, 9, 15, 15, tzinfo=timezone.utc),
    )

    assert result["state"] == "QBO_SOURCE_BACKED_REPORT_REGISTERED"
    assert result["accepted_as_acp_accounting"] is False
    assert result["mutation_authority"] == "none"
    assert result["report_totals"] == [{"label": "Total Income", "value": "100.00"}]
    assert result["provider_pagination_applicable"] is False
    raw_path = Path(str(result["raw_path"]))
    assert raw_path.is_file()
    registration = json.loads(
        (
            Path(settings.qbo_production_evidence_root)
            / "controls"
            / "qbo-may-2026-profit-loss-cash-v1.json"
        ).read_bytes()
    )
    assert registration["schema_version"] == "qbo-control-registration/v1"
    assert registration["raw_sha256"] == result["raw_sha256"]
    assert registration["safe_report_parameters"]["start_date"] == "2026-05-01"
    assert (
        registration["safe_report_parameters"]["provider_environment"] == "production"
    )


@pytest.mark.asyncio
async def test_rejects_provider_scope_mismatch_before_custody_write(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)

    async def reader(request, configuration):
        return _report(start="2026-04-01"), {
            "realm_id": "123456789",
            "company_name": "All County Plumbing and Leak",
            "environment": "production",
        }

    with pytest.raises(EvidenceStoreError, match="provider_report_scope_mismatch"):
        await acquire_production_profit_and_loss(
            AcquireProductionProfitAndLoss(
                "qbo-may-2026-profit-loss-cash-v1",
                date(2026, 5, 1),
                date(2026, 5, 31),
                "cash",
            ),
            configuration=settings,
            reader=reader,
        )

    controls = Path(settings.qbo_production_evidence_root) / "controls"
    assert not controls.exists() or not list((controls / "raw").glob("*.json"))
