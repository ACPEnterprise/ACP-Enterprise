import hashlib
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.economics.operational_acquisition import (
    AcquisitionError,
    AcquisitionRequest,
    AcquisitionState,
    CustomersAcquisitionAdapter,
    CustomerSourceSnapshot,
    DispatchAcquisitionAdapter,
    DispatchSourceSnapshot,
    JobsAcquisitionAdapter,
    JobSourceSnapshot,
    PriceBookAcquisitionAdapter,
    PriceBookSourceSnapshot,
    SourceEvidenceContract,
)

NOW = datetime(2026, 8, 5, tzinfo=timezone.utc)
COMPANY = UUID("10000000-0000-0000-0000-000000000001")
BRANCH = UUID("20000000-0000-0000-0000-000000000001")
SOURCE = UUID("30000000-0000-0000-0000-000000000001")
CUSTOMER = UUID("40000000-0000-0000-0000-000000000001")
LOCATION = UUID("50000000-0000-0000-0000-000000000001")


def request() -> AcquisitionRequest:
    return AcquisitionRequest(
        company_id=COMPANY,
        authorized_branch_ids=frozenset({BRANCH}),
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
    )


def evidence(kind: str) -> SourceEvidenceContract:
    return SourceEvidenceContract(
        source_system="acp-enterprise",
        record_type=kind,
        record_id=str(SOURCE),
        source_version="1",
        content_digest=hashlib.sha256(kind.encode()).hexdigest(),
        observed_at=NOW,
    )


def job() -> JobSourceSnapshot:
    return JobSourceSnapshot(
        id=SOURCE,
        company_id=COMPANY,
        branch_id=BRANCH,
        customer_id=CUSTOMER,
        service_location_id=LOCATION,
        job_number="JOB-000001",
        status="completed",
        job_type_code="service",
        started_at=NOW,
        completed_at=NOW,
        updated_at=NOW,
        concurrency_version=2,
        evidence=evidence("job"),
    )


def dispatch() -> DispatchSourceSnapshot:
    return DispatchSourceSnapshot(
        id=SOURCE,
        company_id=COMPANY,
        branch_id=BRANCH,
        customer_id=CUSTOMER,
        job_id=UUID("60000000-0000-0000-0000-000000000001"),
        technician_id=UUID("70000000-0000-0000-0000-000000000001"),
        status="completed",
        scheduled_start_at=NOW,
        scheduled_end_at=NOW,
        actual_start_at=NOW,
        actual_end_at=NOW,
        updated_at=NOW,
        concurrency_version=1,
        evidence=evidence("dispatch"),
    )


def price_book() -> PriceBookSourceSnapshot:
    return PriceBookSourceSnapshot(
        id=SOURCE,
        company_id=COMPANY,
        branch_id=BRANCH,
        job_id=UUID("60000000-0000-0000-0000-000000000001"),
        estimate_id=UUID("80000000-0000-0000-0000-000000000001"),
        selected_option_id=UUID("90000000-0000-0000-0000-000000000001"),
        item_code="repair_standard",
        item_version=3,
        expected_revenue_minor=100_000,
        expected_labor_minor=30_000,
        expected_materials_minor=20_000,
        currency="USD",
        effective_at=NOW,
        evidence=evidence("price-book"),
    )


def customer() -> CustomerSourceSnapshot:
    return CustomerSourceSnapshot(
        id=SOURCE,
        company_id=COMPANY,
        branch_id=BRANCH,
        customer_number="CUS-000001",
        customer_type="residential",
        status="active",
        marketing_source="referral",
        service_location_id=LOCATION,
        updated_at=NOW,
        evidence=evidence("customer"),
    )


@pytest.mark.parametrize(
    ("adapter", "source"),
    (
        (JobsAcquisitionAdapter(), job()),
        (DispatchAcquisitionAdapter(), dispatch()),
        (PriceBookAcquisitionAdapter(), price_book()),
        (CustomersAcquisitionAdapter(), customer()),
    ),
)
def test_acquires_complete_provider_neutral_facts(adapter, source) -> None:
    batch = adapter.acquire(request(), (source,))

    assert len(batch.facts) == 1
    assert batch.facts[0].state is AcquisitionState.COMPLETE
    assert batch.facts[0].company_id == COMPANY
    assert batch.facts[0].evidence is source.evidence


def test_replay_and_ordering_are_deterministic() -> None:
    first_source = job()
    second_source = replace(
        first_source,
        id=UUID("30000000-0000-0000-0000-000000000002"),
        job_number="JOB-000002",
    )
    adapter = JobsAcquisitionAdapter()

    first = adapter.acquire(request(), (first_source, second_source))
    replay = adapter.acquire(request(), (second_source, first_source))

    assert first == replay
    assert first.batch_id == replay.batch_id
    assert first.evidence_digest == replay.evidence_digest


def test_missing_data_is_explicit_and_never_invented() -> None:
    source = replace(
        dispatch(),
        job_id=None,
        technician_id=None,
        actual_start_at=None,
        actual_end_at=None,
    )
    fact = DispatchAcquisitionAdapter().acquire(request(), (source,)).facts[0]

    assert fact.state is AcquisitionState.INCOMPLETE
    assert fact.missing_fields == (
        "actual_end_at",
        "actual_start_at",
        "job_id",
        "technician_id",
    )
    assert not {item.name for item in fact.attributes}.intersection(fact.missing_fields)


def test_scope_isolation_fails_closed_for_company_and_branch() -> None:
    adapter = JobsAcquisitionAdapter()
    with pytest.raises(AcquisitionError, match="outside"):
        adapter.acquire(
            request(),
            (replace(job(), company_id=UUID(int=99)),),
        )

    foreign_branch = replace(job(), branch_id=UUID(int=98))
    with pytest.raises(AcquisitionError, match="outside"):
        adapter.acquire(request(), (foreign_branch,))

    out_of_period = replace(job(), updated_at=NOW + timedelta(days=40))
    with pytest.raises(AcquisitionError, match="period"):
        adapter.acquire(request(), (out_of_period,))


def test_source_snapshots_and_acquired_facts_are_immutable() -> None:
    source = customer()
    fact = CustomersAcquisitionAdapter().acquire(request(), (source,)).facts[0]

    with pytest.raises(FrozenInstanceError):
        source.status = "inactive"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        fact.state = AcquisitionState.INCOMPLETE  # type: ignore[misc]
