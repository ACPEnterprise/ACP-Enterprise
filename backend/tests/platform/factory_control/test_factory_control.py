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
from app.platform.factory_control.schemas import FactoryEventIn
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
                    {
                        "code": f"M{i}",
                        "lane": "OM1",
                        "engineering_status": "NOT_STARTED",
                        "protected_integration_status": "NOT_STARTED",
                        "beta_deployment_status": "NOT_STARTED",
                        "owner_acceptance_status": "BLOCKED",
                        "lifecycle_status": "NOT_STARTED",
                    }
                    for i in range(1, count + 1)
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
    row = {
        "code": "M1",
        "engineering_status": "NOT_STARTED",
        "protected_integration_status": "NOT_STARTED",
        "beta_deployment_status": "NOT_STARTED",
        "owner_acceptance_status": "BLOCKED",
        "lifecycle_status": "NOT_STARTED",
    }
    path.write_text(json.dumps({"milestones": [row, row]}))
    with pytest.raises(RoadmapError, match="duplicated"):
        load_roadmap(path)


def test_real_operational_acceptance_requires_owner_evidence_for_pass(tmp_path):
    base = {
        "code": "M1",
        "engineering_status": "ENGINEERING_READY",
        "protected_integration_status": "INTEGRATED",
        "beta_deployment_status": "DEPLOYED_BETA",
        "owner_acceptance_status": "OWNER_ACCEPTANCE_REQUIRED",
        "lifecycle_status": "OWNER_ACCEPTANCE_REQUIRED",
    }
    surface = {
        "id": "ROA-1",
        "surface": "Customers",
        "milestone_id": "M1",
        "owner_task": "Find a real Customer.",
        "real_data_required": "Authoritative Customer data.",
        "current_result": "Not tested.",
        "blocker": "Owner test required.",
        "owning_domain": "OM2-A / Customers",
        "priority": "P0",
        "status": "NOT_TESTED",
        "beta_operable": False,
        "owner_accepted": False,
        "evidence": [],
    }
    path = tmp_path / "acceptance.yaml"
    path.write_text(
        json.dumps(
            {
                "milestones": [base],
                "real_operational_acceptance": {"surfaces": [surface]},
            }
        )
    )
    loaded = load_roadmap(path)
    assert loaded.operational_acceptance[0].status == "NOT_TESTED"

    surface.update(status="PASS", beta_operable=True, owner_accepted=False)
    path.write_text(
        json.dumps(
            {
                "milestones": [base],
                "real_operational_acceptance": {"surfaces": [surface]},
            }
        )
    )
    with pytest.raises(RoadmapError, match="PASS requires owner proof"):
        load_roadmap(path)


def test_packaged_roadmap_fails_closed_when_digest_is_missing_or_wrong(tmp_path):
    path = tmp_path / "roadmap.json"
    path.write_text(
        json.dumps(
            {
                "milestones": [
                    {
                        "code": "M1",
                        "engineering_status": "NOT_STARTED",
                        "protected_integration_status": "NOT_STARTED",
                        "beta_deployment_status": "NOT_STARTED",
                        "owner_acceptance_status": "BLOCKED",
                        "lifecycle_status": "NOT_STARTED",
                    }
                ]
            }
        )
    )
    digest_path = tmp_path / "roadmap.sha256"
    with pytest.raises(RoadmapError, match="digest is unavailable"):
        load_roadmap(path, digest_path=digest_path)
    digest_path.write_text("0" * 64)
    with pytest.raises(RoadmapError, match="does not match"):
        load_roadmap(path, digest_path=digest_path)


