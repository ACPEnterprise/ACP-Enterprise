from __future__ import annotations

import copy

import pytest
from app.operational_migration.hcp_current_graph_completeness import (
    _digest,
    verify_complete_graph,
)


def _packet() -> dict[str, object]:
    records = [
        {
            "domain": "customer",
            "source_id": f"source4_{number:03d}",
            "successor_assertion": "CREATE_NEW",
        }
        for number in range(522)
    ]
    value: dict[str, object] = {
        "contract": "hcp-current-overlay-merge-packet/v4",
        "record_count": 522,
        "current_operational_graph_admittable": True,
        "ready_for_guarded_execution": True,
        "records": records,
    }
    value["digest"] = _digest(value)
    return value


def test_complete_graph_requires_unique_522_record_authority() -> None:
    packet = _packet()
    verify_complete_graph(packet)
    assert packet["digest"] == _digest(packet)


def test_duplicate_source_identity_fails_closed() -> None:
    packet = _packet()
    packet["records"][1] = copy.deepcopy(packet["records"][0])  # type: ignore[index]
    packet["digest"] = _digest(packet)
    with pytest.raises(ValueError, match="duplicate"):
        verify_complete_graph(packet)


@pytest.mark.parametrize(
    "field", ("current_operational_graph_admittable", "ready_for_guarded_execution")
)
def test_incomplete_factory_gate_cannot_be_executable(field: str) -> None:
    packet = _packet()
    packet[field] = False
    packet["digest"] = _digest(packet)
    with pytest.raises(ValueError, match="completeness gate"):
        verify_complete_graph(packet)


def test_tampered_artifact_digest_is_rejected() -> None:
    packet = _packet()
    packet["records"][0]["successor_assertion"] = "HOLD"  # type: ignore[index]
    with pytest.raises(ValueError, match="contract/digest"):
        verify_complete_graph(packet)
