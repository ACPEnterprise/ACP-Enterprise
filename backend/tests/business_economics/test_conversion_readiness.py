from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.business_economics.conversion_readiness import project_conversion_readiness


def row(*, acceptance: str = "approved", amount: str = "100.00") -> tuple[object, object]:
    estimate_id = uuid4()
    return (
        SimpleNamespace(
            id=estimate_id,
            branch_id=uuid4(),
            customer_id=uuid4(),
            acceptance_status=acceptance,
            status="approved" if acceptance == "approved" else "sent",
        ),
        SimpleNamespace(
            id=uuid4(),
            revision_number=1,
            issued_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            total_amount=Decimal(amount),
            currency="USD",
        ),
    )


def project(rows: tuple[tuple[object, object], ...], decisions: tuple[object, ...] = ()) -> dict[str, object]:
    return project_conversion_readiness(
        rows=rows,
        decisions=decisions,
        conversions=(),
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
    )


def test_complete_terminal_cohort_has_deterministic_close_rate() -> None:
    accepted = row()
    declined = row(acceptance="rejected", amount="50.00")
    result = project((accepted, declined))

    assert result["readiness"] == "READY"
    assert result["presented_count"] == 2
    assert result["accepted_count"] == 1
    assert result["close_rate"] == "0.5"
    assert result["presented_value"] == "150.00"
    assert result["mutation_authority"] == "none"


def test_open_cohort_is_partial_and_has_no_close_rate() -> None:
    result = project((row(acceptance="pending"),))

    assert result["readiness"] == "PARTIAL"
    assert result["pending_count"] == 1
    assert result["close_rate"] is None


def test_contradictory_decisions_fail_closed() -> None:
    estimate, revision = row(acceptance="pending")
    decisions = (
        SimpleNamespace(id=uuid4(), estimate_id=estimate.id, decision="approved"),
        SimpleNamespace(id=uuid4(), estimate_id=estimate.id, decision="rejected"),
    )
    result = project(((estimate, revision),), decisions)

    assert result["readiness"] == "CONFLICTING_EVIDENCE"
    assert result["close_rate"] is None


def test_missing_population_is_not_zero_conversion() -> None:
    result = project(())

    assert result["readiness"] == "SOURCE_MISSING"
    assert result["close_rate"] is None
