from pathlib import Path
from types import SimpleNamespace

import pytest

from app.customer_migration.adapter_import_policy import (
    customer_adapter_import_policy,
)
from app.operational_migration.hcp_migration2_plan import (
    HcpMigration2Application,
    HcpMigration2ExecutionPlanBuilder,
    RehearsalAdmissionState,
)


def aggregate(
    identity: str,
    *,
    contact: bool = False,
    locations: int = 0,
    billing: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        source_identity_sha256=identity,
        customer=object(),
        contact=object() if contact else None,
        service_locations=tuple(object() for _ in range(locations)),
        billing_address=object() if billing else None,
    )


def test_event_population_separates_admission_from_domain_events() -> None:
    selected = (
        aggregate("a" * 64, contact=True, locations=2),
        aggregate("b" * 64, locations=1, billing=True),
    )
    population = customer_adapter_import_policy.event_population(selected)
    assert population.customer_admission_events == 2
    assert population.customer_domain_events == 2
    assert population.contact_projection_events == 1
    assert population.service_location_projection_events == 3
    assert population.billing_address_projection_events == 1
    assert population.aggregate_domain_events == 7
    assert population.audit_events_in_boundary == 0
    assert population.lineage_events_in_boundary == 0
    assert customer_adapter_import_policy.event_population(
        tuple(reversed(selected))
    ) == population


def test_event_population_rejects_duplicate_identity_and_changes_with_children() -> None:
    with pytest.raises(ValueError, match="duplicate Customer admission"):
        customer_adapter_import_policy.event_population(
            (aggregate("a" * 64), aggregate("a" * 64))
        )
    original = customer_adapter_import_policy.event_population(
        (aggregate("a" * 64),)
    )
    changed = customer_adapter_import_policy.event_population(
        (aggregate("a" * 64, contact=True),)
    )
    assert original.digest != changed.digest


@pytest.mark.parametrize(
    ("masters", "expected"),
    (
        ((), RehearsalAdmissionState.NO_MASTER),
        ((SimpleNamespace(status="running"),), RehearsalAdmissionState.MATCHING_INCOMPLETE_MASTER),
        ((SimpleNamespace(status="interrupted"),), RehearsalAdmissionState.MATCHING_INCOMPLETE_MASTER),
        ((SimpleNamespace(status="completed"),), RehearsalAdmissionState.COMPLETED_MASTER),
        ((SimpleNamespace(status="failed"),), RehearsalAdmissionState.CONTRADICTORY_MASTER),
        (
            (SimpleNamespace(status="running"), SimpleNamespace(status="running")),
            RehearsalAdmissionState.MULTIPLE_UNEXPECTED_MASTERS,
        ),
    ),
)
def test_resume_admission_states_are_explicit(
    masters: tuple[SimpleNamespace, ...], expected: RehearsalAdmissionState
) -> None:
    assert HcpMigration2Application.classify_master_admission(masters) == expected  # type: ignore[arg-type]


@pytest.mark.skipif(
    not (
        Path.home()
        / ".acp-enterprise/migration/housecall-pro/hcp-source-4-20260827T223858Z"
    ).exists(),
    reason="protected SOURCE.4 qualification evidence is not installed",
)
def test_sealed_source4_event_population_is_exact_and_plan_identity_is_stable() -> None:
    root = Path.home() / ".acp-enterprise/migration/housecall-pro"
    plan, _ = HcpMigration2ExecutionPlanBuilder(
        package_root=root / "hcp-source-4-20260827T223858Z",
        control_csv=root
        / "hcp-source-3-controls/derived/AllCountyPlumbingandLeak_customer_export.csv",
        migration1a_root=root / "hcp-migration-1a-20260828T120000Z",
    ).build(
        baseline_counts={
            "appointments": 0,
            "contacts": 0,
            "customer_runs": 0,
            "customers": 0,
            "employees": 0,
            "estimates": 0,
            "invoices": 0,
            "jobs": 0,
            "locations": 0,
            "masters": 0,
            "operational_runs": 0,
            "payments": 0,
        }
    )
    expected = plan.customers.boundary.expected
    assert expected.customer_admission_events == 5296
    assert expected.customers == 5296
    assert expected.contacts == 4148
    assert expected.service_locations == 5339
    assert expected.billing_addresses == 0
    assert expected.business_events == 14783
    assert (
        expected.event_population_digest
        == "bad342ccb09303812cda817fedd8115921f7287e6f2bb41b8b2f8f1426a4c4e3"
    )
    assert str(plan.plan_id) == "8c717798-db5e-5c49-99be-ca3d250536e3"
    assert (
        plan.plan_digest
        == "6ac31cc70e269dfa123a73c8a896f7e957eff113c1873a6ee8c908a9f1256962"
    )
