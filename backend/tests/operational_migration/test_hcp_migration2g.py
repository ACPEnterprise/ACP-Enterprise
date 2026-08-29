from dataclasses import replace
from pathlib import Path

import pytest

from app.operational_migration.hcp_migration2_plan import (
    BUILDER_VERSION,
    HcpMigration2ExecutionPlanBuilder,
)


def _builder(
    builder_type: type[HcpMigration2ExecutionPlanBuilder] = (
        HcpMigration2ExecutionPlanBuilder
    ),
) -> HcpMigration2ExecutionPlanBuilder:
    root = Path.home() / ".acp-enterprise/migration/housecall-pro"
    return builder_type(
        package_root=root / "hcp-source-4-20260827T223858Z",
        control_csv=root
        / "hcp-source-3-controls/derived/AllCountyPlumbingandLeak_customer_export.csv",
        migration1a_root=root / "hcp-migration-1a-20260828T120000Z",
    )


@pytest.mark.skipif(
    not (
        Path.home()
        / ".acp-enterprise/migration/housecall-pro/hcp-source-4-20260827T223858Z"
    ).exists(),
    reason="protected SOURCE.4 qualification evidence is not installed",
)
def test_complete_source4_plan_is_deterministic_and_reconciled(
    capsys: pytest.CaptureFixture[str],
) -> None:
    builder = _builder()
    first, first_summary = builder.build(
        baseline_counts={"business": 0, "masters": 0}
    )
    second, second_summary = builder.build(
        baseline_counts={"masters": 0, "business": 0}
    )

    class ReversedPageBuilder(HcpMigration2ExecutionPlanBuilder):
        def _pages(self, entity: str) -> list[dict[str, object]]:
            return list(reversed(super()._pages(entity)))

    reordered, reordered_summary = _builder(ReversedPageBuilder).build(
        baseline_counts={"business": 0, "masters": 0}
    )
    assert first.builder_version == BUILDER_VERSION
    assert first.plan_id == second.plan_id
    assert first.plan_digest == second.plan_digest
    assert first_summary == second_summary
    assert first.plan_id == reordered.plan_id
    assert first.plan_digest == reordered.plan_digest
    assert first_summary == reordered_summary
    assert first.master.source_counts == {
        "customer": 5296,
        "contact": 4148,
        "service_location": 5633,
        "employee": 7,
        "job": 5801,
        "appointment": 3219,
        "estimate": 1307,
        "invoice": 5756,
        "payment": 4308,
        "note": 2640,
        "hold": 594,
        "unlinked_estimate": 24,
    }
    assert len(first.employees) == 7
    assert sum(
        item.disposition == "CREATE_ENTERPRISE_EMPLOYEE_CANDIDATE"
        for item in first.employees
    ) == 6
    assert len(first.unlinked_estimates) == 24
    assert len(first.holds) == 594
    assert len(first.plan_outcomes) == 4905
    assert first.completion.location_exceptions == 294
    assert first.completion.holds_by_code == {
        "CANCELED_JOB_BALANCE_RECONCILIATION": 296,
        "UNRESOLVED_FINANCIAL_BALANCE": 298,
    }
    first.validate()
    with pytest.raises(ValueError):
        replace(first, plan_outcomes=()).validate()
    assert capsys.readouterr().out == ""


def test_wrong_builder_scope_fails_without_protected_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from uuid import uuid4

    with pytest.raises(ValueError) as captured:
        _builder().build(
            baseline_counts={},
            company_id=uuid4(),
        )
    assert "PRIVATE" not in str(captured.value)
    assert capsys.readouterr().out == ""
