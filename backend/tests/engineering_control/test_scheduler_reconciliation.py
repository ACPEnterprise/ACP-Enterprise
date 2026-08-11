from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.engineering_control.mobile.roadmaps import (
    EngineeringMilestone,
    EngineeringRoadmap,
)
from app.engineering_control.scheduler.manifest import load_scheduler_manifest
from app.engineering_control.scheduler.reconciliation import (
    SchedulerReconciliationError,
    SchedulerReconciliationService,
)
from app.engineering_control.service import EngineeringControlService
from tests.engineering_control.test_engineering_command_service import (
    create_input,
    seed_service_fixture,
    utc_now,
)


@pytest.fixture
def manifest():
    return load_scheduler_manifest()


def test_manifest_is_deterministic_complete_and_unique(manifest) -> None:
    assert manifest.scheduler_version == "MMQ.5-2026-08-11.4"
    assert (
        manifest.fingerprint
        == "f6d8d902f047f8459de82bb1bf22f46f900e63533985d5b4e1a9450dc55f8fef"
    )
    assert {item.identity for item in manifest.capacities} == {
        "OM1",
        "OM2",
        "MIG",
        "ECO",
        "LAP",
    }
    assert {item.milestone_code for item in manifest.milestones} == {
        "PRICEBOOK.1",
        "PHONE-BUG.1",
        "PLAT.1",
        "CRM.2",
        "OPS.1",
        "COMMS.1",
        "CUTOVER.1",
        "CUTOVER.2",
    }
    assert (
        next(
            item for item in manifest.milestones if item.milestone_code == "PLAT.1"
        ).readiness_state
        == "complete"
    )
    assert not next(
        item for item in manifest.milestones if item.milestone_code == "CRM.2"
    ).preserve_active_execution
    assert all(
        next(
            item
            for item in manifest.milestones
            if item.milestone_code == milestone_code
        ).readiness_state
        == "complete"
        for milestone_code in (
            "CRM.2",
            "OPS.1",
            "COMMS.1",
            "CUTOVER.1",
            "CUTOVER.2",
        )
    )
    assert any(
        "u6k8f0h2j497" in warning and "re-parented onto u6k8g0c2d497" in warning
        for warning in manifest.integration_warnings
    )


def test_manifest_codes_are_traceable_to_approved_mmq_documents(manifest) -> None:
    repository = Path(__file__).resolve().parents[3]
    approved = "\n".join(
        (repository / path).read_text(encoding="utf-8")
        for path in manifest.source_documents
    )
    for milestone in manifest.milestones:
        assert milestone.milestone_code in approved


@pytest.mark.asyncio
async def test_dry_run_is_zero_write_deterministic_and_preserves_history(
    manifest,
) -> None:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    fixture = await seed_service_fixture(factory)
    service = SchedulerReconciliationService()
    try:
        async with factory() as session:
            active_crm_command = await EngineeringControlService().create_command(
                session,
                context=fixture.context,
                command=create_input(now=utc_now()),
            )
        async with factory() as session:
            roadmap = EngineeringRoadmap(
                company_id=fixture.context.company.id,
                title="Legacy Operations",
                repository_key="acp-enterprise",
                expected_branch="customer-management-v1",
                expected_head="a" * 40,
                status="active",
            )
            session.add(roadmap)
            await session.flush()
            session.add_all(
                [
                    EngineeringMilestone(
                        company_id=fixture.context.company.id,
                        roadmap_id=roadmap.id,
                        position=1,
                        title="Price Book Foundation V1",
                        objective="Legacy completed implementation.",
                        owning_workstream="Operations",
                        owning_branch="customer-management-v1",
                        authority=[],
                        constraints=[],
                        dependencies=[],
                        validation=[],
                        deliverables=[],
                        stop_conditions=[],
                        expected_completion_evidence=[],
                        status="running",
                        definition_approved=True,
                    ),
                    EngineeringMilestone(
                        company_id=fixture.context.company.id,
                        roadmap_id=roadmap.id,
                        position=2,
                        title="Close launch CRM gaps",
                        objective="Legacy active CRM execution.",
                        owning_workstream="CRM",
                        owning_branch="customer-management-v1",
                        authority=[],
                        constraints=[],
                        dependencies=[],
                        validation=[],
                        deliverables=[],
                        stop_conditions=[],
                        expected_completion_evidence=[],
                        status="running",
                        definition_approved=True,
                        command_id=active_crm_command.id,
                    ),
                ]
            )
            await session.commit()
            first = await service.dry_run(
                session, company_id=fixture.context.company.id, manifest=manifest
            )
            second = await service.dry_run(
                session, company_id=fixture.context.company.id, manifest=manifest
            )
            assert first == second
            assert first.mode == "dry_run"
            assert first.mutations_performed == 0
            assert first.destructive_operation_count == 0
            assert {
                item.permanent_capacity_identity for item in first.capacity_mappings
            } == {"OM1", "OM2", "MIG", "ECO", "LAP"}
            assert all(item.state == "unmapped" for item in first.capacity_mappings)
            assert any(
                item.milestone_code == "PRICEBOOK.1" for item in first.classifications
            )
            crm_classification = next(
                item for item in first.classifications if item.milestone_code == "CRM.2"
            )
            assert crm_classification.classification == "reconciliation-required"
            assert not any(
                transition.milestone_code == "CRM.2"
                for transition in first.proposed_transitions
            )
            pricebook_record_id = next(
                item.record_id
                for item in first.classifications
                if item.milestone_code == "PRICEBOOK.1"
            )
            stored = await session.get(EngineeringMilestone, pricebook_record_id)
            assert stored is not None
            assert stored.milestone_code is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_apply_requires_checkpoint_two_authority() -> None:
    service = SchedulerReconciliationService()

    class NoDatabaseAccess:
        pass

    with pytest.raises(SchedulerReconciliationError, match="Checkpoint 2"):
        await service.apply(
            NoDatabaseAccess(),  # type: ignore[arg-type]
            company_id=uuid4(),
            actor_user_id=uuid4(),
        )


def test_start_authority_states_are_fail_closed(manifest) -> None:
    states = {item.milestone_code: item.readiness_state for item in manifest.milestones}
    assert all(state != "ready" for state in states.values())
    assert states["PRICEBOOK.1"] == "complete"
    assert states["PHONE-BUG.1"] == "complete"
    assert states["PLAT.1"] == "complete"
    assert states["CRM.2"] == "complete"
    assert states["OPS.1"] == "complete"
    assert states["COMMS.1"] == "complete"
    assert states["CUTOVER.1"] == "complete"
    assert states["CUTOVER.2"] == "complete"
