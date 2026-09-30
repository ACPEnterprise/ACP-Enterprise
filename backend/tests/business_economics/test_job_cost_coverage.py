from app.business_economics.job_cost_coverage import project_job_cost_coverage


def _job(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "job_id": "job-1",
        "invoiced_revenue_minor": 10_000,
        "currency": "USD",
        "settlement_applied_minor": None,
        "accepted_worked_seconds": 3600,
        "material_quantity_evidence_count": 1,
        "material_cost_minor": 2_000,
        "service_category": "drain",
        "customer_id": "customer-1",
        "branch_id": "branch-1",
    }
    value.update(updates)
    return value


def test_job_with_real_inputs_remains_partial_when_cost_authority_is_missing() -> None:
    jobs, summary = project_job_cost_coverage([_job()])

    assert jobs[0]["contribution_readiness"] == "PARTIAL"
    assert jobs[0]["direct_contribution_minor"] is None
    assert jobs[0]["cost_coverage"]["material_cost"]["state"] == "AVAILABLE"
    assert jobs[0]["cost_coverage"]["wage_cost"]["state"] == "SOURCE_REQUIRED"
    assert summary["contribution_readiness"] == {
        "READY": 0,
        "PARTIAL": 1,
        "INSUFFICIENT": 0,
        "CONFLICTING": 0,
    }


def test_missing_revenue_is_insufficient_and_missing_cost_never_becomes_zero() -> None:
    jobs, summary = project_job_cost_coverage(
        [_job(invoiced_revenue_minor=None, material_cost_minor=None)]
    )

    assert jobs[0]["contribution_readiness"] == "INSUFFICIENT"
    assert jobs[0]["direct_contribution_minor"] is None
    assert summary["missing_cost_is_zero"] is False
    assert any(
        item["family"] == "invoiced_revenue"
        for item in summary["data_completeness_queue"]
    )


def test_mixed_invoice_currency_is_conflicting() -> None:
    jobs, summary = project_job_cost_coverage([_job(currency=None)])

    assert jobs[0]["contribution_readiness"] == "CONFLICTING"
    assert (
        jobs[0]["cost_coverage"]["invoiced_revenue"]["requirement"]
        == "resolve_multiple_invoice_currencies"
    )
    assert summary["contribution_readiness"]["CONFLICTING"] == 1


def test_queue_is_prioritized_by_affected_job_count() -> None:
    _, summary = project_job_cost_coverage([_job(), _job(job_id="job-2")])

    queue = summary["data_completeness_queue"]
    assert queue[0]["affected_job_count"] == 2
    assert all(item["responsible_party"] == "MACHINE_ACQUISITION" for item in queue)
