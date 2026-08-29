from __future__ import annotations

from types import SimpleNamespace
from typing import Self
from uuid import UUID

import pytest

from app.operational_migration.hcp_migration2_plan import (
    HcpMigration2Application,
    HcpMigration2SupersedingRepairAuthority,
    RehearsalAdmissionState,
)

MASTER_ID = UUID("63273602-8619-5c0b-8b49-8537338b04b5")
PLAN_ID = UUID("8c717798-db5e-5c49-99be-ca3d250536e3")
REPAIR_ID = UUID("5e17975d-0461-5187-b0ea-f1cbe7b58df1")
FAILED_CHILD_ID = UUID("a5896cb7-deea-477a-86e5-5d606ecf0582")
SUPERSEDING_ID = UUID("a39f3927-0f7f-59a4-8056-97077012832f")
PLAN_DIGEST = "6ac31cc70e269dfa123a73c8a896f7e957eff113c1873a6ee8c908a9f1256962"
REPAIR_DIGEST = "64df671d21ab95818ae6035949202e6d61195733013ff63485471164e9b64d8a"
SUPERSEDING_DIGEST = "167f3e3729c78953de2e12382d2b64572b0a42082780d1bba4651be0063c5fb5"
SEQUENCE_DIGEST = "9e77ed819ee488ac5114d6fda26d9ae422b081cdfa9785fb56bbf679d6fa7acb"
CHECKPOINT_DIGEST = "3646dc75db78ac72ae54b6fc1b3cdcd03920d0d54795ab265689a37afbaf906b"


def authority() -> HcpMigration2SupersedingRepairAuthority:
    return HcpMigration2SupersedingRepairAuthority(
        master_run_id=MASTER_ID,
        original_plan_id=PLAN_ID,
        original_plan_digest=PLAN_DIGEST,
        generation1_repair_id=REPAIR_ID,
        generation1_repair_plan_digest=REPAIR_DIGEST,
        failed_operational_child_run_id=FAILED_CHILD_ID,
        superseding_plan_id=SUPERSEDING_ID,
        superseding_plan_digest=SUPERSEDING_DIGEST,
        repair_generation=2,
        sequencing_contract_version="hcp-migration-2k1-appointment-sequence/v1",
        sequence_digest=SEQUENCE_DIGEST,
        checkpoint_digest=CHECKPOINT_DIGEST,
        customer_child_run_id=UUID("4b99260f-43e7-4ae5-81c2-d0cc215b323f"),
        original_operational_child_run_id=UUID("4b8f089d-d47c-4757-a583-e8408f7c4ffd"),
        original_financial_child_run_id=UUID("b8315c42-9d24-4f48-a64f-8fdc05176cce"),
        history_child_run_id=UUID("b612df45-341a-44b7-b85d-964c356ffd17"),
        company_id=UUID("3ddf07ce-0f44-4b67-a40f-fb0ec41bb7cd"),
        branch_id=UUID("887f413a-70dc-4ab1-98aa-8e84f4e7efd0"),
        actor_id=UUID("c427ebd1-7583-4c0d-9c54-55a0c1214174"),
        package_digest="a" * 64,
        builder_version="hcp-migration-2g-plan-builder/v1",
    )


def test_generation2_authority_preserves_generation1_authority() -> None:
    generation2 = authority()
    generation1 = generation2.generation1_authority()
    assert generation1.master_run_id == generation2.master_run_id
    assert generation1.original_plan_digest == PLAN_DIGEST
    assert generation1.repair_plan_digest == REPAIR_DIGEST
    assert generation1.operational_child_run_id == (
        generation2.original_operational_child_run_id
    )
    assert generation2.superseding_plan_digest != generation1.repair_plan_digest


def test_generation2_authority_uses_existing_application_admission() -> None:
    state = HcpMigration2Application.classify_application_admission(
        (SimpleNamespace(status="running"),),  # type: ignore[arg-type]
        repair_authority=authority(),
    )
    assert (
        state
        == RehearsalAdmissionState.MATCHING_INCOMPLETE_MASTER_WITH_ACCEPTED_REPAIR_PLAN
    )


class _Scalars:
    def __init__(self, values: tuple[SimpleNamespace, ...]) -> None:
        self._values = values

    def all(self) -> tuple[SimpleNamespace, ...]:
        return self._values


class _Session:
    def __init__(self, values: tuple[SimpleNamespace, ...]) -> None:
        self._values = values

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def scalars(self, _statement: object) -> _Scalars:
        return _Scalars(self._values)


class _Factory:
    def __init__(self, values: tuple[SimpleNamespace, ...]) -> None:
        self._values = values

    def __call__(self) -> _Session:
        return _Session(self._values)


class _Generation2Application(HcpMigration2Application):
    async def execute_superseding_repair(
        self, *args: object, **kwargs: object
    ) -> dict[str, object]:
        return {"state": "GENERATION2_REPAIR_COMPLETED"}

    async def replay_completed_superseding(
        self, *args: object, **kwargs: object
    ) -> dict[str, object]:
        return {"state": "COMPLETED_REPLAY_VERIFIED"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("master_status", "expected"),
    (
        ("running", "GENERATION2_REPAIR_COMPLETED"),
        ("completed", "COMPLETED_REPLAY_VERIFIED"),
    ),
)
async def test_public_entry_routes_generation2_without_manual_plan_assembly(
    master_status: str, expected: str
) -> None:
    application = _Generation2Application(builder=SimpleNamespace())  # type: ignore[arg-type]
    result = await application.execute(
        _Factory((SimpleNamespace(status=master_status),)),  # type: ignore[arg-type]
        context=SimpleNamespace(),  # type: ignore[arg-type]
        target=SimpleNamespace(),  # type: ignore[arg-type]
        repair_authority=authority(),
    )
    assert result == {"state": expected}


def test_generation2_authority_safe_fields_do_not_contain_source_payloads() -> None:
    rendered = repr(authority()).lower()
    assert not any(
        value in rendered
        for value in ("customer_name", "address", "email", "phone", "payload")
    )
