import hashlib
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.economics.contracts import EvidenceInput, RecordBusinessFact
from app.economics.domain import (
    Confidence,
    EconomicCategory,
    EvidenceKind,
    MeasurementStatus,
)
from app.economics.ledger import EconomicsLedgerError, EconomicsLedgerService
from app.economics.models import (
    BusinessFactRecord,
    EvidenceReferenceRecord,
    FactEvidenceRecord,
    ProfitMeasurementRecord,
)
from app.economics.service import EconomicsQueryService
from app.events.models import BusinessEvent
from app.platform.company.models import Company


@pytest_asyncio.fixture
async def economics_database() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_measurement_queries_are_tenant_scoped_and_retain_evidence(
    economics_database: async_sessionmaker[AsyncSession],
) -> None:
    suffix = uuid4().hex[:8].upper()
    companies = (
        Company(
            name="Economics A", code=f"ECA{suffix}", status="active", timezone="UTC"
        ),
        Company(
            name="Economics B", code=f"ECB{suffix}", status="active", timezone="UTC"
        ),
    )
    subject_id = uuid4()
    evidence = [
        {
            "kind": "business_event",
            "reference_id": str(uuid4()),
            "source_system": "acp_enterprise",
            "source_version": "1",
            "source_record_type": "business_event",
            "content_digest": "a" * 64,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "explanation": "Payment received event.",
        },
        {
            "kind": "reasoning",
            "reference_id": "business-economics/1",
            "source_system": "business_economics",
            "source_version": "business-economics/1",
            "source_record_type": "measurement_formula",
            "content_digest": "b" * 64,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "explanation": "Versioned profit formula.",
        },
    ]
    async with economics_database() as session, session.begin():
        session.add_all(companies)
        await session.flush()
        for company, net_profit in zip(companies, (48_000, 99_000), strict=True):
            session.add(
                ProfitMeasurementRecord(
                    company_id=company.id,
                    subject_type="job",
                    subject_id=subject_id,
                    period_start=date(2026, 7, 1),
                    period_end=date(2026, 7, 31),
                    currency="USD",
                    revenue_minor=100_000,
                    labor_minor=20_000,
                    materials_minor=15_000,
                    equipment_minor=5_000,
                    truck_minor=2_000,
                    overhead_minor=10_000,
                    gross_profit_minor=58_000,
                    net_profit_minor=net_profit,
                    confidence_status="measured",
                    confidence_percentage=100,
                    confidence_explanation="All inputs are measured.",
                    evidence_snapshot=evidence,
                    input_fact_ids=[str(uuid4())],
                    input_allocation_ids=[],
                    engine_version="business-economics/1",
                    version=1,
                    measured_at=datetime.now(timezone.utc),
                )
            )

    async with economics_database() as session:
        response = await EconomicsQueryService.latest_for_subject(
            session, companies[0].id, "job", subject_id
        )
        listing = await EconomicsQueryService.list_measurements(
            session, companies[0].id, limit=50, offset=0
        )

    assert response.net_profit_minor == 48_000
    assert response.company_id == companies[0].id
    assert len(response.evidence) == 2
    assert [item.id for item in listing.items] == [response.id]


@pytest.mark.asyncio
async def test_fact_ledger_versions_and_binds_immutable_business_event_evidence(
    economics_database: async_sessionmaker[AsyncSession],
) -> None:
    suffix = uuid4().hex[:8].upper()
    company = Company(
        name="Economics Ledger", code=f"ECL{suffix}", status="active", timezone="UTC"
    )
    subject_id = uuid4()
    event = BusinessEvent(
        event_type="payment.received",
        entity_type="job",
        entity_id=subject_id,
        payload={"amount_minor": 12_500, "currency": "USD"},
    )
    async with economics_database() as session, session.begin():
        session.add_all([company, event])
        await session.flush()
        event.company_id = company.id
        content_digest = hashlib.sha256(b"payment.received:v1:12500:USD").hexdigest()
        evidence = EvidenceInput(
            kind=EvidenceKind.BUSINESS_EVENT,
            reference_id=str(event.id),
            source_system="acp_enterprise",
            source_record_type="business_event",
            source_version="1",
            content_digest=content_digest,
            observed_at=event.occurred_at,
            explanation="Recorded payment business event.",
            business_event_id=event.id,
        )
        command = RecordBusinessFact(
            branch_id=None,
            subject_type="job",
            subject_id=subject_id,
            category=EconomicCategory.REVENUE,
            fact_key="payment_revenue",
            amount_minor=12_500,
            currency="USD",
            confidence=Confidence(
                MeasurementStatus.MEASURED, 100, "Directly recorded payment."
            ),
            evidence=(evidence,),
            occurred_at=event.occurred_at,
            period_start=date(2026, 7, 31),
            period_end=date(2026, 7, 31),
            measurement_method="business_event_amount",
        )
        first = await EconomicsLedgerService.record_fact(session, company.id, command)
        second = await EconomicsLedgerService.record_fact(session, company.id, command)

    async with economics_database() as session:
        evidence_count = await session.scalar(
            select(func.count())
            .select_from(EvidenceReferenceRecord)
            .where(EvidenceReferenceRecord.company_id == company.id)
        )
        link_count = await session.scalar(
            select(func.count())
            .select_from(FactEvidenceRecord)
            .where(FactEvidenceRecord.company_id == company.id)
        )
        facts = tuple(
            (
                await session.scalars(
                    select(BusinessFactRecord)
                    .where(BusinessFactRecord.company_id == company.id)
                    .order_by(BusinessFactRecord.version)
                )
            ).all()
        )

    assert (first.version, second.version) == (1, 2)
    assert [item.version for item in facts] == [1, 2]
    assert evidence_count == 1
    assert link_count == 2

    conflicting = EvidenceInput(
        kind=evidence.kind,
        reference_id=evidence.reference_id,
        source_system=evidence.source_system,
        source_record_type=evidence.source_record_type,
        source_version=evidence.source_version,
        content_digest="f" * 64,
        observed_at=evidence.observed_at,
        explanation=evidence.explanation,
        business_event_id=evidence.business_event_id,
    )
    async with economics_database() as session:
        with pytest.raises(EconomicsLedgerError, match="recorded digest"):
            await EconomicsLedgerService.record_fact(
                session,
                company.id,
                replace(command, evidence=(conflicting,)),
            )
