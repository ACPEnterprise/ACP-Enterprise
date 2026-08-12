from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from app.core.config import settings
from app.database.session import get_database_session, get_security_database_session
from app.engineering_capacity.service import EngineeringCapacityService
from app.engineering_control.mobile.control import EngineeringWorkstreamControl
from app.engineering_control.mobile.roadmap_initialization import ROADMAPS
from app.engineering_control.mobile.roadmaps import EngineeringMilestone
from app.engineering_control.mobile.router import _bounded_projection, router
from app.engineering_control.mobile.schemas import MilestoneItem
from app.engineering_control.mobile.service import MobileEngineeringControlService
from app.engineering_control.models import EngineeringCommand
from app.engineering_control.registry import engineering_repository_registry
from app.engineering_control.review.service import EngineeringReviewService
from app.engineering_control.workstream_runtime import EngineeringWorkstreamRuntime
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import (
    EngineeringCommandPermission,
    EngineeringExecutionPermission,
)
from app.platform.permissions.dependencies import get_authorization_context
from app.worker_control.models import EngineeringWorker
from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.engineering_control.review.test_engineering_review import completed_command
from tests.engineering_control.test_engineering_command_service import (
    ServiceFixture,
    context_with_permissions,
    seed_service_fixture,
    utc_now,
)


@dataclass(frozen=True)
class MobileApiFixture:
    factory: async_sessionmaker[AsyncSession]
    service_fixture: ServiceFixture

    def app_for(
        self,
        permissions: tuple[str, ...],
        *,
        other_company: bool = False,
        membership_status: str = "active",
    ) -> FastAPI:
        source = (
            self.service_fixture.other_context
            if other_company
            else self.service_fixture.context
        )
        membership = replace(source.membership, status=membership_status)
        context = AuthorizationContext(
            user=source.user,
            company=source.company,
            membership=membership,
            authorized_branches=source.authorized_branches,
            active_branch=source.active_branch,
            effective_roles=(),
            effective_permissions=context_with_permissions(
                source.user, source.company, membership, permissions
            ).effective_permissions,
            credential_version=source.credential_version,
            authorization_version=source.authorization_version,
        )
        app = FastAPI()
        app.include_router(router)

        async def session_override() -> AsyncIterator[AsyncSession]:
            async with self.factory() as session:
                yield session

        async def context_override() -> AuthorizationContext:
            return context

        app.dependency_overrides[get_database_session] = session_override
        app.dependency_overrides[get_authorization_context] = context_override
        return app


@pytest_asyncio.fixture
async def mobile_api() -> AsyncIterator[MobileApiFixture]:
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    fixture = await seed_service_fixture(factory)
    try:
        yield MobileApiFixture(factory, fixture)
    finally:
        await engine.dispose()


async def request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    json: Mapping[str, object] | None = None,
    params: Mapping[str, str | int] | None = None,
) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.request(method, path, json=json, params=params)


def create_payload(*, suffix: str) -> dict[str, object]:
    return {
        "command_type": "owner_instruction",
        "owner_instruction": "Inspect the approved mobile API boundary.",
        "repository_key": "acp-enterprise",
        "expected_branch": "customer-management-v1",
        "expected_head": "a" * 40,
        "requested_code_changes": True,
        "expires_at": (utc_now() + timedelta(hours=2)).isoformat(),
        "idempotency_key": f"mobile-{suffix}",
    }


