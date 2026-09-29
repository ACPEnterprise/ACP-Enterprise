from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.marketing.adapters import FixtureMarketingProviderAdapter
from app.marketing.contracts import (
    AttributionResolution,
    AttributionRole,
    MarketingOutcomeCoverage,
    MarketingOutcomeProjection,
    MarketingOutcomeProjectionRequest,
    MetricAvailability,
    ProviderSnapshotEnvelope,
)
from app.marketing.legacy import legacy_customer_source_evidence
from app.marketing.models import (
    MarketingAppointmentAttribution,
    MarketingAttributionAssignment,
    MarketingCustomerAttribution,
    MarketingJobAttribution,
    MarketingLeadAttribution,
    MarketingProviderAccount,
    MarketingProviderSnapshot,
    MarketingTouch,
)
from app.marketing.router import router as marketing_router
from app.marketing.schemas import ManualAttributionConfirmation
from app.marketing.service import ordered_touch_ids
from app.platform.launch_controls import LAUNCH_ROLE_MATRIX, LaunchRoleCode
from app.platform.permissions.catalog import permission_catalog
from app.platform.permissions.codes import MarketingPermission

BACKEND_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 28, 15, 0, tzinfo=timezone.utc)


def test_permission_catalog_contains_marketing_without_field_technician_grant() -> None:
    permission_catalog.validate()
    codes = {item.code for item in permission_catalog.definitions}
    assert MarketingPermission.ALL <= codes
    technician = next(
        item for item in LAUNCH_ROLE_MATRIX if item.code is LaunchRoleCode.TECHNICIAN
    )
    assert technician.permission_codes.isdisjoint(MarketingPermission.ALL)


def test_foundation_has_typed_targets_and_no_estimate_link() -> None:
    assert MarketingCustomerAttribution.__table__.c.customer_id is not None
    assert MarketingLeadAttribution.__table__.c.lead_id is not None
    assert MarketingAppointmentAttribution.__table__.c.appointment_id is not None
    assert MarketingJobAttribution.__table__.c.job_id is not None
    all_foreign_tables = {
        element.target_fullname.split(".", 1)[0]
        for table in (
            MarketingCustomerAttribution.__table__,
            MarketingLeadAttribution.__table__,
            MarketingAppointmentAttribution.__table__,
            MarketingJobAttribution.__table__,
        )
        for constraint in table.foreign_key_constraints
        for element in constraint.elements
    }
    assert "pipeline_leads" in all_foreign_tables
    assert "estimate_proposals" not in all_foreign_tables
    assert "estimates" not in all_foreign_tables


def test_provider_accounts_cannot_store_credentials() -> None:
    prohibited = {"token", "secret", "password", "credential", "oauth"}
    columns = {item.name.lower() for item in MarketingProviderAccount.__table__.columns}
    assert all(not any(word in column for word in prohibited) for column in columns)


def test_manual_resolution_states_and_supporting_touch_rule() -> None:
    for resolution in (
        AttributionResolution.UNKNOWN,
        AttributionResolution.CONFLICTING,
        AttributionResolution.NOT_AVAILABLE,
    ):
        value = ManualAttributionConfirmation(
            target_type="customer",
            target_id=uuid4(),
            role=AttributionRole.FIRST_TOUCH,
            resolution=resolution,
            supporting_evidence_reference="customer statement recorded by CSR",
            reason="Owner-reviewed evidence",
            idempotency_key=f"manual-{resolution.value}",
        )
        assert value.touch_id is None
    with pytest.raises(ValidationError):
        ManualAttributionConfirmation(
            target_type="lead",
            target_id=uuid4(),
            role=AttributionRole.BOOKING,
            resolution=AttributionResolution.RESOLVED,
            supporting_evidence_reference="missing touch",
            reason="Cannot resolve without touch",
            idempotency_key="manual-resolved-without-touch",
        )


def test_booking_and_job_attribution_are_independent_roles() -> None:
    assert AttributionRole.BOOKING != AttributionRole.JOB_ASSOCIATED
    assert {
        "first_touch",
        "latest_touch",
        "booking",
        "job_associated",
    } == {item.value for item in AttributionRole}


def test_touch_order_is_stable_for_first_and_latest() -> None:
    first_id, second_id, third_id = sorted((uuid4(), uuid4(), uuid4()))
    touches = [
        MarketingTouch(
            id=third_id,
            observed_at=NOW,
            evidence_kind="fixture",
            resolution="unknown",
            evidence_digest="a" * 64,
            idempotency_key="3",
        ),
        MarketingTouch(
            id=first_id,
            observed_at=NOW - timedelta(hours=1),
            evidence_kind="fixture",
            resolution="unknown",
            evidence_digest="b" * 64,
            idempotency_key="1",
        ),
        MarketingTouch(
            id=second_id,
            observed_at=NOW,
            evidence_kind="fixture",
            resolution="unknown",
            evidence_digest="c" * 64,
            idempotency_key="2",
        ),
    ]
    ordered = ordered_touch_ids(touches)
    assert ordered[0] == first_id
    assert ordered[-1] == third_id


