import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.platform.factory_control.roadmap import (
    RoadmapError,
    load_roadmap,
    safe_event_details,
)
from app.platform.factory_control.service import calculate_metrics
from scripts.sync_factory_roadmap import sync

NOW = datetime(2026, 9, 18, 0, 0, tzinfo=timezone.utc)


def event(event_type, *, milestone="M1", occurred_at=NOW, details=None):
    return SimpleNamespace(
        id=uuid4(),
        event_type=event_type,
        milestone_code=milestone,
        occurred_at=occurred_at,
        details=details or {},
    )


def lane(code, state, queue=0):
    return SimpleNamespace(lane_code=code, lifecycle_state=state, queue_depth=queue)


def roadmap(tmp_path, count=4):
    path = tmp_path / "roadmap.yaml"
    path.write_text(
        json.dumps(
            {
                "milestones": [
                    {"code": f"M{i}", "lane": "OM1"} for i in range(1, count + 1)
                ]
            }
        )
    )
    return load_roadmap(path)


def test_json_compatible_yaml_roadmap_is_canonical_and_rejects_duplicates(tmp_path):
    first = roadmap(tmp_path, 2)
    assert [item.code for item in first.milestones] == ["M1", "M2"]
    assert len(first.digest) == 64
    path = tmp_path / "duplicate.yaml"
    path.write_text('{"milestones":[{"code":"M1"},{"code":"M1"}]}')
    with pytest.raises(RoadmapError, match="duplicated"):
        load_roadmap(path)


def test_packaged_roadmap_fails_closed_when_digest_is_missing_or_wrong(tmp_path):
    path = tmp_path / "roadmap.json"
    path.write_text('{"milestones":[{"code":"M1"}]}')
    digest_path = tmp_path / "roadmap.sha256"
    with pytest.raises(RoadmapError, match="digest is unavailable"):
        load_roadmap(path, digest_path=digest_path)
    digest_path.write_text("0" * 64)
    with pytest.raises(RoadmapError, match="does not match"):
        load_roadmap(path, digest_path=digest_path)


def test_packaged_roadmap_is_deterministically_generated_and_validated(tmp_path):
    source = tmp_path / "source.yaml"
    source.write_text('{"milestones": [{"lane": "OM1", "code": "M1"}]}')
    destination = tmp_path / "runtime" / "roadmap.json"
    digest = sync(source, destination)
    assert destination.read_text() == ('{"milestones":[{"code":"M1","lane":"OM1"}]}\n')
    assert destination.with_suffix(".sha256").read_text() == f"{digest}\n"
    assert (
        load_roadmap(destination, digest_path=destination.with_suffix(".sha256")).digest
        == digest
    )


def test_event_details_reject_secrets_payroll_values_and_unbounded_documents():
    assert safe_event_details({"result": "passed", "count": 4})["count"] == 4
    for prohibited in (
        {"access_token": "x"},
        {"payroll_value": 12},
        {"wage_rate": 20},
        {"evidence": [{"secret_reference": "x"}]},
    ):
        with pytest.raises(RoadmapError, match="prohibited"):
            safe_event_details(prohibited)
    with pytest.raises(RoadmapError, match="bounded size"):
        safe_event_details({"evidence": "x" * 17_000})


def test_metrics_cover_delivery_quality_capacity_and_flow(tmp_path):
    events = [
        event("engineering_complete", milestone="M1"),
        event("beta_complete", milestone="M1"),
        event("owner_accepted", milestone="M1"),
        event("closed", milestone="M1", occurred_at=NOW - timedelta(hours=12)),
        event("closed", milestone="M2", occurred_at=NOW - timedelta(days=2)),
        event("closed", milestone="M3", occurred_at=NOW - timedelta(days=6)),
        event(
            "defect_opened",
            occurred_at=NOW - timedelta(minutes=3),
            details={"defect_id": "D1"},
        ),
        event(
            "defect_opened",
            occurred_at=NOW - timedelta(minutes=2),
            details={"defect_id": "D2"},
        ),
        event(
            "defect_closed",
            occurred_at=NOW - timedelta(minutes=1),
            details={"defect_id": "D1"},
        ),
        event("gate_opened", details={"gate_id": "G1"}),
        event(
            "handoff",
            milestone="M4",
            occurred_at=NOW - timedelta(hours=2),
            details={"handoff_id": "H1"},
        ),
        event(
            "pickup",
            milestone="M4",
            occurred_at=NOW - timedelta(hours=1),
            details={"handoff_id": "H1"},
        ),
        event(
            "handoff",
            milestone="M5",
            occurred_at=NOW - timedelta(hours=3),
            details={"handoff_id": "H2"},
        ),
        event("rework_started"),
        event("first_pass_complete"),
        event("first_pass_complete"),
    ]
    metrics = calculate_metrics(
        roadmap=roadmap(tmp_path),
        events=events,
        lanes=[lane("A", "active", 2), lane("B", "idle", 3)],
        now=NOW,
    )
    assert metrics == {
        "engineering_percent": 25.0,
        "beta_percent": 25.0,
        "owner_percent": 25.0,
        "closed_percent": 75.0,
        "weighted_delivery_percent": 42.5,
        "delivery_1d_percent": 25.0,
        "delivery_3d_percent": 50.0,
        "delivery_7d_percent": 75.0,
        "open_defects": 1,
        "open_gates": 1,
        "utilization_percent": 50.0,
        "pickup_latency_seconds": 3600.0,
        "queue_depth": 5,
        "oldest_handoff_seconds": 10800.0,
        "rework_rate_percent": 33.33,
        "first_pass_yield_percent": 66.67,
    }


def test_empty_metrics_are_defined_without_division_errors(tmp_path):
    metrics = calculate_metrics(
        roadmap=roadmap(tmp_path, 0), events=[], lanes=[], now=NOW
    )
    assert metrics["closed_percent"] == 0.0
    assert metrics["utilization_percent"] == 0.0
    assert metrics["pickup_latency_seconds"] is None
    assert metrics["oldest_handoff_seconds"] is None


def test_canonical_roadmap_statuses_are_the_zero_event_baseline(tmp_path):
    path = tmp_path / "roadmap.yaml"
    path.write_text(
        json.dumps(
            {
                "milestones": [
                    {
                        "id": "M1",
                        "engineering_status": "ENGINEERING_READY",
                        "protected_integration_status": "INTEGRATED",
                        "beta_deployment_status": "DEPLOYED_BETA",
                        "owner_acceptance_status": "ACCEPTED",
                        "lifecycle_status": "CLOSED",
                    }
                ]
            }
        )
    )
    metrics = calculate_metrics(
        roadmap=load_roadmap(path), events=[], lanes=[], now=NOW
    )
    assert metrics["engineering_percent"] == 100.0
    assert metrics["beta_percent"] == 100.0
    assert metrics["owner_percent"] == 100.0
    assert metrics["closed_percent"] == 100.0