async def create_command(
    mobile_api: MobileApiFixture, *, suffix: str
) -> dict[str, object]:
    from app.engineering_control.commands import CreateEngineeringCommand
    from app.engineering_control.service import EngineeringControlService

    async with mobile_api.factory() as session:
        payload = create_payload(suffix=suffix)
        record = await EngineeringControlService().create_command(
            session,
            context=mobile_api.service_fixture.context,
            command=CreateEngineeringCommand(
                command_type=str(payload["command_type"]),
                owner_instruction=str(payload["owner_instruction"]),
                repository_key=str(payload["repository_key"]),
                expected_branch=str(payload["expected_branch"]),
                expected_head=str(payload["expected_head"]),
                requested_code_changes=bool(payload["requested_code_changes"]),
                expires_at=utc_now() + timedelta(hours=2),
                idempotency_key=str(payload["idempotency_key"]),
                execution_boundary={
                    "allowed_repository": str(payload["repository_key"]),
                    "allowed_branch": str(payload["expected_branch"]),
                    "expected_head": str(payload["expected_head"]),
                    "allowed_paths": ["backend/app/**"],
                    "forbidden_paths": [".git/**", ".env*", "**/.env*"],
                    "permitted_operations": [
                        "inspect",
                        "modify",
                        "validate",
                        "commit",
                        "mechanical_reconcile",
                        "push",
                    ],
                    "validation_requirements": ["git diff --check"],
                },
            ),
        )
    return {
        "id": str(record.id),
        "version": record.version,
        "instruction_digest": record.instruction_digest,
        "request_digest": record.request_digest,
        "repository_key": record.repository_key,
        "expected_branch": record.expected_branch,
        "expected_head": record.expected_head,
        "requested_code_changes": record.requested_code_changes,
    }


async def mark_scheduler_current(
    mobile_api: MobileApiFixture, *, title: str, readiness_state: str = "ready"
) -> None:
    """Test-only adoption of a fully approved manifest-backed milestone."""
    async with mobile_api.factory() as session, session.begin():
        milestone = await session.scalar(
            select(EngineeringMilestone).where(
                EngineeringMilestone.company_id
                == mobile_api.service_fixture.context.company.id,
                EngineeringMilestone.title == title,
            )
        )
        assert milestone is not None
        milestone.milestone_code = f"TEST.{milestone.position}"
        milestone.scheduler_version = "TEST.1"
        milestone.scheduler_fingerprint = "a" * 64
        milestone.permanent_capacity_identity = "OM1"
        milestone.readiness_state = readiness_state
        milestone.reconciliation_state = "current"


@pytest.mark.asyncio
async def test_pending_review_detail_approval_status_and_cancel(
    mobile_api: MobileApiFixture,
) -> None:
    command = await create_command(mobile_api, suffix="workflow")
    app = mobile_api.app_for(tuple(EngineeringCommandPermission.ALL))

    listed = await request(
        app,
        "GET",
        "/api/v1/engineering/mobile/reviews",
        params={"page": 1, "page_size": 10},
    )
    assert listed.status_code == 200
    assert listed.json()["total_count"] == 1
    assert listed.json()["items"][0]["approval_state"] == "awaiting_approval"
    assert "owner_instruction" not in listed.json()["items"][0]

    detail = await request(
        app, "GET", f"/api/v1/engineering/mobile/reviews/{command['id']}"
    )
    assert detail.status_code == 200
    assert detail.json()["can_approve"] is True
    assert detail.json()["execution_connected"] is False

    approval = {
        **{
            key: value for key, value in command.items() if key not in {"id", "version"}
        },
        "expected_version": command["version"],
    }
    mismatch = await request(
        app,
        "POST",
        f"/api/v1/engineering/mobile/reviews/{command['id']}/approve",
        json={**approval, "request_digest": "b" * 64},
    )
    assert mismatch.status_code == 409

    approved = await request(
        app,
        "POST",
        f"/api/v1/engineering/mobile/reviews/{command['id']}/approve",
        json=approval,
    )
    assert approved.status_code == 200
    assert approved.json()["approval_state"] == "approved"
    assert approved.json()["execution_state"] == "execution_not_connected"
    assert approved.json()["execution_connected"] is False

    status_response = await request(
        app,
        "GET",
        f"/api/v1/engineering/mobile/commands/{command['id']}/status",
    )
    assert status_response.status_code == 200
    assert status_response.json()["can_approve"] is False

    canceled = await request(
        app,
        "POST",
        f"/api/v1/engineering/mobile/reviews/{command['id']}/cancel",
        json={"expected_version": 2, "reason_code": "owner_requested"},
    )
    assert canceled.status_code == 200
    assert canceled.json()["approval_state"] == "canceled"
    assert canceled.json()["can_cancel"] is False


