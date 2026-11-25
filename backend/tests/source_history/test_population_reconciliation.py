from dataclasses import replace
from uuid import UUID

from app.source_history.population_reconciliation import (
    SourcePopulationRecord,
    reconcile_population,
)
from app.source_history.registration import (
    SealedSourceManifest,
    canonical_manifest_digest,
    register_sealed_source,
)

COMPANY = UUID("10000000-0000-0000-0000-000000000001")


def registration():
    draft = SealedSourceManifest(
        "housecall_pro", COMPANY, "a" * 64, 5, "2026-11-25T00:00:00Z", True, ""
    )
    return register_sealed_source(
        replace(draft, manifest_digest=canonical_manifest_digest(draft)),
        expected_company_id=COMPANY,
    )


def test_reconciles_customer_location_job_detail_and_photograph_population() -> None:
    rows = (
        SourcePopulationRecord("customer:c1", "customer"),
        SourcePopulationRecord("location:l1", "location", ("customer:c1",)),
        SourcePopulationRecord("job:j1", "job", ("customer:c1", "location:l1")),
        SourcePopulationRecord("job_detail:j1", "job_detail", ("job:j1",)),
        SourcePopulationRecord("photo:p1", "photograph", ("job:j1",)),
    )
    result = reconcile_population(registration(), rows)
    assert result.source_count == result.unique_count == result.complete_count == 5
    assert result.held_count == 0
    assert ("photograph", 1) in result.kind_counts
    assert result.mutation_authority == "none"


def test_duplicate_and_missing_relationships_remain_explicit_holds() -> None:
    rows = (
        SourcePopulationRecord("customer:c1", "customer"),
        SourcePopulationRecord("customer:c1", "customer"),
        SourcePopulationRecord("photo:p1", "photograph", ("job:missing",)),
    )
    result = reconcile_population(registration(), rows)
    assert result.duplicate_source_keys == ("customer:c1",)
    assert result.missing_relationships == ("photo:p1->job:missing",)
    assert result.complete_count == 0
    assert result.held_count == 2