def test_packaged_roadmap_is_deterministically_generated_and_validated(tmp_path):
    source = tmp_path / "source.yaml"
    source.write_text(
        json.dumps(
            {
                "milestones": [
                    {
                        "lane": "OM1",
                        "code": "M1",
                        "engineering_status": "NOT_STARTED",
                        "protected_integration_status": "NOT_STARTED",
                        "beta_deployment_status": "NOT_STARTED",
                        "owner_acceptance_status": "BLOCKED",
                        "lifecycle_status": "NOT_STARTED",
                    }
                ]
            }
        )
    )
    destination = tmp_path / "runtime" / "roadmap.json"
    digest = sync(source, destination)
    assert json.loads(destination.read_text()) == json.loads(source.read_text())
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
        {"result": "Bearer abc.def.ghi"},
        {"result": "-----BEGIN PRIVATE KEY-----x-----END PRIVATE KEY-----"},
    ):
        with pytest.raises(RoadmapError, match="prohibited"):
            safe_event_details(prohibited)
    with pytest.raises(RoadmapError, match="bounded size"):
        safe_event_details({"evidence": "x" * 17_000})


def test_owner_gate_requires_complete_resolved_engineering_evidence():
    base = {
        "lane_code": "OM1-A",
        "event_type": "gate_opened",
        "lifecycle_state": "HUMAN_GATE",
        "idempotency_key": "gate-1",
        "occurred_at": NOW,
        "details": {
            "gate_id": "G1",
            "gate_type": "HUMAN_GATE",
            "action": "Approve platform custody.",
            "why_blocked": "Only the owner can approve custody.",
            "workflow": "Platform ownership approval",
            "estimated_owner_minutes": 15,
            "resume_action": "Provision the approved boundary.",
            "engineering_prerequisites_resolved": True,
        },
    }
    assert FactoryEventIn.model_validate(base).details["estimated_owner_minutes"] == 15
    base["details"]["engineering_prerequisites_resolved"] = False
    with pytest.raises(ValueError, match="engineering prerequisites"):
        FactoryEventIn.model_validate(base)


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
        "represented_milestones": 4,
        "superseded_milestones": 0,
        "engineering_count": 3,
        "beta_count": 3,
        "owner_count": 3,
        "closed_count": 3,
        "engineering_percent": 75.0,
        "beta_percent": 75.0,
        "owner_percent": 75.0,
        "closed_percent": 75.0,
        "engineering_remaining_weight": 1,
        "human_gated_remaining_weight": 0,
        "provider_gated_remaining_weight": 0,
        "weighted_delivery_percent": 42.5,
        "delivery_1d_percent": 25.0,
        "delivery_3d_percent": 50.0,
        "delivery_7d_percent": 75.0,
        "open_defects": 1,
        "defects_discovered": 2,
        "defects_closed": 1,
        "defects_reopened": 0,
        "open_gates": 1,
        "utilization_percent": 50.0,
        "effective_utilization_percent": 100.0,
        "eligible_idle_seconds": 0,
        "pickup_latency_seconds": 3600.0,
        "domain_pickup_latency_seconds": None,
        "release_pickup_latency_seconds": None,
        "release_latency_seconds": None,
        "queue_depth": 5,
        "oldest_handoff_seconds": 10800.0,
        "rework_rate_percent": 33.33,
        "first_pass_yield_percent": 66.67,
        "event_history_status": "MEASURED",
        "lane_history_status": "MEASURED",
        "velocity_history_status": "MEASURED",
    }


def test_empty_metrics_are_defined_without_division_errors(tmp_path):
    metrics = calculate_metrics(
        roadmap=roadmap(tmp_path, 0), events=[], lanes=[], now=NOW
    )
    assert metrics["closed_percent"] == 0.0
    assert metrics["utilization_percent"] == 0.0
    assert metrics["pickup_latency_seconds"] is None
    assert metrics["oldest_handoff_seconds"] is None
    assert metrics["event_history_status"] == "NOT_YET_MEASURED"
    assert metrics["lane_history_status"] == "NOT_YET_MEASURED"
    assert metrics["velocity_history_status"] == "NOT_YET_MEASURED"


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


