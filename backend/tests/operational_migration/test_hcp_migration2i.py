from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.operational_migration.financial import (
    InvoiceMigrationRecord,
    PaymentMigrationRecord,
)
from app.operational_migration.hcp_migration2i import (
    canonical_nonzero_counts,
    requalify_financial_commands,
    requalify_operational_commands,
    require_equivalent_hold_counts,
)
from app.operational_migration.service import (
    AppointmentMigrationRecord,
    JobMigrationRecord,
)

NOW = datetime(2023, 1, 1, tzinfo=timezone.utc)


def job(
    identity: str, *, location: str = "adr_1", status: str = "ready"
) -> JobMigrationRecord:
    return JobMigrationRecord(
        source_id=identity,
        source_customer_id="cus_1",
        source_service_location_id=location,
        status=status,
        source_job_number=identity,
    )


def appointment(identity: str, parent: str) -> AppointmentMigrationRecord:
    return AppointmentMigrationRecord(
        source_id=identity,
        source_job_id=parent,
        source_customer_id="cus_1",
        source_service_location_id="adr_1",
        status="scheduled",
        arrival_window_start_at=NOW,
        arrival_window_end_at=NOW,
        duration_minutes=0,
    )


def test_zero_hold_bucket_is_semantically_absent_but_nonzero_is_not_hidden() -> None:
    digest = require_equivalent_hold_counts(
        {"job": 296, "invoice": 298},
        {"job": 296, "invoice": 298, "hold": 0},
    )
    assert len(digest) == 64
    assert canonical_nonzero_counts({"hold": 0, "job": 296}) == {"job": 296}
    with pytest.raises(ValueError, match="HOLD entity accounting"):
        require_equivalent_hold_counts(
            {"job": 296, "invoice": 298},
            {"job": 296, "invoice": 298, "payment": 1},
        )


def test_operational_requalification_uses_authoritative_parents_and_lifecycle() -> None:
    result = requalify_operational_commands(
        jobs=(
            job("job_ready"),
            job("job_missing_location", location="adr_missing"),
            job("job_cancelled", status="cancelled"),
            job("job_in_progress", status="in_progress"),
        ),
        appointments=(
            appointment("appt_ok", "job_ready"),
            appointment("appt_parent_rejected", "job_cancelled"),
        ),
        created_at_by_job={
            "job_ready": NOW,
            "job_missing_location": NOW,
            "job_cancelled": NOW,
            "job_in_progress": NOW,
        },
        persisted_customer_ids=frozenset({"cus_1"}),
        persisted_location_ids=frozenset({"adr_1"}),
    )
    assert [item.source_id for item in result.jobs] == ["job_ready"]
    assert result.jobs[0].activated_at == NOW
    assert [item.source_id for item in result.appointments] == ["appt_ok"]
    assert result.job_exceptions == {
        "authoritative_location_parent_unavailable": 1,
        "cancelled_history_requires_non_operational_outcome": 1,
        "source_started_timestamp_unavailable": 1,
    }
    assert result.appointment_exceptions == {"authoritative_job_parent_not_admitted": 1}


def test_operational_requalification_is_deterministic_under_reordering() -> None:
    kwargs = {
        "created_at_by_job": {"job_1": NOW, "job_2": NOW},
        "persisted_customer_ids": frozenset({"cus_1"}),
        "persisted_location_ids": frozenset({"adr_1"}),
    }
    first = requalify_operational_commands(
        jobs=(job("job_2"), job("job_1")),
        appointments=(appointment("appt_2", "job_2"), appointment("appt_1", "job_1")),
        **kwargs,
    )
    second = requalify_operational_commands(
        jobs=(job("job_1"), job("job_2")),
        appointments=(appointment("appt_1", "job_1"), appointment("appt_2", "job_2")),
        **kwargs,
    )
    assert first.digest == second.digest
    assert first.jobs == second.jobs
    assert first.appointments == second.appointments


def test_financial_eligibility_follows_admitted_job_then_invoice() -> None:
    invoices = (
        InvoiceMigrationRecord("inv_1", "job_1", "issued", "USD", 0, 0, 0, ()),
        InvoiceMigrationRecord("inv_2", "job_2", "issued", "USD", 0, 0, 0, ()),
    )
    payments = (
        PaymentMigrationRecord("pay_1", "inv_1", "paid", "USD", 0),
        PaymentMigrationRecord("pay_2", "inv_2", "paid", "USD", 0),
    )
    result = requalify_financial_commands(
        invoices=invoices,
        payments=payments,
        admitted_job_ids=frozenset({"job_1"}),
    )
    assert [item.source_id for item in result.invoices] == ["inv_1"]
    assert [item.source_id for item in result.payments] == ["pay_1"]
    assert result.invoice_exceptions == 1
    assert result.payment_exceptions == 1


@pytest.mark.skipif(
    not (
        Path.home()
        / ".acp-enterprise/migration/housecall-pro/hcp-source-4-20260827T223858Z"
    ).exists(),
    reason="protected SOURCE.4 qualification evidence is not installed",
)
def test_sealed_source4_requalification_has_exact_safe_counts() -> None:
    from app.operational_migration.hcp_migration2_plan import (
        HcpMigration2ExecutionPlanBuilder,
    )

    root = Path.home() / ".acp-enterprise/migration/housecall-pro"
    builder = HcpMigration2ExecutionPlanBuilder(
        package_root=root / "hcp-source-4-20260827T223858Z",
        control_csv=root
        / "hcp-source-3-controls/derived/AllCountyPlumbingandLeak_customer_export.csv",
        migration1a_root=root / "hcp-migration-1a-20260828T120000Z",
    )
    plan, _ = builder.build(baseline_counts={"business": 0, "masters": 1})
    customer_ids = frozenset(
        item.source_identity for item in plan.customers.reviewed.aggregates
    )
    location_ids = frozenset(
        identity
        for item in plan.customers.reviewed.aggregates
        for identity in item.service_location_source_identities
    )
    repair = builder.build_child_repair_plan(
        original=plan,
        persisted_customer_ids=customer_ids,
        persisted_location_ids=location_ids,
    )
    assert len(repair.operational.jobs) == 1094
    assert len(repair.operational.appointments) == 1249
    assert sum(repair.operational.job_exceptions.values()) == 4136
    assert sum(repair.operational.appointment_exceptions.values()) == 1861
    assert len(repair.financial.estimates) == 14
    assert len(repair.financial.invoices) == 780
    assert len(repair.financial.payments) == 684
    assert (
        repair.persisted_counts.items()
        >= {
            "job": 1094,
            "appointment": 1249,
            "estimate": 14,
            "invoice": 780,
            "payment": 684,
        }.items()
    )
    assert (
        repair.exception_counts.items()
        >= {
            "job": 4411,
            "appointment": 1970,
            "estimate": 32,
            "invoice": 4587,
            "payment": 3337,
        }.items()
    )
    assert len(repair.additional_plan_outcomes) == 13711
    assert all(
        item.outcome == "EXPLICIT_EXCEPTION" for item in repair.additional_plan_outcomes
    )
    assert repair.original_plan_digest == plan.plan_digest
    assert len(repair.repair_plan_digest) == 64
