from app.operational_migration.hcp_historical_population_reconciliation import (
    PopulationSnapshot,
    SnapshotRecord,
    reconcile_historical_population,
)

DIGEST = "a" * 64


def row(
    domain: str,
    source_id: str,
    *,
    target: str | None = None,
    parents: tuple[str, ...] = (),
    disposition: str = "ADMITTED",
    merged_into: str | None = None,
) -> SnapshotRecord:
    return SnapshotRecord(
        domain,
        source_id,
        target,
        parents,
        DIGEST,
        disposition,
        merged_into,
    )


def snapshot(
    identifier: str, records: tuple[SnapshotRecord, ...], digest: str
) -> PopulationSnapshot:
    return PopulationSnapshot(
        identifier, f"2026-11-{identifier}T00:00:00Z", digest, records
    )


def test_reconciles_population_discrepancies_and_relationships() -> None:
    previous = snapshot(
        "25",
        (
            row("customer", "c-1", target="native-c1"),
            row("customer", "c-missing", target="native-old"),
            row("location", "l-missing", parents=("customer:c-missing",)),
            row("job", "j-1", target="native-j1", parents=("location:l-missing",)),
            row("appointment", "a-1", parents=("job:j-1",)),
        ),
        "1" * 64,
    )
    current = snapshot(
        "27",
        (
            row("customer", "c-1", target="native-changed"),
            row("customer", "c-2", target="native-c2"),
            row("customer", "c-3", target="native-c2", merged_into="c-2"),
            row("location", "l-2", parents=("customer:c-2",)),
            row("job", "j-1", target="native-j1", parents=("location:l-missing",)),
            row("appointment", "a-2", parents=("job:j-missing",), disposition="HELD"),
        ),
        "2" * 64,
    )
    result = reconcile_historical_population(previous, current)

    assert result.previous_counts == {
        "customer": 2,
        "location": 1,
        "job": 1,
        "appointment": 1,
    }
    assert result.current_counts == {
        "customer": 3,
        "location": 1,
        "job": 1,
        "appointment": 1,
    }
    assert "customer:c-missing" in result.missing_identities
    assert result.missing_locations == ("location:l-missing",)
    assert result.duplicate_customer_targets == (("native-c2", ("c-2", "c-3")),)
    assert result.merged_customers == (("c-3", "c-2"),)
    assert result.orphaned_jobs == ("job:j-1",)
    assert result.orphaned_appointments == ("appointment:a-2",)
    assert "customer:c-1" in result.target_identity_mismatches
    assert result.excluded_records == ("appointment:a-2",)
    assert result.provenance_differences == (
        "provenance_digest_changed",
        "acquired_at_changed",
    )
    assert result.mutation_authority == "none"


def test_duplicate_source_rows_are_reported_as_provenance_differences() -> None:
    duplicate = row("customer", "c-1")
    result = reconcile_historical_population(
        snapshot("25", (duplicate,), "1" * 64),
        snapshot("27", (duplicate, duplicate), "1" * 64),
    )
    assert "current_duplicate:customer:c-1" in result.provenance_differences


def test_invalid_snapshot_fails_closed() -> None:
    try:
        reconcile_historical_population(
            snapshot("25", (row("unknown", "x"),), "1" * 64),
            snapshot("27", (), "1" * 64),
        )
    except ValueError as error:
        assert "record identity" in str(error)
    else:
        raise AssertionError("invalid snapshot was accepted")