@pytest.mark.asyncio
async def test_workstream_projection_lists_authoritative_safe_next_action(
    mobile_api: MobileApiFixture,
) -> None:
    command = await create_command(mobile_api, suffix="workstream")
    app = mobile_api.app_for(tuple(EngineeringCommandPermission.ALL))

    response = await request(
        app,
        "GET",
        "/api/v1/engineering/mobile/workstreams",
        params={"page": 1, "page_size": 10},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["connectivity"]["state"] == "disconnected"
    assert body["items"] == [
        {
            "command_id": command["id"],
            "ecid": body["items"][0]["ecid"],
            "display_name": "Inspect the approved mobile API boundary",
            "repository_key": command["repository_key"],
            "expected_branch": command["expected_branch"],
            "expected_head": command["expected_head"],
            "approval_state": "awaiting_approval",
            "lifecycle_state": "awaiting_approval",
            "progress_summary": "Awaiting owner approval",
            "owner_action_required": True,
            "next_owner_action": "review_command",
            "connection_state": "disconnected",
            "assigned_worker_id": None,
            "execution_id": None,
            "offer_or_lease_state": None,
            "heartbeat_at": None,
            "review_id": None,
            "review_state": None,
            "authorization_id": None,
            "authorization_status": None,
            "repository_operation_id": None,
            "repository_operation_status": None,
            "failure_classification": None,
            "resulting_commit_sha": None,
            "repository_clean": None,
            "owner_attention_required": True,
            "updated_at": body["items"][0]["updated_at"],
            "pipeline_status": "waiting_for_owner",
            "desired_state": "active",
            "control_pending": False,
            "available_actions": ["cancel"],
            "runtime_state": "waiting_for_owner",
            "runtime_version": None,
            "acknowledged_action": None,
            "acknowledged_at": None,
            "acknowledgement_expires_at": None,
            "worker_health": None,
            "progress_percent": None,
            "current_activity": None,
            "scheduler_milestone_code": None,
            "scheduler_version": None,
            "permanent_capacity_identity": None,
            "authoritative_state": "waiting_for_owner_review",
            "reconciliation_state": "legacy_unreconciled",
            "stale_runtime": False,
            "acknowledgement_latency_ms": None,
            "execution_latency_ms": None,
            "validation_latency_ms": None,
            "deployment_latency_ms": None,
            "worker_uptime_seconds": None,
            "reconnect_count": 0,
        }
    ]

    detail = await request(
        app,
        "GET",
        f"/api/v1/engineering/mobile/workstreams/{command['id']}",
    )
    assert detail.status_code == 200
    assert detail.json()["pipeline_status"] == "waiting_for_owner"
    assert (
        detail.json()["owner_instruction"]
        == create_payload(suffix="workstream")["owner_instruction"]
    )

    paused = await request(
        app,
        "POST",
        f"/api/v1/engineering/mobile/workstreams/{command['id']}/actions",
        json={"action": "pause", "reason": "Owner review"},
    )
    assert paused.status_code == 200
    assert paused.json()["desired_state"] == "paused"

    refreshed = await request(
        app,
        "GET",
        f"/api/v1/engineering/mobile/workstreams/{command['id']}",
    )
    assert refreshed.json()["desired_state"] == "paused"
    assert refreshed.json()["control_pending"] is True
    assert refreshed.json()["available_actions"] == ["resume", "cancel"]


@pytest.mark.asyncio
async def test_scheduler_dry_run_is_approve_scoped_and_company_isolated(
    mobile_api: MobileApiFixture,
) -> None:
    read_only = mobile_api.app_for((EngineeringCommandPermission.READ,))
    denied = await request(
        read_only, "GET", "/api/v1/engineering/mobile/scheduler/reconciliation/dry-run"
    )
    assert denied.status_code == 403

    authorized = mobile_api.app_for(tuple(EngineeringCommandPermission.ALL))
    response = await request(
        authorized,
        "GET",
        "/api/v1/engineering/mobile/scheduler/reconciliation/dry-run",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "dry_run"
    assert body["destructive_operation_count"] == 0
    assert body["mutations_performed"] == 0
    assert body["before_counts"]["commands"] == 0
    assert {
        item["permanent_capacity_identity"] for item in body["capacity_mappings"]
    } == {"OM1", "OM2", "MIG", "ECO", "LAP"}


@pytest.mark.asyncio
async def test_roadmap_dispatch_and_safe_progression_owner_workflow(
    mobile_api: MobileApiFixture,
) -> None:
    permissions = tuple(
        EngineeringCommandPermission.ALL | EngineeringExecutionPermission.ALL
    )
    app = mobile_api.app_for(permissions)
    created = await request(
        app,
        "POST",
        "/api/v1/engineering/mobile/roadmaps",
        json={
            "title": "Mission Control",
            "repository_key": "acp-enterprise",
            "expected_branch": "customer-management-v1",
            "expected_head": "a" * 40,
            "milestones": [
                {
                    "title": "Milestone one",
                    "objective": "Complete the bounded first milestone.",
                    "authority": ["Milestone authority"],
                    "constraints": ["Stay in scope"],
                    "validation": ["Run focused tests"],
                    "deliverables": ["Validated result"],
                    "stop_conditions": ["Unrecoverable blocker"],
                    "expected_completion_evidence": ["Structured report"],
                    "approved": True,
                    "requested_code_changes": False,
                },
                {
                    "title": "Milestone two",
                    "objective": "Continue without copying a prompt.",
                    "approved": True,
                },
            ],
        },
    )
    assert created.status_code == 200, created.text
    await mark_scheduler_current(mobile_api, title="Milestone one")
    await mark_scheduler_current(mobile_api, title="Milestone two")
    roadmap = await request(app, "GET", "/api/v1/engineering/mobile/roadmaps")
    assert roadmap.status_code == 200
    body = roadmap.json()
    assert body["actionable_count"] == 1
    assert body["waiting_for_me"][0]["status"] == "ready"
    assert body["owner_attention"][0]["attention_class"] == "owner_action_required"
    assert body["owner_attention"][0]["available_owner_actions"] == [
        "start",
        "skip",
    ]
    assert body["dependency_waiting_milestones"][0]["title"] == "Milestone two"
    assert body["dependency_waiting_milestones"][0]["available_owner_actions"] == []
    first = body["waiting_for_me"][0]

    started = await request(
        app,
        "POST",
        f"/api/v1/engineering/mobile/milestones/{first['id']}/actions",
        json={"action": "start", "expected_version": first["version"]},
    )
    assert started.status_code == 200
    assert started.json()["status"] == "running"
    assert started.json()["command_id"] is not None
    assert started.json()["requested_code_changes"] is False
    after_start = (
        await request(app, "GET", "/api/v1/engineering/mobile/roadmaps")
    ).json()
    assert after_start["actionable_count"] == 0
    assert after_start["capacity_waiting_milestones"][0]["title"] == "Milestone one"
    async with mobile_api.factory() as session:
        capacity = await EngineeringCapacityService().summary(
            session, context=mobile_api.service_fixture.context
        )
        dispatched_command = await session.scalar(
            select(EngineeringCommand).where(
                EngineeringCommand.id == started.json()["command_id"]
            )
        )
    assert dispatched_command is not None
    queued = capacity.waiting_workstreams[0]
    assert queued.command_id == dispatched_command.id
    assert queued.milestone_title == "Milestone one"
    assert queued.milestone_position == 1
    assert queued.workstream == "Mission Control"
    assert queued.roadmap_title == "Mission Control"
    assert queued.owning_branch == "customer-management-v1"
    assert queued.identity_state == "resolved"
    assert dispatched_command.requested_code_changes is False

    async with mobile_api.factory() as session, session.begin():
        second_milestone = await session.scalar(
            select(EngineeringMilestone).where(
                EngineeringMilestone.title == "Milestone two"
            )
        )
        assert second_milestone is not None
        original_status = second_milestone.status
        second_milestone.command_id = dispatched_command.id
        second_milestone.status = "running"
    async with mobile_api.factory() as session:
        linked_milestones = (
            await session.scalars(
                select(EngineeringMilestone).where(
                    EngineeringMilestone.command_id == dispatched_command.id
                )
            )
        ).all()
        assert len(linked_milestones) == 2
        ambiguous_capacity = await EngineeringCapacityService().summary(
            session, context=mobile_api.service_fixture.context
        )
    ambiguous = ambiguous_capacity.waiting_workstreams[0]
    assert ambiguous.identity_state == "reconciliation_required"
    assert ambiguous.milestone_title is None
    assert ambiguous.decision == "reconciliation_required"
    assert ambiguous.assigned_worker_id is None
    async with mobile_api.factory() as session, session.begin():
        second_milestone = await session.scalar(
            select(EngineeringMilestone).where(
                EngineeringMilestone.title == "Milestone two"
            )
        )
        assert second_milestone is not None
        second_milestone.command_id = None
        second_milestone.status = original_status

    duplicate = await request(
        app,
        "POST",
        f"/api/v1/engineering/mobile/milestones/{first['id']}/actions",
        json={"action": "start", "expected_version": first["version"]},
    )
    assert duplicate.status_code == 409

    completed_at = utc_now()
    async with mobile_api.factory() as session, session.begin():
        item = await session.scalar(
            select(EngineeringMilestone).where(
                EngineeringMilestone.id == started.json()["id"]
            )
        )
        assert item is not None
        control = await session.scalar(
            select(EngineeringWorkstreamControl).where(
                EngineeringWorkstreamControl.command_id == item.command_id
            )
        )
        assert control is not None
        worker_id = uuid4()
        session.add(
            EngineeringWorker(
                id=worker_id,
                company_id=item.company_id,
                provider_identifier="acceptance-worker",
                name="Mission Control acceptance worker",
                worker_version="1.0",
                capabilities=["mission_control_milestone"],
                lifecycle_state="available",
                registered_by_user_id=mobile_api.service_fixture.context.user.id,
                registered_at=completed_at,
                last_heartbeat_at=completed_at,
                created_at=completed_at,
                updated_at=completed_at,
            )
        )
        await session.flush()
        session.add(
            EngineeringWorkstreamRuntime(
                company_id=item.company_id,
                command_id=item.command_id,
                control_id=control.id,
                worker_id=worker_id,
                worker_session_id=uuid4(),
                acknowledged_control_version=control.version,
                acknowledged_action="start",
                runtime_state="completed",
                worker_health="healthy",
                progress_percent=100,
                current_activity="Milestone validation completed",
                acknowledged_at=completed_at,
                acknowledgement_expires_at=completed_at + timedelta(minutes=5),
                heartbeat_at=completed_at,
                updated_at=completed_at,
            )
        )

    review = await request(app, "GET", "/api/v1/engineering/mobile/roadmaps")
    reviewed_first = next(
        item for item in review.json()["milestones"] if item["id"] == first["id"]
    )
    assert reviewed_first["status"] == "waiting_review"
    assert reviewed_first["attention_class"] == "owner_action_required"

    approved = await request(
        app,
        "POST",
        f"/api/v1/engineering/mobile/milestones/{first['id']}/actions",
        json={
            "action": "approve",
            "expected_version": reviewed_first["version"],
        },
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "completed"

    advanced = (await request(app, "GET", "/api/v1/engineering/mobile/roadmaps")).json()
    assert advanced["actionable_count"] == 1
    assert advanced["waiting_for_me"][0]["title"] == "Milestone two"
    assert advanced["waiting_for_me"][0]["status"] == "ready"
    assert advanced["waiting_for_me"][0]["command_id"] is None
    completed_first = next(
        item for item in advanced["milestones"] if item["id"] == first["id"]
    )
    assert completed_first["attention_class"] == "informational"
    assert completed_first["available_owner_actions"] == []

    # Advancement is promotion only. The sole command and control belong to the
    # milestone the owner explicitly started; the promoted milestone has no
    # execution state until a later owner Start action.
    async with mobile_api.factory() as session:
        company_id = mobile_api.service_fixture.context.company.id
        command_ids = tuple(
            (
                await session.scalars(
                    select(EngineeringCommand.id).where(
                        EngineeringCommand.company_id == company_id
                    )
                )
            ).all()
        )
        control_ids = tuple(
            (
                await session.scalars(
                    select(EngineeringWorkstreamControl.id).where(
                        EngineeringWorkstreamControl.company_id == company_id
                    )
                )
            ).all()
        )
        runtime_ids = tuple(
            (
                await session.scalars(
                    select(EngineeringWorkstreamRuntime.id).where(
                        EngineeringWorkstreamRuntime.company_id == company_id
                    )
                )
            ).all()
        )
    assert len(command_ids) == 1
    assert len(control_ids) == 1
    assert len(runtime_ids) == 1


def test_initial_roadmap_catalog_is_truthful_and_never_auto_dispatches() -> None:
    by_title = {item["title"]: item for item in ROADMAPS}
    assert set(by_title) == {
        "Customer Migration",
        "Business Economics",
        "Beacon",
        "Operations",
        "Mission Control",
    }
    all_milestones = [
        milestone for roadmap in ROADMAPS for milestone in roadmap["milestones"]
    ]
    ready = [item for item in all_milestones if item["status"] == "ready"]
    assert [item["title"] for item in ready] == [
        "BEA.6 Economics Signal Definitions",
        "Scheduling Readiness",
        "Mission Control V2.1 Phone Acceptance Rehearsal",
    ]
    assert ready[-1]["requested_code_changes"] is False
    assert (
        by_title["Mission Control"]["branch"]
        == engineering_repository_registry.resolve(
            "acp-enterprise"
        ).approved_active_branch
    )
    beacon = by_title["Beacon"]
    bea6 = next(
        item
        for item in beacon["milestones"]
        if item["title"] == "BEA.6 Economics Signal Definitions"
    )
    approved_branch = engineering_repository_registry.resolve(
        "acp-enterprise"
    ).approved_active_branch
    assert beacon["branch"] == approved_branch
    assert bea6["branch"] == approved_branch
    assert {
        item["title"]
        for item in all_milestones
        if item["status"] == "externally_running"
    } == {
        "Operational Migration Phase 2 — Estimates, Invoices, and Payments",
    }


def test_v22_catalog_has_ordered_approved_dependency_chains() -> None:
    expected = {
        "Customer Migration": (
            (
                "Complete Historical Job Boundary",
                "draft",
                ("Remaining Customer/Location Owner Disposition",),
            ),
            (
                "Multi-Property Customer Expansion",
                "draft",
                (),
            ),
            (
                "Historical Notes Migration",
                "draft",
                ("Multi-Property Customer Expansion",),
            ),
            ("Attachment Migration", "draft", ("Historical Notes Migration",)),
        ),
        "Business Economics": (
            (
                "Accounting Integration",
                "draft",
                ("Phase 4 — Accounting Integration and Financial Close",),
            ),
            ("Financial Close", "draft", ("Accounting Integration",)),
            ("General Ledger Reconciliation", "draft", ("Financial Close",)),
            ("Projection Publication", "draft", ("General Ledger Reconciliation",)),
        ),
        "Beacon": (
            (
                "BEA.6 Economics Signal Definitions",
                "ready",
                ("BEA.5 Business Economics Signal Integration",),
            ),
            (
                "BEA.7 Signal Evaluation",
                "draft",
                ("BEA.6 Economics Signal Definitions",),
            ),
            ("BEA.8 Signal Lifecycle", "draft", ("BEA.7 Signal Evaluation",)),
            ("BEA.9 Beacon Dashboard", "draft", ("BEA.8 Signal Lifecycle",)),
        ),
        "Operations": (
            ("Scheduling Readiness", "ready", ()),
            ("Dispatch Readiness", "draft", ("Scheduling Readiness",)),
            ("Estimate Workspace", "draft", ("Dispatch Readiness",)),
        ),
    }
    by_roadmap = {item["title"]: item for item in ROADMAPS}
    populated = []
    for roadmap_title, chain in expected.items():
        milestones = {
            item["title"]: item for item in by_roadmap[roadmap_title]["milestones"]
        }
        positions = []
        for title, status, dependencies in chain:
            item = milestones[title]
            populated.append(item)
            positions.append(
                next(
                    index
                    for index, candidate in enumerate(
                        by_roadmap[roadmap_title]["milestones"]
                    )
                    if candidate["title"] == title
                )
            )
            assert item["status"] == status
            assert item["approved"] is True
            assert tuple(item["dependencies"]) == dependencies
            assert any(
                constraint.startswith("Estimated duration: ")
                for constraint in item["constraints"]
            )
            assert any(
                "explicit authenticated owner Start" in constraint
                for constraint in item["constraints"]
            )
        assert positions == sorted(positions)
        assert sum(item["status"] == "ready" for item in populated[-len(chain) :]) <= 1
    assert len(populated) == 15


def test_invalid_milestone_does_not_blank_roadmap_projection() -> None:
    now = utc_now()
    values = {
        "id": uuid4(),
        "roadmap_id": uuid4(),
        "position": 1,
        "title": "Valid milestone",
        "objective": "Remain visible when an adjacent record is malformed.",
        "owning_workstream": "Mission Control",
        "owning_branch": "customer-management-v1",
        "authority": [],
        "constraints": [],
        "dependencies": [],
        "validation": [],
        "deliverables": [],
        "stop_conditions": [],
        "expected_completion_evidence": [],
        "status": "ready",
        "definition_approved": True,
        "requested_code_changes": False,
        "external_evidence": None,
        "command_id": None,
        "version": 1,
        "started_at": None,
        "completed_at": None,
        "reviewed_at": None,
        "created_at": now,
        "updated_at": now,
    }
    valid = SimpleNamespace(**values)
    invalid = SimpleNamespace(**{**values, "id": uuid4(), "objective": None})

    items, warnings = _bounded_projection((valid, invalid), MilestoneItem, "milestone")

    assert [item.title for item in items] == ["Valid milestone"]
    assert warnings == (
        "One milestone record is unavailable because its stored definition is invalid.",
    )


@pytest.mark.asyncio
async def test_start_reports_repository_policy_rejection_as_api_error(
    mobile_api: MobileApiFixture,
) -> None:
    permissions = tuple(
        EngineeringCommandPermission.ALL | EngineeringExecutionPermission.ALL
    )
    app = mobile_api.app_for(permissions)
    created = await request(
        app,
        "POST",
        "/api/v1/engineering/mobile/roadmaps",
        json={
            "title": "Invalid dispatch coordinates",
            "repository_key": "acp-enterprise",
            "expected_branch": "mission-control-v2.1",
            "expected_head": "a" * 40,
            "milestones": [
                {
                    "title": "Read-only inspection",
                    "objective": "Prove policy failures are returned to the owner.",
                    "approved": True,
                    "requested_code_changes": False,
                }
            ],
        },
    )
    assert created.status_code == 200
    await mark_scheduler_current(mobile_api, title="Read-only inspection")
    listing = (await request(app, "GET", "/api/v1/engineering/mobile/roadmaps")).json()
    milestone = next(
        item
        for item in listing["milestones"]
        if item["title"] == "Read-only inspection"
    )

    rejected = await request(
        app,
        "POST",
        f"/api/v1/engineering/mobile/milestones/{milestone['id']}/actions",
        json={"action": "start", "expected_version": milestone["version"]},
    )

    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "engineering_command_invalid"


@pytest.mark.asyncio
async def test_realtime_stream_rejects_unknown_company_resume_token(
    mobile_api: MobileApiFixture,
) -> None:
    app = mobile_api.app_for(tuple(EngineeringCommandPermission.ALL))
    response = await request(
        app,
        "GET",
        f"/api/v1/engineering/mobile/events?after={uuid4()}",
    )
    assert response.status_code == 409
    assert "resume token" in response.json()["detail"]


def test_realtime_authentication_sessions_close_before_streaming_response() -> None:
    route = next(
        item
        for item in router.routes
        if getattr(item, "path", "") == "/api/v1/engineering/mobile/events"
    )

    def dependencies(dependant: Dependant) -> list[Dependant]:
        nested = list(dependant.dependencies)
        return nested + [child for item in nested for child in dependencies(item)]

    security_sessions = [
        dependency
        for dependency in dependencies(route.dependant)
        if dependency.call is get_security_database_session
    ]
    assert len(security_sessions) == 2
    assert all(dependency.scope == "function" for dependency in security_sessions)


@pytest.mark.asyncio
async def test_permissions_inactive_membership_and_company_concealment(
    mobile_api: MobileApiFixture,
) -> None:
    command = await create_command(mobile_api, suffix="auth")
    no_read = mobile_api.app_for((EngineeringCommandPermission.MANAGE,))
    denied = await request(no_read, "GET", "/api/v1/engineering/mobile/reviews")
    assert denied.status_code == 403
    workstreams_denied = await request(
        no_read, "GET", "/api/v1/engineering/mobile/workstreams"
    )
    assert workstreams_denied.status_code == 403

    inactive = mobile_api.app_for(
        tuple(EngineeringCommandPermission.ALL), membership_status="suspended"
    )
    denied = await request(inactive, "GET", "/api/v1/engineering/mobile/reviews")
    assert denied.status_code == 403

    other_company = mobile_api.app_for(
        tuple(EngineeringCommandPermission.ALL), other_company=True
    )
    concealed = await request(
        other_company,
        "GET",
        f"/api/v1/engineering/mobile/reviews/{command['id']}",
    )
    assert concealed.status_code == 404


@pytest.mark.asyncio
async def test_owner_review_projection_uses_immutable_review_packages(
    mobile_api: MobileApiFixture,
) -> None:
    command = await completed_command(mobile_api.service_fixture)
    owner = mobile_api.app_for(tuple(EngineeringCommandPermission.ALL))
    async with mobile_api.factory() as session:
        package = await EngineeringReviewService().prepare(
            session,
            context=context_with_permissions(
                mobile_api.service_fixture.context.user,
                mobile_api.service_fixture.context.company,
                mobile_api.service_fixture.context.membership,
                tuple(EngineeringCommandPermission.ALL),
            ),
            command_id=command.id,
        )

    listed = await request(
        owner,
        "GET",
        "/api/v1/engineering/mobile/owner-reviews",
        params={"page": 1, "page_size": 10},
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["total_count"] == 1
    assert body["connectivity"]["state"] == "disconnected"
    assert body["connectivity"]["session_id"] is None
    item = body["items"][0]
    assert item["id"] == str(package.review.id)
    assert item["command_id"] == str(command.id)
    assert item["execution_id"] == str(package.review.execution_id)
    assert item["provider_identifier"] == package.review.provider_identifier
    assert item["result_disposition"] == package.result_disposition
    assert item["validation_summary"] == package.validation_summary
    assert item["file_boundary"] == package.validation_summary.get("file_boundary", [])
    assert item["state"] == "pending"
    assert item["decision"] is None
    assert "review_digest" not in item
    assert "credential" not in str(body).lower()

    other_company = mobile_api.app_for(
        tuple(EngineeringCommandPermission.ALL), other_company=True
    )
    concealed = await request(
        other_company,
        "GET",
        "/api/v1/engineering/mobile/owner-reviews",
    )
    assert concealed.status_code == 200
    assert concealed.json()["items"] == []


def test_mobile_openapi_exposes_no_rejection_or_execution_operation() -> None:
    app = FastAPI()
    app.include_router(router)
    paths = app.openapi()["paths"]
    assert "/api/v1/engineering/mobile/reviews" in paths
    assert "/api/v1/engineering/mobile/reviews/{command_id}/approve" in paths
    assert all("reject" not in path and "execute" not in path for path in paths)


def test_connectivity_projection_distinguishes_connecting_fresh_and_stale() -> None:
    now = datetime(2026, 7, 27, 23, 0, tzinfo=timezone.utc)

    assert (
        MobileEngineeringControlService._connectivity_state(heartbeat_at=None, now=now)
        == "connecting"
    )
    assert (
        MobileEngineeringControlService._connectivity_state(
            heartbeat_at=now - timedelta(seconds=90), now=now
        )
        == "connected"
    )
    assert (
        MobileEngineeringControlService._connectivity_state(
            heartbeat_at=now - timedelta(seconds=91), now=now
        )
        == "disconnected"
    )


def test_file_boundary_falls_back_to_controlled_workspace_evidence() -> None:
    assert MobileEngineeringControlService._file_boundary(
        {"controlled_execution": True},
        {"file_boundary": ("README.md",)},
    ) == ("README.md",)


def test_expired_unresolved_lease_projects_reconciliation_not_running() -> None:
    now = datetime(2026, 8, 12, 18, 0, tzinfo=timezone.utc)
    status = SimpleNamespace(
        lease=SimpleNamespace(
            status="active", expires_at=now - timedelta(minutes=1)
        ),
        monitoring_state="running",
    )
    runtime = SimpleNamespace(runtime_state="acknowledged")

    pipeline = MobileEngineeringControlService._pipeline_status(
        command=SimpleNamespace(),
        status=status,
        desired_state="active",
        runtime=runtime,
        now=now,
    )

    assert pipeline == "reconciliation_required"
    assert (
        MobileEngineeringControlService._authoritative_state(pipeline, None)
        == "reconciliation_required"
    )
