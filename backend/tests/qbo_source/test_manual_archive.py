import os
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.qbo_source import manual_archive, router
from app.qbo_source.accounting_evidence_projection import project_latest_qbo_workspace
from app.qbo_source.errors import QboEvidenceProjectionError
from app.qbo_source.manual_archive import (
    project_manual_aged_receivables,
    project_manual_archive,
)

ARCHIVE = Path(os.environ.get("QBO_MANUAL_ARCHIVE_TEST_ROOT", "/unavailable"))


@pytest.mark.skipif(
    not ARCHIVE.is_dir(), reason="sealed laptop custody package unavailable"
)
def test_manual_archive_projects_verified_source_counts_without_native_posting() -> (
    None
):
    result = project_manual_archive(root=ARCHIVE, basis="accrual")

    assert len(result["accounts"]) == 131
    assert len(result["invoices"]) == 1341
    assert len(result["vendors"]) == 868
    assert result["entity_counts"]["purchase"] == 12414
    assert result["ar"]["total_open"]["amount"] == "500584.34"
    reconciliation = result["historical_reconciliation"]
    assert reconciliation["source_record_count"] == 20702
    assert reconciliation["relationship_id_count"] == 97093
    assert reconciliation["conflict_count"] == 7
    assert reconciliation["payment_invoice_links"] == 1171
    assert reconciliation["missing_payment_invoice_links"] == 0
    assert reconciliation["mutation_authority"] == "none"
    assert result["mutation_authority"] == "none"
    assert "source_reported_not_posted_acp_ledger" in result["limitations"]


@pytest.mark.skipif(
    not ARCHIVE.is_dir(), reason="sealed laptop custody package unavailable"
)
def test_manual_archive_projects_read_only_aged_receivables() -> None:
    result = project_manual_aged_receivables(root=ARCHIVE, report_date="2026-11-27")

    assert result["net_open_ar"] == "500584.34"
    assert result["current"]["amount"] == "12500.00"
    assert result["overdue"]["amount"] == "488084.34"
    assert result["accepted_as_acp_accounting"] is False
    assert result["mutation_authority"] == "none"
    assert result["includes_customer_credits_and_unapplied_payments"] is False
    assert result["source_digest"] == result["source_manifest_sha256"]
    assert (
        "unapplied_payments_and_credits_require_account_level_bridge"
        in result["limitations"]
    )


@pytest.mark.skipif(
    not ARCHIVE.is_dir(), reason="sealed laptop custody package unavailable"
)
def test_manual_archive_is_used_only_when_bounded_evidence_is_absent() -> None:
    result = project_latest_qbo_workspace(
        evidence_root=ARCHIVE / "missing-bounded-root",
        basis="accrual",
        manual_archive_root=ARCHIVE,
    )

    assert result["evidence_mode"] == "sealed_manual_archive"
    assert result["mode"] == "historical"


def test_manual_archive_rejects_invalid_custody_contract(tmp_path: Path) -> None:
    (tmp_path / "custody-manifest.json").write_text('{"contract":"wrong"}')
    with pytest.raises(
        QboEvidenceProjectionError, match="manual_archive_contract_invalid"
    ):
        project_manual_archive(root=tmp_path, basis="accrual")


def test_manual_aged_receivables_preserves_scalar_provider_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        manual_archive,
        "project_manual_archive",
        lambda **_: {
            "invoices": [
                {
                    "open_balance": {"amount": "10.00"},
                    "due_date": "2026-11-28",
                },
                {
                    "open_balance": {"amount": "25.00"},
                    "due_date": "2026-11-01",
                },
            ],
            "ar": {
                "total_open": {"amount": "35.00"},
                "invoice_evidence_count": 2,
                "open_invoice_count": 2,
            },
            "source_manifest_sha256": "a" * 64,
        },
    )
    monkeypatch.setattr(
        manual_archive,
        "_read_json",
        lambda _: {
            "connection": {"company_name": "Test Company", "realm_id": "masked"},
            "current_acquisition": {"cutoff": "2026-11-19"},
            "sealed_at": "2026-11-20T00:00:00Z",
        },
    )

    result = project_manual_aged_receivables(root=tmp_path, report_date="2026-11-27")

    assert result["net_open_ar"] == "35.00"
    assert result["current"]["amount"] == "10.00"
    assert result["overdue"]["amount"] == "25.00"
    assert result["source_digest"] == "a" * 64
    assert result["includes_customer_credits_and_unapplied_payments"] is False


@pytest.mark.asyncio
async def test_aged_receivables_route_uses_archive_before_live_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = uuid4()
    expected = {
        "contract_version": "qbo-source-backed-ar-summary/v1",
        "net_open_ar": "35.00",
        "includes_customer_credits_and_unapplied_payments": False,
    }
    monkeypatch.setattr(router.settings, "qbo_manual_archive_root", "/evidence")
    monkeypatch.setattr(router.settings, "qbo_production_acp_company_id", company_id)
    monkeypatch.setattr(router, "project_manual_aged_receivables", lambda **_: expected)

    async def live_provider_must_not_run(*_: object, **__: object) -> None:
        raise AssertionError("live QBO provider was called")

    monkeypatch.setattr(
        router, "read_production_aged_receivables", live_provider_must_not_run
    )

    response = await router.qbo_source_backed_aged_receivables(
        report_date=date(2026, 11, 27),
        authorization=SimpleNamespace(company=SimpleNamespace(id=company_id)),
    )

    assert response.status_code == 200
    assert b'"net_open_ar":"35.00"' in response.body
