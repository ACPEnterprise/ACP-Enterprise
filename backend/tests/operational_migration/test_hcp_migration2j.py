from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Self
from uuid import UUID

import pytest

from app.operational_migration.hcp_migration2_plan import (
    HcpMigration2Application,
    HcpMigration2ExecutionPlanBuilder,
    HcpMigration2RepairAuthority,
    HcpMigration2RepairResult,
    RehearsalAdmissionState,
)

MASTER_ID = UUID("63273602-8619-5c0b-8b49-8537338b04b5")
PLAN_ID = UUID("8c717798-db5e-5c49-99be-ca3d250536e3")
PLAN_DIGEST = "6ac31cc70e269dfa123a73c8a896f7e957eff113c1873a6ee8c908a9f1256962"
REPAIR_DIGEST = "64df671d21ab95818ae6035949202e6d61195733013ff63485471164e9b64d8a"


def authority() -> HcpMigration2RepairAuthority:
    return HcpMigration2RepairAuthority(
        master_run_id=MASTER_ID,
        original_plan_id=PLAN_ID,
        original_plan_digest=PLAN_DIGEST,
        repair_plan_digest=REPAIR_DIGEST,
        customer_child_run_id=UUID("4b99260f-43e7-4ae5-81c2-d0cc215b323f"),
        operational_child_run_id=UUID("4b8f089d-d47c-4757-a583-e8408f7c4ffd"),
        financial_child_run_id=UUID("b8315c42-9d24-4f48-a64f-8fdc05176cce"),
        history_child_run_id=UUID("b612df45-341a-44b7-b85d-964c356ffd17"),
    )


def test_application_lifecycle_identifies_repair_and_completed_replay() -> None:
    repair = authority()
    running = (SimpleNamespace(status="running"),)
    completed = (SimpleNamespace(status="completed"),)
    assert (
        HcpMigration2Application.classify_application_admission(
            running,  # type: ignore[arg-type]
            repair_authority=repair,
        )
        == RehearsalAdmissionState.MATCHING_INCOMPLETE_MASTER_WITH_ACCEPTED_REPAIR_PLAN
    )
    assert (
        HcpMigration2Application.classify_application_admission(
            completed,  # type: ignore[arg-type]
            repair_authority=repair,
        )
        == RehearsalAdmissionState.COMPLETED_MASTER
    )
    assert (
        HcpMigration2Application.classify_application_admission(
            running,  # type: ignore[arg-type]
            repair_authority=None,
        )
        == RehearsalAdmissionState.MATCHING_INCOMPLETE_MASTER
    )


def test_repair_result_exposes_safe_metadata_only() -> None:
    result = HcpMigration2RepairResult(
        state="REPAIR_COMPLETED",
        master_run_id=MASTER_ID,
        master_status="completed",
        repair_plan_digest=REPAIR_DIGEST,
        operational_repair_run_id=UUID(int=1),
        financial_repair_run_id=UUID(int=2),
        reconciliation_digest="a" * 64,
    ).safe_output()
    assert set(result) == {
        "state",
        "master_run_id",
        "master_status",
        "repair_plan_digest",
        "operational_repair_run_id",
        "financial_repair_run_id",
        "reconciliation_digest",
    }
    assert not any(
        unsafe in str(result).lower()
        for unsafe in ("customer_name", "address", "email", "phone", "payload")
    )


class _Scalars:
    def __init__(self, masters: tuple[SimpleNamespace, ...]) -> None:
        self._masters = masters

    def all(self) -> tuple[SimpleNamespace, ...]:
        return self._masters


class _Session:
    def __init__(self, masters: tuple[SimpleNamespace, ...]) -> None:
        self._masters = masters

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def scalars(self, _statement: object) -> _Scalars:
        return _Scalars(self._masters)


class _Factory:
    def __init__(self, masters: tuple[SimpleNamespace, ...]) -> None:
        self._masters = masters

    def __call__(self) -> _Session:
        return _Session(self._masters)


