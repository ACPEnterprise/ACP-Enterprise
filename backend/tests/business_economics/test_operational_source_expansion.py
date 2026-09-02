from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import UUID

from app.business_economics.operational_sources import operational_source_projection

ASSET = UUID("10000000-0000-0000-0000-000000000001")


def _row(**values: object) -> SimpleNamespace:
    return SimpleNamespace(**values)


def _projection(**overrides: object) -> dict[str, object]:
    now = datetime(2027, 1, 15, tzinfo=timezone.utc)
    values = {
        "period_start": date(2027, 1, 1),
        "period_end": date(2027, 1, 31),
        "assets": (
            _row(id=ASSET, asset_number="SYNTH-EQ-1", asset_class="customer_equipment"),
        ),
        "actions": (
            _row(
                id=UUID(int=11),
                asset_id=ASSET,
                action_type="service_link",
                state="completed",
                occurred_at=now,
                evidence_digest="a" * 64,
            ),
            _row(
                id=UUID(int=12),
                asset_id=ASSET,
                action_type="service_link",
                state="completed",
                occurred_at=now,
                evidence_digest="b" * 64,
            ),
            _row(
                id=UUID(int=13),
                asset_id=ASSET,
                action_type="warranty_evidence",
                state="recorded",
                occurred_at=now,
                evidence_digest="c" * 64,
            ),
            _row(
                id=UUID(int=14),
                asset_id=ASSET,
                action_type="maintenance",
                state="due",
                occurred_at=now,
                evidence_digest="d" * 64,
            ),
        ),
        "relationships": (
            _row(relationship_type="customer"),
            _row(relationship_type="service_location"),
            _row(relationship_type="job"),
        ),
        "profiles": (_row(id=UUID(int=21)),),
        "certifications": (_row(status="pending"),),
        "availability": (_row(status="available"),),
        "communications": (
            _row(status="sent"),
            _row(status="failed"),
        ),
    }
    values.update(overrides)
    return operational_source_projection(**values)  # type: ignore[arg-type]


def test_projection_composes_operational_evidence_without_inventing_cost_or_causality() -> (
    None
):
    value = _projection()
    equipment = value["asset_equipment"]
    assert isinstance(equipment, dict)
    assert equipment["economic_cost_state"] == "UNAVAILABLE"
    assert equipment["repeated_service"][0]["service_evidence_count"] == 2
    assert value["communications"]["causality_authority"] == "none"
    assert value["workforce"]["employee_scoring"] == "PROHIBITED"
    assert value["accounting"]["protected_migration_rows_accessed"] is False


def test_projection_keeps_warranty_callback_and_capacity_partial() -> None:
    value = _projection()
    sources = {item["source"]: item for item in value["sources"]}
    assert sources["warranty_callback"]["state"] == "PARTIAL"
    assert sources["capacity_measurement"]["state"] == "PARTIAL"
    assert sources["accounting_readiness"]["state"] == "EXTERNAL_GATE"


def test_projection_questions_and_beacon_evidence_are_read_only() -> None:
    first = _projection()
    second = _projection()
    assert first["projection_digest"] == second["projection_digest"]
    questions = {item["key"]: item for item in first["owner_questions"]}
    assert questions["repeated_equipment"]["state"] == "ANSWERABLE"
    assert questions["labor_attribution"]["state"] == "SOURCE_REQUIRED"
    assert questions["accounting_gate"]["state"] == "EXTERNAL_GATE"
    assert all(
        item["beacon_authority"] == "evaluation_only"
        for item in first["beacon_condition_evidence"]
    )
    assert first["mutation_authority"] == "none"


def test_absent_source_is_not_zero_or_ready() -> None:
    value = _projection(
        assets=(),
        actions=(),
        relationships=(),
        profiles=(),
        certifications=(),
        availability=(),
        communications=(),
    )
    sources = {item["source"]: item for item in value["sources"]}
    assert sources["customer_equipment"]["state"] == "SOURCE_REQUIRED"
    assert sources["communications_delivery"]["state"] == "SOURCE_REQUIRED"
    questions = {item["key"]: item for item in value["owner_questions"]}
    assert questions["communication_failures"]["state"] == "SOURCE_REQUIRED"
