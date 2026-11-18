from datetime import datetime, timezone
from uuid import uuid4

import pytest
from app.migration_factory.certification import (
    CertificationStatus,
    ProviderConformanceHarness,
)
from app.migration_factory.domain import Domain
from app.migration_factory.operations import (
    MonthlyCapacityModel,
    owner_projection,
    staff_projection,
)
from app.migration_factory.providers import (
    AcquisitionCursor,
    AdapterContext,
    ProviderPage,
    ProviderRawRecord,
)
from app.migration_factory.providers.jobber import JobberAdapter
from app.migration_factory.providers.servicetitan import ServiceTitanAdapter
from app.migration_factory.retained_qualification import (
    HCP_ALL_COUNTY_RETAINED,
    QBO_ALL_COUNTY_RETAINED,
    QBO_PAYROLL_RETAINED,
)


def fixture_pages(adapter, family: str) -> dict[str, tuple[ProviderPage, ...]]:
    now = datetime.now(timezone.utc)
    records = tuple(
        ProviderRawRecord(
            adapter.provider,
            family,
            f"{family}-{number}",
            {"id": f"{family}-{number}"},
            now,
            "fixture/v1",
        )
        for number in range(3)
    )
    return {
        family: (
            ProviderPage(
                AcquisitionCursor(family, "page-1", "1"),
                records[:2],
                (),
                AcquisitionCursor(family, "page-2", "2"),
                False,
                4,
            ),
            ProviderPage(
                AcquisitionCursor(family, "page-2", "2"),
                records[2:],
                ({"source_id": "bad-1", "reason": "malformed"},),
                None,
                True,
                4,
            ),
        )
    }


def all_fixture_pages(adapter) -> dict[str, tuple[ProviderPage, ...]]:
    result: dict[str, tuple[ProviderPage, ...]] = {}
    for capability in adapter.capabilities:
        result.update(fixture_pages(adapter, capability.domain.value))
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter_type", "domain", "family"),
    (
        (ServiceTitanAdapter, Domain.CUSTOMERS, "customers"),
        (JobberAdapter, Domain.JOBS, "jobs"),
    ),
)
async def test_first_wave_adapter_passes_common_synthetic_conformance(
    adapter_type, domain, family
) -> None:
    seed = adapter_type()
    adapter = adapter_type(fixture_pages(seed, family))
    certificate = await ProviderConformanceHarness().qualify(
        adapter=adapter,
        company_id=uuid4(),
        context=AdapterContext("company", "connection", "authorization"),
        families={domain: family},
        environment="synthetic",
        transformation_version="qualification/v1",
        live=False,
    )
    assert certificate.conformance.passed
    assert certificate.domains[0].status is CertificationStatus.QUALIFIED_SYNTHETIC
    assert certificate.domains[0].source_count == 4
    assert certificate.domains[0].quarantined_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter_type", (ServiceTitanAdapter, JobberAdapter))
async def test_every_mapped_first_wave_domain_is_synthetically_qualified(
    adapter_type,
) -> None:
    seed = adapter_type()
    adapter = adapter_type(all_fixture_pages(seed))
    certificate = await ProviderConformanceHarness().qualify(
        adapter=adapter,
        company_id=uuid4(),
        context=AdapterContext("company", "connection", "authorization"),
        families={item.domain: item.domain.value for item in adapter.capabilities},
        environment="synthetic",
        transformation_version="qualification/v1",
        live=False,
    )
    assert certificate.conformance.passed
    assert len(certificate.domains) == len(adapter.capabilities)
    assert all(
        item.status is CertificationStatus.QUALIFIED_SYNTHETIC
        for item in certificate.domains
    )


@pytest.mark.asyncio
async def test_certificate_projects_to_stable_owner_and_staff_contracts() -> None:
    seed = JobberAdapter()
    certificate = await ProviderConformanceHarness().qualify(
        adapter=JobberAdapter(fixture_pages(seed, "jobs")),
        company_id=uuid4(),
        context=AdapterContext("company", "connection", "authorization"),
        families={Domain.JOBS: "jobs"},
        environment="synthetic",
        transformation_version="qualification/v1",
        live=False,
    )
    owner = owner_projection("migration-1", (certificate,))
    staff = staff_projection("migration-1", (certificate,), retry_count=1)
    assert owner.progress[0].label == "Jobs"
    assert "pagination" not in str(owner).lower()
    assert staff.domains[0].source_count == 4
    assert staff.retry_count == 1


def test_retained_live_evidence_never_overstates_provider_coverage() -> None:
    hcp = {item.domain: item for item in HCP_ALL_COUNTY_RETAINED}
    assert hcp["customers"].status is CertificationStatus.QUALIFIED_LIVE
    assert hcp["appointments"].status is CertificationStatus.PARTIAL
    assert hcp["attachments"].status is CertificationStatus.BLOCKED_PROVIDER
    assert all(
        item.status is CertificationStatus.IMPLEMENTED_UNQUALIFIED
        for item in QBO_ALL_COUNTY_RETAINED
    )
    assert all(
        item.status is CertificationStatus.BLOCKED_PROVIDER
        for item in QBO_PAYROLL_RETAINED
    )


def test_monthly_capacity_model_reserves_peak_and_exception_capacity() -> None:
    model = MonthlyCapacityModel()
    model.verify()
    assert model.average_starts_per_day == 10
    assert model.peak_start_capacity == 30
    assert model.exception_assumption_percent == 10
