from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.engineering_control.mobile.roadmaps import (
    EngineeringMilestone,
    EngineeringRoadmap,
)
from app.engineering_control.scheduler.manifest import (
    load_scheduler_manifest,
    release_bound_manifest,
)
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
    assert manifest.scheduler_version == "MMQ.5-2026-08-27.9"
    assert (
        manifest.fingerprint
        == "9efea5198540c476bf1064b26151d86f273102bb1d5e594a56466a2bb570ae7a"
    )
    assert (
        manifest.authoritative_repository_head
        == "7a9314b4647563eefaa48a755101e0f9cdf93602"
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
        "EST.4",
        "DISP.2",
        "INV.3-LEGACY",
        "PHONE-WEEKEND.2",
        "MIG.1",
        "MIG.PREP.2",
        "MIG.2",
        "BE.8",
        "BE.PLAN.1",
        "BE.REVIEW.1",
        "BE.EVIDENCE.1",
        "BE.GAP.1",
        "BE.9",
        "INV.2A",
        "TECH.1",
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
            "EST.4",
            "DISP.2",
            "INV.3-LEGACY",
            "PHONE-WEEKEND.2",
            "MIG.1",
            "MIG.PREP.2",
            "BE.8",
            "BE.PLAN.1",
            "BE.REVIEW.1",
            "BE.EVIDENCE.1",
            "BE.GAP.1",
        )
    )
    pricebook = next(
        item for item in manifest.milestones if item.milestone_code == "PRICEBOOK.1"
    )
    assert pricebook.legacy_titles == ("Price Book Foundation V1",)
    assert pricebook.superseded_legacy_titles == ("Price Book",)
    tech = next(item for item in manifest.milestones if item.milestone_code == "TECH.1")
    assert tech.execution_boundary is not None
    assert tech.permanent_capacity_identity == "OM1"
    assert manifest.capacities[0].worker_id == UUID(
        "d4eeead4-455e-4c2d-a87a-7c2abba3db5a"
    )
    assert tech.execution_boundary.boundary_id == "TECH.1"
    assert tech.execution_boundary.boundary_version == 2
    assert tech.execution_boundary.fingerprint == (
        "04980ac90a5d1ed0e379600ab7e02cdc4f74fc767572c10cd35a79e3280442c9"
    )


def test_release_binding_refreshes_code_candidate_heads_without_mutating_history() -> (
    None
):
    release = "a" * 40
    manifest = release_bound_manifest(release)
    tech = next(item for item in manifest.milestones if item.milestone_code == "TECH.1")
    pricebook = next(
        item for item in manifest.milestones if item.milestone_code == "PRICEBOOK.1"
    )
    assert manifest.authoritative_repository_head == release
    assert manifest.scheduler_version.endswith("+aaaaaaaaaaaa")
    assert tech.starting_commit_evidence["authoritative_head"] == release
    assert pricebook.starting_commit_evidence["commit"] == (
        "e97dc408742e0037330b79156cd0a5ba583c6649"
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
                    EngineeringMilestone(
                        company_id=fixture.context.company.id,
                        roadmap_id=roadmap.id,
                        position=3,
                        title="Price Book",
                        objective="Legacy generic placeholder.",
                        owning_workstream="Operations",
                        owning_branch="customer-management-v1",
                        authority=[],
                        constraints=[],
                        dependencies=[],
                        validation=[],
                        deliverables=[],
                        stop_conditions=[],
                        expected_completion_evidence=[],
                        status="draft",
                        definition_approved=False,
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
            assert not first.ambiguous_record_ids
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
            superseded = next(
                item
                for item in first.classifications
                if item.classification == "superseded"
                and item.reason.startswith("The scheduler explicitly supersedes")
            )
            assert any(
                transition.record_id == superseded.record_id
                and transition.record_type == "milestone_supersession"
                and transition.to_state == "superseded"
                for transition in first.proposed_transitions
            )
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
    assert {code for code, state in states.items() if state == "ready"} == {"TECH.1"}
    assert states["PRICEBOOK.1"] == "complete"
    assert states["PHONE-BUG.1"] == "complete"
    assert states["PLAT.1"] == "complete"
    assert states["CRM.2"] == "complete"
    assert states["OPS.1"] == "complete"
    assert states["COMMS.1"] == "complete"
    assert states["EST.4"] == "complete"
    assert states["DISP.2"] == "complete"
    assert states["INV.3-LEGACY"] == "complete"
    assert states["PHONE-WEEKEND.2"] == "complete"
    assert states["MIG.2"] == "blocked"
    assert states["BE.9"] == "blocked"
    assert states["INV.2A"] == "blocked"


@pytest.mark.asyncio
async def test_apply_supersedes_legacy_pricebook_identity_idempotently(
    manifest,
) -> None:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    fixture = await seed_service_fixture(factory)
    service = SchedulerReconciliationService()
    try:
        async with factory() as session, session.begin():
            roadmap = EngineeringRoadmap(
                company_id=fixture.context.company.id,
                title="Legacy Price Book Roadmaps",
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
                        objective="Canonical completed milestone.",
                        owning_workstream="Sales / Commercial Operations",
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
                        title="Price Book",
                        objective="Historical generic placeholder.",
                        owning_workstream="Operations",
                        owning_branch="customer-management-v1",
                        authority=[],
                        constraints=[],
                        dependencies=[],
                        validation=[],
                        deliverables=[],
                        stop_conditions=[],
                        expected_completion_evidence=[],
                        status="draft",
                        definition_approved=False,
                    ),
                ]
            )
        async with factory() as session:
            first = await service.apply(
                session,
                company_id=fixture.context.company.id,
                actor_user_id=fixture.context.user.id,
                checkpoint_2_authorized=True,
            )
            second = await service.apply(
                session,
                company_id=fixture.context.company.id,
                actor_user_id=fixture.context.user.id,
                checkpoint_2_authorized=True,
            )
            assert first.mode == "apply"
            assert first.mutations_performed > 0
            assert second.mutations_performed == 0
            milestones = tuple(
                (
                    await session.scalars(
                        select(EngineeringMilestone).where(
                            EngineeringMilestone.company_id
                            == fixture.context.company.id,
                            EngineeringMilestone.title.in_(
                                ("Price Book Foundation V1", "Price Book")
                            ),
                        )
                    )
                ).all()
            )
            canonical = next(x for x in milestones if x.title.endswith("V1"))
            historical = next(x for x in milestones if x.title == "Price Book")
            assert canonical.milestone_code == "PRICEBOOK.1"
            assert canonical.reconciliation_state == "current"
            assert canonical.status == "completed"
            assert historical.milestone_code is None
            assert historical.status == "draft"
            assert historical.reconciliation_state == "superseded"
            tech = await session.scalar(
                select(EngineeringMilestone).where(
                    EngineeringMilestone.company_id == fixture.context.company.id,
                    EngineeringMilestone.milestone_code == "TECH.1",
                )
            )
            assert tech is not None
            boundary = tech.starting_commit_evidence["execution_boundary"]
            assert isinstance(boundary, dict)
            assert boundary["boundary_id"] == "TECH.1"
            assert boundary["boundary_version"] == 2
            assert boundary["fingerprint"] == (
                "04980ac90a5d1ed0e379600ab7e02cdc4f74fc767572c10cd35a79e3280442c9"
            )
    finally:
        await engine.dispose()
