from datetime import datetime, timezone

import pytest
from app.lia.adapters import cash_operational_evidence
from app.lia.foundation import EvidenceState


def packet() -> dict[str, object]:
    return {
        "version": "economics.cash-operational-composition.v1",
        "projection_digest": "a" * 64,
        "work_period": {"state": "COMPLETE", "earned_revenue_minor": 10000},
        "operational_current_state": {
            "state": "AVAILABLE",
            "completed_work_open_commercial_balance_minor": 5000,
        },
        "cash_accounting_period": {
            "state": "EXTERNAL_GATE",
            "recognized_income_minor": None,
        },
    }


def test_lia_adapter_explains_separation_without_exposing_amounts() -> None:
    value = cash_operational_evidence(packet(), observed_at=datetime.now(timezone.utc))
    assert value.state is EvidenceState.PARTIAL
    assert "separate admitted truth planes" in value.safe_summary
    assert "10000" not in value.safe_summary
    assert value.drillback_path == "/business-economics"
    assert "infer cash" in value.limitations[0]


def test_lia_adapter_rejects_tampered_or_incomplete_contract() -> None:
    invalid = packet()
    invalid["projection_digest"] = "bad"
    with pytest.raises(ValueError, match="digest"):
        cash_operational_evidence(invalid, observed_at=datetime.now(timezone.utc))
    invalid = packet()
    invalid.pop("cash_accounting_period")
    with pytest.raises(TypeError, match="three economic truth planes"):
        cash_operational_evidence(invalid, observed_at=datetime.now(timezone.utc))
