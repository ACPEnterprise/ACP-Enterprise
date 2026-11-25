import json
from pathlib import Path

import pytest
from development_factory.assignment_bridge import prepare_claim_envelope
from development_factory.coordination import (
    CoordinationError,
    build_daily_report,
    canonical_digest,
    dependency_layers,
    eligible_after_activation,
    load_queue,
    validate_activation,
    validate_inventory,
    validate_queue,
)


def queue_payload() -> dict[str, object]:
    return {
        "schema_version": "twelfthats.continuous-engineering-queue.v1",
        "status": "PREPARED_PENDING_MACHINE_ACTIVATION",
        "assignments": [
            {
                "id": "LAP-ONE",
                "lane": "LAPTOP_MASTER",
                "priority": "P0",
                "state": "READY_AFTER_INVENTORY",
                "depends_on": [],
                "objective": "A bounded test assignment.",
            },
            {
                "id": "OM1-TWO",
                "lane": "OM1",
                "priority": "P1",
                "state": "BLOCKED_DEPENDENCY",
                "depends_on": ["LAP-ONE"],
                "objective": "A dependent test assignment.",
            },
        ],
    }


def test_loads_repository_queue_and_projects_only_activated_lanes() -> None:
    queue = load_queue(Path(__file__).parents[3])
    assert len(queue.assignments) == 12
    assert eligible_after_activation(queue, ()) == ()


def test_dependency_layers_and_activation_projection() -> None:
    queue = validate_queue(queue_payload())
    assert dependency_layers(queue) == (("LAP-ONE",), ("OM1-TWO",))
    assert eligible_after_activation(queue, ("LAPTOP_MASTER",)) == ("LAP-ONE",)
    assert eligible_after_activation(queue, ("OM1",)) == ()
    assert eligible_after_activation(queue, ("OM1",), ("LAP-ONE",)) == ("OM1-TWO",)


def test_unknown_completion_evidence_fails_closed() -> None:
    queue = validate_queue(queue_payload())
    with pytest.raises(CoordinationError, match="unknown completed assignments"):
        eligible_after_activation(queue, ("OM1",), ("NOT-A-QUEUE-ITEM",))


def test_claim_envelope_is_bound_to_clean_machine_and_remains_unclaimed() -> None:
    queue = validate_queue(
        {
            **queue_payload(),
            "assignments": [
                {
                    **queue_payload()["assignments"][0],
                    "allowed_paths": ["backend/tests/**"],
                    "validation": ["focused tests"],
                    "stop_conditions": ["live mutation"],
                },
                queue_payload()["assignments"][1],
            ],
        }
    )
    receipt = {
        "schema": "twelfthats.machine-inventory.v1",
        "role_claimed": "LAPTOP",
        "host": {"hostname": "laptop"},
        "repository": {
            "root": "/repo",
            "branch": "work/laptop",
            "head": "a" * 40,
            "origin": "https://example.invalid/repo.git",
            "status_clean": True,
        },
    }
    envelope = prepare_claim_envelope(
        queue,
        assignment_id="LAP-ONE",
        inventory=receipt,
    )
    assert envelope["claim_state"] == "PREPARED_NOT_CLAIMED"
    assert envelope["safety"] == {
        "claim_issued": False,
        "lease_issued": False,
        "approval_issued": False,
        "git_mutation_performed": False,
        "live_data_mutation": False,
    }
    assert envelope["machine_inventory_digest_sha256"]


def test_machine_inventory_requires_secret_free_safety_flags() -> None:
    receipt = {
        "schema": "twelfthats.machine-inventory.v1",
        "role_claimed": "OM1",
        "host": {
            "hostname": "om1",
            "os": "macOS",
            "machine": "arm64",
            "python": "3.12",
        },
        "repository": {
            "root": "/repo",
            "branch": "work/om1",
            "head": "a" * 40,
            "origin": "https://example.invalid/repo.git",
        },
        "safety": {
            "private_keys_read": False,
            "environment_values_dumped": False,
            "git_mutation_performed": False,
            "docker_container_started": False,
        },
    }
    assert validate_inventory(receipt)["role_claimed"] == "OM1"
    receipt["safety"]["private_keys_read"] = True
    with pytest.raises(CoordinationError):
        validate_inventory(receipt)


