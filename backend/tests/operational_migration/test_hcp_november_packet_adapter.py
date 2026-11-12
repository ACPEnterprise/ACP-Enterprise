from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from app.operational_migration.hcp_migration2_runner import SafeEvidenceError
from app.operational_migration.hcp_november_packet_adapter import (
    EXPECTED_COUNTS,
    SOURCE_PACKET_CONTRACT,
    adapt_source_packet,
)
from app.operational_migration.hcp_november_executor import _digest


COMPANY = "3ddf07ce-0f44-4b67-a40f-fb0ec41bb7cd"
BRANCH = "887f413a-70dc-4ab1-98aa-8e84f4e7efd0"
ACTOR = "c427ebd1-7583-4c0d-9c54-55a0c1214174"
PROVIDER = "aba4de03-d1b7-4c4e-8fb6-32a3fca713f5"
QUALIFICATION = "1" * 64
SOURCE_SHA = "2" * 64
ACQUIRED = "2026-11-10T15:24:37.096169+00:00"


def _source_packet() -> dict:
    domains = (
        "appointment",
        "attachment",
        "customer",
        "employee",
        "estimate",
        "invoice",
        "job",
        "legacy_appointment",
        "note",
        "service_location",
        "technician_reference",
    )
    records: list[dict] = []
    index = 0
    for disposition, count in EXPECTED_COUNTS.items():
        for _ in range(count):
            domain = domains[index % len(domains)]
            source_id = f"{domain}-{index}"
            executable = disposition in {"CREATE", "UPDATE", "REPLAY"}
            records.append(
                {
                    "domain": domain,
                    "source_id": source_id,
                    "disposition": disposition,
                    "executable": executable,
                    "execution_phase": 10 if executable else None,
                    "hold_subdisposition": None if executable else "HOLD_TEST",
                    "original_gate_disposition": disposition,
                    "parent_lineage": [],
                    "payload_locator": f"private/{domain}.json#{source_id}",
                    "prior_source_digest": "b" * 64 if disposition == "UPDATE" else None,
                    "reason": "synthetic",
                    "source_digest": "a" * 64,
                }
            )
            index += 1
    source = {
        "contract": SOURCE_PACKET_CONTRACT,
        "created_at": "2026-11-12T03:43:57Z",
        "acquired_at": ACQUIRED,
        "scope": {
            "company_id": COMPANY,
            "branch_id": BRANCH,
            "actor_id": ACTOR,
            "provider_company_id": PROVIDER,
            "target": "preview",
        },
        "sealed_inputs": {
            "admission_bundle_sha256": "c" * 64,
            "gate_digest": "d" * 64,
            "policy_digest": "e" * 64,
            "provider_observations_digest": "f" * 64,
            "reconciliation_digest": "0" * 64,
        },
        "classification_totals": EXPECTED_COUNTS.copy(),
        "summary": {
            "record_count": len(records),
            "executable_record_count": 5191,
            "held_identity_count": 2102,
            "unexplained_omissions": [],
            "lineage_gaps": [],
        },
        "execution_order": [
            {
                "domain": item["domain"],
                "source_id": item["source_id"],
                "disposition": item["disposition"],
                "execution_phase": item["execution_phase"],
            }
            for item in records
            if item["executable"]
        ],
        "records": records,
    }
    source["digest"] = _digest(source)
    return source


def _adapt(source: dict) -> dict:
    return adapt_source_packet(
        source,
        source_packet_sha256=SOURCE_SHA,
        expected_source_packet_sha256=SOURCE_SHA,
        expected_source_packet_digest=source["digest"],
        qualification_digest=QUALIFICATION,
        repository_sha="9" * 40,
        schema_head="yp8r0t2v4x6z",
        expected_scope={
            "company_id": COMPANY,
            "branch_id": BRANCH,
            "actor_id": ACTOR,
            "provider_company_id": PROVIDER,
        },
    )


def test_final_packet_adapts_without_dropping_records() -> None:
    source = _source_packet()
    derived = _adapt(source)

    assert derived["contract"] == "hcp-november-preview-execution-packet/v1"
    assert derived["provider_company_id"] == PROVIDER
    assert len(derived["records"]) == len(source["records"]) == 7293
    assert {item["source_id"] for item in derived["records"]} == {
        item["source_id"] for item in source["records"]
    }
    assert {item["domain"] for item in derived["records"]} == {
        item["domain"] for item in source["records"]
    }


@pytest.mark.parametrize(
    "change,code",
    [
        (lambda packet: packet.update(contract="wrong/v1"), "hcp_november_adapter_source_contract"),
        (lambda packet: packet["classification_totals"].update(CREATE=510), "hcp_november_adapter_count_mismatch"),
        (lambda packet: packet["records"][0].update(parent_lineage=[{"domain": "job", "source_id": "missing", "disposition": "CREATE"}]), "hcp_november_adapter_lineage_ambiguous"),
        (lambda packet: packet["records"][0].update(domain="unknown"), "hcp_november_adapter_unknown_domain"),
        (lambda packet: packet["records"][0].update(disposition="MUTATE"), "hcp_november_adapter_unknown_disposition"),
    ],
)
def test_malformed_source_fails_closed(change, code: str) -> None:
    source = _source_packet()
    change(source)
    if source.get("contract") == SOURCE_PACKET_CONTRACT:
        source["digest"] = _digest({key: value for key, value in source.items() if key != "digest"})
    with pytest.raises(SafeEvidenceError, match=code):
        _adapt(source)


def test_count_drift_in_records_fails_closed() -> None:
    source = _source_packet()
    source["records"].pop()
    source["digest"] = _digest({key: value for key, value in source.items() if key != "digest"})
    with pytest.raises(SafeEvidenceError, match="hcp_november_adapter_count_mismatch"):
        _adapt(source)


def test_executable_child_of_held_parent_fails_closed() -> None:
    source = _source_packet()
    held = next(item for item in source["records"] if item["disposition"] == "HOLD")
    child = next(item for item in source["records"] if item["executable"])
    child["parent_lineage"] = [
        {"domain": held["domain"], "source_id": held["source_id"], "disposition": held["disposition"]}
    ]
    source["digest"] = _digest({key: value for key, value in source.items() if key != "digest"})
    with pytest.raises(SafeEvidenceError, match="hcp_november_adapter_held_parent_executable_edge"):
        _adapt(source)


def test_source_digest_and_output_are_deterministic() -> None:
    source = _source_packet()
    first = _adapt(source)
    second = _adapt(deepcopy(source))
    assert first == second
    assert first["source_packet_digest"] == source["digest"]
    assert first["adapter_version"]
    assert hashlib.sha256(json.dumps(source, sort_keys=True, separators=(",", ":")).encode()).hexdigest() != first["digest"]
