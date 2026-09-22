from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.pipeline.models import Lead
from app.pipeline.schemas import LeadCreate
from app.pipeline.service import ALLOWED_TRANSITIONS, PipelineService, attention_state

NOW = datetime(2026, 9, 22, 14, 0, tzinfo=timezone.utc)


def lead(**changes: object) -> Lead:
    values: dict[str, object] = {
        "id": uuid4(),
        "company_id": uuid4(),
        "branch_id": uuid4(),
        "prospect_name": "Taylor Homeowner",
        "lead_source": "incoming_phone",
        "service_need": "Water heater is leaking",
        "stage": "contacted",
        "contact_attempt_count": 1,
        "created_at": NOW - timedelta(days=1),
        "created_by_user_id": uuid4(),
        "updated_at": NOW,
        "updated_by_user_id": uuid4(),
        "version": 1,
    }
    values.update(changes)
    return Lead(**values)


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (lead(stage="new", first_contact_at=None), "new_uncontacted"),
        (lead(next_action_type=None, next_action_due_at=None), "missing_next_action"),
        (
            lead(
                next_action_type="callback",
                next_action_due_at=NOW - timedelta(minutes=1),
            ),
            "overdue",
        ),
        (lead(stage="qualified", appointment_id=None), "qualified_not_scheduled"),
        (lead(stage="estimate_follow_up"), "estimate_follow_up"),
        (lead(stage="scheduled"), None),
        (lead(stage="won"), None),
    ],
)
def test_attention_projection(record: Lead, expected: str | None) -> None:
    assert attention_state(record, NOW) == expected


def test_source_does_not_determine_whether_record_is_a_lead() -> None:
    sources = (
        "incoming_phone",
        "referral",
        "existing_customer",
        "paid_ad",
        "manual_csr",
    )
    for source in sources:
        item = LeadCreate(
            branch_id=uuid4(),
            prospect_name="A real service opportunity",
            lead_source=source,
            service_need="Service requested",
        )
        assert item.lead_source == source


def test_prospect_can_exist_before_customer() -> None:
    item = LeadCreate(
        branch_id=uuid4(),
        prospect_name="New prospect",
        lead_source="web_form",
        service_need="Drain cleaning",
    )
    assert item.customer_id is None


def test_customer_or_prospect_is_required() -> None:
    with pytest.raises(ValidationError):
        LeadCreate(
            branch_id=uuid4(),
            lead_source="incoming_phone",
            service_need="Service requested",
        )


def test_imported_identity_requires_source_system() -> None:
    with pytest.raises(ValidationError):
        LeadCreate(
            branch_id=uuid4(),
            prospect_name="Imported opportunity",
            lead_source="other",
            source_provider_id="hcp-123",
            service_need="Service requested",
        )


def test_lifecycle_preserves_scheduled_and_alternate_exits() -> None:
    assert {"scheduled", "lost", "nurture"} <= ALLOWED_TRANSITIONS["new"]
    assert "won" in ALLOWED_TRANSITIONS["estimate_follow_up"]
    assert not ALLOWED_TRANSITIONS["won"]


def test_pipeline_value_is_unavailable_when_any_value_is_missing() -> None:
    bucket = PipelineService._bucket(
        "needs_attention",
        "Needs attention",
        [
            lead(attributable_value_minor=42_000, value_currency="USD"),
            lead(attributable_value_minor=None, value_currency=None),
        ],
    )
    assert bucket.count == 2
    assert bucket.value_minor is None
    assert bucket.value_complete is False
    assert bucket.drilldown_path == "/pipeline?view=needs_attention"


def test_pipeline_value_is_authoritative_only_when_population_is_complete() -> None:
    bucket = PipelineService._bucket(
        "moving_forward",
        "Scheduled / moving forward",
        [
            lead(attributable_value_minor=42_000, value_currency="USD"),
            lead(attributable_value_minor=31_700, value_currency="USD"),
        ],
    )
    assert bucket.value_minor == 73_700
    assert bucket.currency == "USD"
    assert bucket.value_complete is True