def test_worker_activation_requires_bound_identity_session_and_healthy_heartbeat() -> (
    None
):
    inventory = {
        "schema": "twelfthats.machine-inventory.v1",
        "role_claimed": "OM1",
        "host": {
            "hostname": "om1",
            "os": "macOS",
            "machine": "arm64",
            "python": "3.12",
        },
        "repository": {
            "root": "/repo",
            "branch": "work/om1",
            "head": "a" * 40,
            "origin": "https://example.invalid/repo.git",
            "status_clean": True,
        },
        "safety": {
            "private_keys_read": False,
            "environment_values_dumped": False,
            "git_mutation_performed": False,
            "docker_container_started": False,
        },
    }
    activation = {
        "schema": "twelfthats.machine-activation.v1",
        "role_claimed": "OM1",
        "machine_inventory_digest_sha256": canonical_digest(inventory),
        "worker": {
            "worker_id": "worker-1",
            "provider_identifier": "om1-provider",
            "capabilities": ["transport.connectivity", "validation.run"],
            "public_key_fingerprint_sha256": "b" * 64,
            "session_state": "connected",
        },
        "heartbeat": {"health": "healthy", "observed_at_utc": "2026-11-24T00:00:00Z"},
        "safety": {
            "private_key_material_included": False,
            "credential_values_included": False,
            "customer_data_included": False,
            "git_mutation_performed": False,
            "live_data_mutation": False,
        },
    }
    assert validate_activation(activation, inventory=inventory)["role_claimed"] == "OM1"
    activation["worker"]["session_state"] = "closed"
    with pytest.raises(CoordinationError, match="session is not connected"):
        validate_activation(activation, inventory=inventory)


def test_worker_activation_rejects_secret_bearing_fields() -> None:
    inventory = {
        "schema": "twelfthats.machine-inventory.v1",
        "role_claimed": "OM2",
        "host": {
            "hostname": "om2",
            "os": "Linux",
            "machine": "x86_64",
            "python": "3.12",
        },
        "repository": {
            "root": "/repo",
            "branch": "work/om2",
            "head": "c" * 40,
            "origin": "https://example.invalid/repo.git",
            "status_clean": True,
        },
        "safety": {
            "private_keys_read": False,
            "environment_values_dumped": False,
            "git_mutation_performed": False,
            "docker_container_started": False,
        },
    }
    activation = {
        "schema": "twelfthats.machine-activation.v1",
        "role_claimed": "OM2",
        "machine_inventory_digest_sha256": canonical_digest(inventory),
        "worker": {
            "worker_id": "worker-2",
            "provider_identifier": "om2-provider",
            "capabilities": ["transport.connectivity"],
            "public_key_fingerprint_sha256": "d" * 64,
            "session_state": "connected",
        },
        "heartbeat": {"health": "healthy", "observed_at_utc": "2026-11-24T00:00:00Z"},
        "safety": {
            "private_key_material_included": False,
            "credential_values_included": False,
            "customer_data_included": False,
            "git_mutation_performed": False,
            "live_data_mutation": False,
        },
        "access_token": "must-not-appear",
    }
    with pytest.raises(CoordinationError, match="secret-bearing"):
        validate_activation(activation, inventory=inventory)


def test_daily_report_projects_inventory_queue_and_unverified_lanes(
    tmp_path: Path,
) -> None:
    receipt = {
        "schema": "twelfthats.machine-inventory.v1",
        "role_claimed": "LAPTOP",
        "host": {
            "hostname": "laptop",
            "os": "macOS",
            "machine": "arm64",
            "python": "3.13",
        },
        "repository": {
            "root": "/repo",
            "branch": "work/laptop",
            "head": "b" * 40,
            "origin": "https://example.invalid/repo.git",
            "status_clean": True,
        },
        "resources": {"free_bytes_at_repo": 100, "host_memory_bytes": 200},
        "safety": {
            "private_keys_read": False,
            "environment_values_dumped": False,
            "git_mutation_performed": False,
            "docker_container_started": False,
        },
    }
    receipt_path = tmp_path / "laptop.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    latest_path = tmp_path / "latest.json"
    latest_path.write_text(
        json.dumps(
            {
                "readiness": "Ready for owner review",
                "repository": {"head": "c" * 40},
                "blocking_failures": [],
            }
        ),
        encoding="utf-8",
    )

    report = build_daily_report(
        Path(__file__).parents[3],
        inventory_paths=(receipt_path,),
        active_lanes=("LAPTOP_MASTER",),
        latest_report_path=latest_path,
    )

    assert report["schema"] == "twelfthats.daily-engineering-report.v1"
    assert report["queue"]["eligible_after_supplied_activation"] == [
        "LAP-SALES-DEMO-ACCESS-01",
        "LAP-WORKFORCE-DISPATCH-READINESS-01",
    ]
    assert report["queue"]["completed_assignments_supplied"] == []
    assert report["unverified_lanes"] == ["OM1", "OM2", "REVIEWER"]
    assert report["validation"]["status"] == "STALE"
    assert report["validation"]["head"] == "c" * 40


@pytest.mark.parametrize("dependency", ["MISSING", "OM1-TWO"])
def test_unknown_or_cyclic_dependencies_fail_closed(dependency: str) -> None:
    payload = json.loads(json.dumps(queue_payload()))
    payload["assignments"][0]["depends_on"] = [dependency]
    with pytest.raises(CoordinationError):
        validate_queue(payload)
