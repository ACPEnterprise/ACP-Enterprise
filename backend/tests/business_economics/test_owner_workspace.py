from types import SimpleNamespace
from uuid import uuid4

from app.business_economics.workspace import EconomicsWorkspaceService, JobIdentity


def _record(
    *,
    revenue: int,
    labor: int,
    materials: int,
    contribution: int,
    complete: bool = True,
):
    def component(amount: int | None):
        return {
            "state": "measured" if amount is not None else "missing",
            "amount_minor": amount,
        }

    components = {
        "revenue": component(revenue),
        "labor": component(labor),
        "materials": component(materials),
        "equipment": component(0),
        "truck": component(0),
        "overhead": component(0 if complete else None),
        "gross_profit": component(contribution),
        "net_profit": component(contribution if complete else None),
    }
    subject_id = uuid4()
    return SimpleNamespace(
        id=uuid4(),
        subject_id=subject_id,
        scope="job",
        currency="USD",
        components=components,
        quality={
            "freshness_status": "current",
            "completeness_percent": 100 if complete else 83,
            "confidence_percent": 100 if complete else 80,
            "missing_categories": [] if complete else ["overhead"],
        },
        metrics={},
        branch_id=uuid4(),
    )


def test_owner_projection_reconciles_jobs_rollups_and_losses() -> None:
    profitable = _record(
        revenue=100_000, labor=30_000, materials=20_000, contribution=50_000
    )
    losing = _record(
        revenue=40_000, labor=35_000, materials=15_000, contribution=-10_000
    )
    identities = {
        profitable.subject_id: JobIdentity(
            "JOB-000001",
            "completed",
            uuid4(),
            "Main",
            uuid4(),
            "Synthetic One",
            "water_heater",
        ),
        losing.subject_id: JobIdentity(
            "JOB-000002",
            "completed",
            uuid4(),
            "North",
            uuid4(),
            "Synthetic Two",
            "repair",
        ),
    }
    profitable.branch_id = identities[profitable.subject_id].branch_id
    losing.branch_id = identities[losing.subject_id].branch_id
    value = EconomicsWorkspaceService._project((profitable, losing), identities)
    assert value["quality_state"] == "complete"
    assert value["totals"]["revenue"] == 140_000
    assert value["totals"]["gross_profit"] == 40_000
    assert (
        sum(item["contribution_minor"] for item in value["service_categories"])
        == 40_000
    )
    assert value["jobs"][0]["job_number"] == "JOB-000001"
    assert value["jobs"][1]["contribution_minor"] == -10_000


def test_incomplete_job_remains_visible_but_is_not_fabricated_into_totals() -> None:
    incomplete = _record(
        revenue=100_000,
        labor=30_000,
        materials=20_000,
        contribution=50_000,
        complete=False,
    )
    identities = {
        incomplete.subject_id: JobIdentity(
            "JOB-000003", "in_progress", uuid4(), "Main", uuid4(), "Synthetic", None
        )
    }
    incomplete.branch_id = identities[incomplete.subject_id].branch_id
    value = EconomicsWorkspaceService._project((incomplete,), identities)
    assert value["quality_state"] == "partial"
    assert value["jobs"][0]["quality_state"] == "partial"
    assert value["fully_allocated_available"] is False
    assert value["unclassified_job_count"] == 1


def test_period_comparison_fails_closed_without_both_complete_periods() -> None:
    unavailable = EconomicsWorkspaceService._comparison(
        EconomicsWorkspaceService._empty_projection("unavailable"),
        EconomicsWorkspaceService._empty_projection("unavailable"),
    )
    assert unavailable["state"] == "unavailable"


def test_competing_active_job_results_fail_closed_instead_of_double_counting() -> None:
    first = _record(
        revenue=100_000, labor=30_000, materials=20_000, contribution=50_000
    )
    second = _record(
        revenue=100_000, labor=30_000, materials=20_000, contribution=50_000
    )
    second.subject_id = first.subject_id
    identities = {
        first.subject_id: JobIdentity(
            "JOB-000004", "completed", uuid4(), "Main", uuid4(), "Synthetic", "repair"
        )
    }
    first.branch_id = identities[first.subject_id].branch_id
    second.branch_id = identities[first.subject_id].branch_id
    value = EconomicsWorkspaceService._project((first, second), identities)
    assert value["quality_state"] == "conflicting"
    assert value["totals"] is None


def test_owner_projection_rejects_result_job_branch_conflict() -> None:
    record = _record(
        revenue=100_000, labor=30_000, materials=20_000, contribution=50_000
    )
    identities = {
        record.subject_id: JobIdentity(
            "JOB-000005", "completed", uuid4(), "North", uuid4(), "Synthetic", "repair"
        )
    }

    value = EconomicsWorkspaceService._project((record,), identities)

    assert value["quality_state"] == "conflicting"
    assert value["totals"] is None
    assert "branch" in value["explanation"].lower()
