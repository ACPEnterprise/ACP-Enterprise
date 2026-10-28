from app.business_economics.operational_rollups import build_operational_rollups


def job(
    identity: str,
    *,
    category: str | None,
    revenue: int | None,
    material: int | None,
) -> dict[str, object]:
    return {
        "job_id": identity,
        "branch_id": "branch-1",
        "branch_name": "Main",
        "service_category": category,
        "invoiced_revenue_minor": revenue,
        "currency": "USD" if revenue is not None else None,
        "accepted_worked_seconds": 3600,
        "material_cost_minor": material,
    }


def test_rollup_preserves_partial_totals_and_uncategorized_jobs() -> None:
    result = build_operational_rollups(
        [
            job("one", category="drain", revenue=10_000, material=2_000),
            job("two", category="drain", revenue=None, material=None),
            job("three", category=None, revenue=5_000, material=500),
        ]
    )

    assert result["uncategorized_job_count"] == 1
    assert len(result["service_lines"]) == 1
    drain = result["service_lines"][0]
    assert drain["job_count"] == 2
    assert drain["invoiced_revenue"]["known_value"] == 10_000
    assert drain["invoiced_revenue"]["authoritative_total"] is None
    assert drain["invoiced_revenue"]["state"] == "PARTIAL"
    assert drain["direct_contribution_minor"] is None
    assert result["branches"][0]["job_count"] == 3


def test_complete_known_metric_exposes_authoritative_total() -> None:
    result = build_operational_rollups(
        [job("one", category="drain", revenue=10_000, material=2_000)]
    )

    service = result["service_lines"][0]
    assert service["invoiced_revenue"]["state"] == "AVAILABLE"
    assert service["invoiced_revenue"]["authoritative_total"] == 10_000
    assert service["accepted_worked_seconds"]["authoritative_total"] == 3600
    assert service["direct_material_cost"]["authoritative_total"] == 2_000
    assert service["direct_wage_cost"]["state"] == "SOURCE_REQUIRED"


def test_digest_is_deterministic() -> None:
    jobs = [job("one", category="drain", revenue=10_000, material=2_000)]
    assert build_operational_rollups(jobs)["digest"] == build_operational_rollups(
        jobs
    )["digest"]
