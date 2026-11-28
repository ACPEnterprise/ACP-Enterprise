import json
from pathlib import Path

from backend.scripts.reconcile_historical_workforce import _historical_rows


def test_historical_rows_preserve_known_ids_without_granting_access() -> None:
    native = {
        name: __import__("uuid").uuid4()
        for name in (
            "Michael Fouse",
            "Alex Donahue",
            "Melvin Santiago",
            "Dakota Wilcox",
            "Jason Calci",
            "Alex Donahue (stale)",
        )
    }
    rows = _historical_rows(native)
    assert len(rows) == 10
    assert {row["source_identity"] for row in rows} >= {
        "pro_23be6c33b14a4127bd737529180a56a1",
        "pro_2edf25dd14494b1885a50fa134b44fd8",
        "pro_4f1d81e3d31b4ffa9072dd6a32906586",
        "pro_8646a77e7dc649ba96259ce8ef68acb2",
        "name:kamen-wilmington",
    }
    assert all(
        row["lifecycle_state"] in {"VERIFIED", "PARTIAL", "QUARANTINED", "UNRESOLVED"}
        for row in rows
    )


def test_melvin_and_dakota_are_preserved_as_non_authoritative_when_unresolved() -> None:
    from uuid import uuid4

    native = {
        name: uuid4()
        for name in (
            "Michael Fouse",
            "Alex Donahue",
            "Melvin Santiago",
            "Dakota Wilcox",
            "Jason Calci",
            "Alex Donahue (stale)",
        )
    }
    rows = {row["display_name"]: row for row in _historical_rows(native)}
    assert rows["Melvin Santiago"]["lifecycle_state"] == "PARTIAL"
    assert rows["Dakota Wilcox"]["lifecycle_state"] == "QUARANTINED"


def test_operational_roster_and_historical_identity_counts_reconcile() -> None:
    contract = json.loads(
        (
            Path(__file__).parents[2]
            / "operations/real-workforce-cutover-contract.v1.json"
        ).read_text()
    )
    employee_count = len(contract["expected_roster"]) + len(
        contract["terminated_historical_roster"]
    )
    native = {
        name: __import__("uuid").uuid4()
        for name in (
            "Michael Fouse",
            "Alex Donahue",
            "Melvin Santiago",
            "Dakota Wilcox",
            "Jason Calci",
            "Alex Donahue (stale)",
        )
    }
    historical = _historical_rows(native)

    assert employee_count == 9
    assert len(historical) == 10
    assert {item["display_name"] for item in historical} >= {
        item["canonical_display_name"]
        for item in contract["terminated_historical_roster"]
    }
    terminated_names = {
        item["canonical_display_name"]
        for item in contract["terminated_historical_roster"]
    }
    assert all(
        item["native_employee_id"] is None and item["lifecycle_state"] == "UNRESOLVED"
        for item in historical
        if item["display_name"] in terminated_names
    )