class _RoutedApplication(HcpMigration2Application):
    async def execute_repair(
        self, *args: object, **kwargs: object
    ) -> dict[str, object]:
        return {"state": "REPAIR_COMPLETED"}

    async def replay_completed(
        self, *args: object, **kwargs: object
    ) -> dict[str, object]:
        return {"state": "COMPLETED_REPLAY_VERIFIED"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected"),
    (
        ("running", "REPAIR_COMPLETED"),
        ("completed", "COMPLETED_REPLAY_VERIFIED"),
    ),
)
async def test_public_application_routes_repair_and_completed_replay(
    status: str, expected: str
) -> None:
    application = _RoutedApplication(builder=SimpleNamespace())  # type: ignore[arg-type]
    result = await application.execute(
        _Factory((SimpleNamespace(status=status),)),  # type: ignore[arg-type]
        context=SimpleNamespace(),  # type: ignore[arg-type]
        target=SimpleNamespace(),  # type: ignore[arg-type]
        repair_authority=authority(),
    )
    assert result == {"state": expected}


@pytest.mark.skipif(
    not (
        Path.home()
        / ".acp-enterprise/migration/housecall-pro/hcp-source-4-20260827T223858Z"
    ).exists(),
    reason="protected SOURCE.4 qualification evidence is not installed",
)
def test_sealed_repair_plan_and_completion_envelope_are_deterministic() -> None:
    root = Path.home() / ".acp-enterprise/migration/housecall-pro"
    builder = HcpMigration2ExecutionPlanBuilder(
        package_root=root / "hcp-source-4-20260827T223858Z",
        control_csv=root
        / "hcp-source-3-controls/derived/AllCountyPlumbingandLeak_customer_export.csv",
        migration1a_root=root / "hcp-migration-1a-20260828T120000Z",
    )
    plan, _ = builder.build(baseline_counts={"business": 0, "masters": 1})
    customer_ids = frozenset(
        item.source_identity for item in plan.customers.reviewed.aggregates
    )
    location_ids = frozenset(
        native_id
        for item in plan.customers.reviewed.aggregates
        for native_id in item.service_location_source_identities
    )
    repair = builder.build_child_repair_plan(
        original=plan,
        persisted_customer_ids=customer_ids,
        persisted_location_ids=location_ids,
    )
    repair_again = builder.build_child_repair_plan(
        original=plan,
        persisted_customer_ids=frozenset(customer_ids),
        persisted_location_ids=frozenset(location_ids),
    )
    assert repair.repair_plan_digest == REPAIR_DIGEST
    assert repair_again.repair_plan_digest == repair.repair_plan_digest
    assert len(repair.operational.jobs) == 1094
    assert len(repair.operational.appointments) == 1249
    assert len(repair.financial.estimates) == 14
    assert len(repair.financial.invoices) == 780
    assert len(repair.financial.payments) == 684
    assert len(repair.additional_plan_outcomes) == 13711
    requirements = replace(
        plan.completion,
        transformed_counts=repair.persisted_counts,
        persisted_counts=repair.persisted_counts,
        exception_counts=repair.exception_counts,
    )
    envelope = HcpMigration2Application._requalified_completion_authority(
        plan=plan,
        repair=repair,
        requirements=requirements,
        original_operational_run_id=authority().operational_child_run_id,
        original_financial_run_id=authority().financial_child_run_id,
        repaired_operational_run_id=UUID(int=10),
        repaired_financial_run_id=UUID(int=11),
    )
    assert envelope == HcpMigration2Application._requalified_completion_authority(
        plan=plan,
        repair=repair_again,
        requirements=requirements,
        original_operational_run_id=authority().operational_child_run_id,
        original_financial_run_id=authority().financial_child_run_id,
        repaired_operational_run_id=UUID(int=10),
        repaired_financial_run_id=UUID(int=11),
    )
    changed = HcpMigration2Application._requalified_completion_authority(
        plan=plan,
        repair=repair,
        requirements=requirements,
        original_operational_run_id=authority().operational_child_run_id,
        original_financial_run_id=authority().financial_child_run_id,
        repaired_operational_run_id=UUID(int=12),
        repaired_financial_run_id=UUID(int=11),
    )
    assert changed != envelope