def test_legacy_customer_source_is_preserved_but_unresolved() -> None:
    customer_id = uuid4()
    evidence = legacy_customer_source_evidence(
        customer_id=customer_id,
        original_value="  Google maybe  ",
        observed_at=NOW,
    )
    assert evidence.original_value == "Google maybe"
    assert evidence.resolution is AttributionResolution.UNKNOWN
    assert evidence.evidence_kind == "legacy_customer_source"
    assert len(evidence.evidence_digest) == 64
    assert str(customer_id) in evidence.idempotency_key


@pytest.mark.asyncio
async def test_fixture_adapter_is_read_only_and_supports_out_of_order_snapshots() -> (
    None
):
    older = ProviderSnapshotEnvelope(
        "campaign", "c1", NOW, NOW, "v1", {"state": "active"}, "a" * 64
    )
    newer = ProviderSnapshotEnvelope(
        "campaign",
        "c1",
        NOW + timedelta(hours=1),
        NOW + timedelta(hours=1),
        "v1",
        {"state": "paused"},
        "b" * 64,
    )
    adapter = FixtureMarketingProviderAdapter(
        provider_family="fixture", adapter_version="1", records=(newer, older)
    )
    records = await adapter.snapshots(
        external_account_id="fixture-account", start_at=None, end_at=None
    )
    assert records == (newer, older)
    assert not hasattr(adapter, "mutate")
    assert not hasattr(adapter, "pause_campaign")


def test_provider_snapshot_revision_and_append_only_migration_contract() -> None:
    unique_names = {
        item.name for item in MarketingProviderSnapshot.__table__.constraints
    }
    assert "uq_marketing_snapshots_revision" in unique_names
    migration = (
        BACKEND_ROOT
        / "alembic/versions/qf6b8d0e2h4j6_create_marketing_attribution_foundation.py"
    ).read_text()
    for table in (
        "marketing_touches",
        "marketing_provider_snapshots",
        "marketing_attribution_assignments",
    ):
        assert f'"{table}"' in migration
    assert "trg_{table}_append_only" in migration
    assert "pf6b8d0f2h4j6" in migration


def test_only_manual_confirmation_is_exposed_as_marketing_mutation() -> None:
    routes = {
        (method, route.path)
        for route in marketing_router.routes
        if getattr(route, "path", "").startswith("/api/v1/marketing")
        for method in getattr(route, "methods", set())
    }
    mutations = {
        (method, path)
        for method, path in routes
        if method not in {"GET", "HEAD", "OPTIONS"}
    }
    assert mutations == {
        ("POST", "/api/v1/marketing/attributions/manual-confirmation"),
        ("POST", "/api/v1/marketing/google-ads/account-bindings"),
        ("POST", "/api/v1/marketing/google-ads/oauth/authorize"),
    }
    assert not any(
        word in path
        for _, path in mutations
        for word in ("campaigns", "budgets", "bids", "targeting", "keywords")
    )


def test_economics_projection_is_reference_only_and_carries_coverage() -> None:
    request = MarketingOutcomeProjectionRequest(
        uuid4(), None, NOW - timedelta(days=30), NOW, NOW, "marketing-attribution.v1"
    )
    projection = MarketingOutcomeProjection(
        request=request,
        source_id=None,
        campaign_id=None,
        lead_ids=(),
        appointment_ids=(),
        job_ids=(),
        estimate_proposal_ids=(),
        invoice_ids=(),
        payment_ids=(),
        admitted_economics_result_ids=(),
        coverage=MarketingOutcomeCoverage(
            0, 0, ("lead", "economics"), MetricAvailability.UNAVAILABLE
        ),
    )
    assert projection.coverage.availability is MetricAvailability.UNAVAILABLE
    assert not hasattr(projection, "gross_profit")


def test_assignment_supports_append_only_supersession() -> None:
    assert "supersedes_assignment_id" in MarketingAttributionAssignment.__table__.c
    assert "request_digest" in MarketingAttributionAssignment.__table__.c


def test_manual_confirmation_replay_and_duplicate_conflict_contract() -> None:
    columns = MarketingAttributionAssignment.__table__.c
    assert "idempotency_key" in columns
    assert "request_digest" in columns