def test_safe_non_authoritative_movement_recomputes_without_closing_real_work(tmp_path):
    fixture = roadmap(tmp_path, 2)
    baseline = calculate_metrics(roadmap=fixture, events=[], lanes=[], now=NOW)
    moved = calculate_metrics(
        roadmap=fixture,
        events=[event("engineering_complete", milestone="M1")],
        lanes=[],
        now=NOW,
    )
    assert baseline["engineering_percent"] == 0.0
    assert moved["engineering_percent"] == 50.0
    assert moved["beta_percent"] == 0.0
    assert moved["owner_percent"] == 0.0
    assert moved["closed_percent"] == 0.0


def test_deployment_label_alone_does_not_claim_beta_operability(tmp_path):
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
                        "owner_acceptance_status": "OWNER_ACCEPTANCE_REQUIRED",
                        "lifecycle_status": "OWNER_ACCEPTANCE_REQUIRED",
                    }
                ]
            }
        )
    )
    metrics = calculate_metrics(
        roadmap=load_roadmap(path), events=[], lanes=[], now=NOW
    )
    assert metrics["engineering_percent"] == 100.0
    assert metrics["beta_percent"] == 0.0


def test_canonical_supersession_and_reopen_do_not_double_count_progress(tmp_path):
    status = {
        "engineering_status": "NOT_STARTED",
        "protected_integration_status": "NOT_STARTED",
        "beta_deployment_status": "NOT_STARTED",
        "owner_acceptance_status": "BLOCKED",
        "lifecycle_status": "NOT_STARTED",
    }
    path = tmp_path / "roadmap.yaml"
    path.write_text(
        json.dumps(
            {
                "milestones": [
                    dict(status, code="OLD"),
                    dict(
                        status,
                        code="NEW",
                        successor_supersession={"supersedes": ["OLD"]},
                    ),
                ]
            }
        )
    )
    fixture = load_roadmap(path)
    metrics = calculate_metrics(
        roadmap=fixture,
        events=[
            event("closed", milestone="NEW"),
            event("milestone_reopened", milestone="NEW"),
        ],
        lanes=[],
        now=NOW,
    )
    assert metrics["represented_milestones"] == 1
    assert metrics["superseded_milestones"] == 1
    assert metrics["closed_percent"] == 0.0


def test_defect_reopen_is_counted_as_a_transition(tmp_path):
    metrics = calculate_metrics(
        roadmap=roadmap(tmp_path, 1),
        events=[
            event(
                "defect_opened",
                occurred_at=NOW - timedelta(minutes=3),
                details={"defect_id": "D1"},
            ),
            event(
                "defect_closed",
                occurred_at=NOW - timedelta(minutes=2),
                details={"defect_id": "D1"},
            ),
            event(
                "defect_opened",
                occurred_at=NOW - timedelta(minutes=1),
                details={"defect_id": "D1"},
            ),
        ],
        lanes=[],
        now=NOW,
    )
    assert metrics["defects_discovered"] == 1
    assert metrics["defects_closed"] == 1
    assert metrics["defects_reopened"] == 1
    assert metrics["open_defects"] == 1


def test_runtime_roadmap_rejects_unknown_dependencies_and_cycles(tmp_path):
    base = {
        "engineering_status": "NOT_STARTED",
        "protected_integration_status": "NOT_STARTED",
        "beta_deployment_status": "NOT_STARTED",
        "owner_acceptance_status": "BLOCKED",
        "lifecycle_status": "NOT_STARTED",
    }
    path = tmp_path / "invalid.yaml"
    path.write_text(
        json.dumps({"milestones": [dict(base, code="M1", prerequisites=["M2"])]})
    )
    with pytest.raises(RoadmapError, match="unknown prerequisites"):
        load_roadmap(path)
    path.write_text(
        json.dumps(
            {
                "milestones": [
                    dict(base, code="M1", prerequisites=["M2"]),
                    dict(base, code="M2", prerequisites=["M1"]),
                ]
            }
        )
    )
    with pytest.raises(RoadmapError, match="cyclic"):
        load_roadmap(path)
