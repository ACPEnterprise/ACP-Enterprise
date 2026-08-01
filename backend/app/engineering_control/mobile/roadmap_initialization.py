"""Approved ACP Enterprise roadmap catalog and one-time Preview initialization."""

import asyncio
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionFactory
from app.platform.company.models import Company

from .roadmaps import (
    EngineeringMilestone,
    EngineeringMilestoneEvent,
    EngineeringRoadmap,
)

COMPLETED_AUTHORITY = ["Recorded completion evidence only; no execution authority."]
STANDARD_STOP = [
    (
        "Stop for irreversible production impact, an out-of-scope architecture "
        "decision, significant security or data-integrity risk, or an "
        "unrecoverable blocker."
    )
]


def completed(title: str, branch: str) -> dict[str, Any]:
    return {
        "title": title,
        "objective": f"Preserve the completed {title} milestone as durable roadmap truth.",
        "status": "completed",
        "approved": True,
        "branch": branch,
        "authority": COMPLETED_AUTHORITY,
        "constraints": ["Do not redispatch completed work."],
        "dependencies": [],
        "validation": ["Verify the milestone commit and completion report exist."],
        "deliverables": ["Durable completion record."],
        "evidence": ["Committed milestone history."],
    }


def draft(
    title: str, objective: str, branch: str, dependencies: Sequence[str]
) -> dict[str, Any]:
    return {
        "title": title,
        "objective": objective,
        "status": "draft",
        "approved": False,
        "branch": branch,
        "authority": ["Definition preparation only; execution is not approved."],
        "constraints": [
            "Do not dispatch until the owner approves a complete work order."
        ],
        "dependencies": list(dependencies),
        "validation": ["Define milestone-specific validation before approval."],
        "deliverables": ["Owner-approved detailed milestone definition."],
        "evidence": ["Approved definition and dependency evidence."],
    }


def approved_milestone(
    title: str,
    objective: str,
    branch: str,
    dependencies: Sequence[str],
    estimated_duration: str,
    *,
    ready: bool = False,
    externally_adoptable: bool = False,
) -> dict[str, Any]:
    """Define approved roadmap work without granting execution authority."""
    return {
        "title": title,
        "objective": objective,
        "status": "ready" if ready else "draft",
        "approved": True,
        "externally_adoptable": externally_adoptable,
        "branch": branch,
        "authority": [
            "Operate under milestone-level authority after an authenticated owner explicitly starts this milestone."
        ],
        "constraints": [
            "Do not dispatch or execute without an explicit authenticated owner Start action.",
            f"Estimated duration: {estimated_duration}.",
        ],
        "dependencies": list(dependencies),
        "validation": [
            "Run milestone-focused tests and applicable regression, typing, lint, and production-build checks."
        ],
        "deliverables": [f"Complete and validate {title}."],
        "evidence": [
            "Committed implementation, clean validation results, and durable completion evidence."
        ],
    }


ROADMAPS: tuple[Mapping[str, Any], ...] = (
    {
        "title": "Customer Migration",
        # Future Mission Control dispatch uses the repository registry's approved
        # execution branch. The adopted milestone retains its external branch.
        "branch": "customer-management-v1",
        "head": "eb63fe8ccbc936bcb38104d159bb3742bf967d31",
        "milestones": (
            completed(
                "Deterministic Customer Migration", "customer-migration-workstream"
            ),
            completed(
                "Operational Migration Phase 1 — Jobs and Appointments",
                "customer-migration-workstream",
            ),
            {
                "title": "Operational Migration Phase 2 — Estimates, Invoices, and Payments",
                "objective": "Complete and reconcile deterministic financial-history migration and owner-facing migrated history workflows.",
                "status": "externally_running",
                "approved": True,
                "branch": "customer-migration-workstream",
                "authority": [
                    "Continue only within the active Customer Migration worktree."
                ],
                "constraints": [
                    "Do not dispatch a duplicate Mission Control command.",
                    "Do not alter production data or cut over production.",
                ],
                "dependencies": [
                    "Operational Migration Phase 1 — Jobs and Appointments"
                ],
                "validation": [
                    "Run financial migration regression and fresh-schema validation.",
                    "Reconcile Preview history counts without production access.",
                ],
                "deliverables": [
                    "Validated financial migration stages and history workflows."
                ],
                "evidence": [
                    "Branch customer-migration-workstream at 51f6d059; active isolated Codex worktree."
                ],
            },
            draft(
                "Notes and Attachments Migration",
                "Define deterministic migration of customer, job, and financial notes and attachments.",
                "customer-migration-workstream",
                ["Operational Migration Phase 2 — Estimates, Invoices, and Payments"],
            ),
            draft(
                "Owner Disposition Resolution",
                "Define owner review and disposition for records that cannot be reconciled automatically.",
                "customer-migration-workstream",
                ["Notes and Attachments Migration"],
            ),
            draft(
                "Cutover Reconciliation",
                "Define final source-to-target reconciliation and a reversible non-production cutover rehearsal.",
                "customer-migration-workstream",
                ["Owner Disposition Resolution"],
            ),
            approved_milestone(
                "Complete Historical Job Boundary",
                "Complete the approved deterministic boundary for historical job migration without changing active migration execution.",
                "customer-migration-workstream",
                ["Remaining Customer/Location Owner Disposition"],
                "5 engineering days",
            ),
            approved_milestone(
                "Multi-Property Customer Expansion",
                "Expand deterministic customer migration to approved multi-property relationships and reconciliation evidence.",
                "customer-migration-workstream",
                [],
                "5 engineering days",
                externally_adoptable=True,
            ),
            approved_milestone(
                "Historical Notes Migration",
                "Migrate approved historical notes with deterministic ownership, ordering, and reconciliation.",
                "customer-migration-workstream",
                ["Multi-Property Customer Expansion"],
                "4 engineering days",
            ),
            approved_milestone(
                "Attachment Migration",
                "Migrate approved historical attachments with bounded storage, integrity, and reconciliation controls.",
                "customer-migration-workstream",
                ["Historical Notes Migration"],
                "5 engineering days",
            ),
            approved_milestone(
                "Remaining Customer/Location Owner Disposition",
                "Resolve remaining customer and location ownership dispositions with durable owner evidence.",
                "customer-migration-workstream",
                ["Attachment Migration"],
                "4 engineering days",
            ),
        ),
    },
    {
        "title": "Business Economics",
        "branch": "customer-management-v1",
        "head": "eb63fe8ccbc936bcb38104d159bb3742bf967d31",
        "milestones": (
            completed("Foundation Phase 1", "business-economics-foundation"),
            completed("ECON.1R Reconciliation", "business-economics-foundation"),
            completed(
                "Phase 2 Authoritative Fact Ingestion", "business-economics-foundation"
            ),
            completed(
                "Phase 3 Allocation Integrity and Accounting Period Control",
                "business-economics-foundation",
            ),
            {
                "title": "Phase 4 — Accounting Integration and Financial Close",
                "objective": "Integrate approved accounting boundaries and establish a controlled financial-close workflow on authoritative economic facts.",
                "status": "planned",
                "approved": True,
                "externally_adoptable": True,
                "branch": "business-economics-foundation",
                "authority": [
                    "Operate within the approved Business Economics workstream."
                ],
                "constraints": [
                    "Preserve authoritative fact and allocation invariants.",
                    "Do not create production accounting entries or alter production ledgers.",
                    "Do not duplicate the active isolated workstream.",
                ],
                "dependencies": [
                    "Phase 3 Allocation Integrity and Accounting Period Control"
                ],
                "validation": [
                    "Run economics regression, accounting-boundary tests, typing, and fresh migration.",
                    "Prove close operations are versioned, balanced, and auditable.",
                ],
                "deliverables": [
                    "Accounting integration contracts and controlled close evidence."
                ],
                "evidence": [
                    "Active business-economics-foundation worktree based on completed Phase 3 head 3940d1d."
                ],
            },
            draft(
                "Financial Integrity Readiness Gate for Beacon",
                "Define the integrity gate required before economics facts can drive Beacon decisions.",
                "business-economics-foundation",
                ["Phase 4 — Accounting Integration and Financial Close"],
            ),
            draft(
                "Profitability Intelligence Projections",
                "Define bounded profitability projections from authoritative economic facts.",
                "business-economics-foundation",
                ["Financial Integrity Readiness Gate for Beacon"],
            ),
            approved_milestone(
                "Accounting Integration",
                "Complete the approved accounting integration boundary after the active Phase 4 work is reconciled.",
                "business-economics-foundation",
                ["Phase 4 — Accounting Integration and Financial Close"],
                "5 engineering days",
            ),
            approved_milestone(
                "Phase 5 — Accounting Operationalization",
                "Operationalize approved accounting and close controls without creating production ledger authority.",
                "business-economics-foundation",
                ["Phase 4 — Accounting Integration and Financial Close"],
                "5 engineering days",
            ),
            approved_milestone(
                "General Ledger Reconciliation and Export Readiness",
                "Prove reconciled general-ledger boundaries and bounded export readiness.",
                "business-economics-foundation",
                ["Phase 5 — Accounting Operationalization"],
                "5 engineering days",
            ),
            approved_milestone(
                "Period Audit and Projection Publication",
                "Publish versioned period-audit evidence and approved projections.",
                "business-economics-foundation",
                ["General Ledger Reconciliation and Export Readiness"],
                "4 engineering days",
            ),
            approved_milestone(
                "Financial Integrity Gate for Beacon",
                "Establish the approved financial-integrity gate before Beacon consumes economics facts.",
                "business-economics-foundation",
                ["Period Audit and Projection Publication"],
                "4 engineering days",
            ),
            approved_milestone(
                "Financial Close",
                "Establish the approved repeatable financial-close workflow on reconciled accounting facts.",
                "business-economics-foundation",
                ["Accounting Integration"],
                "4 engineering days",
            ),
            approved_milestone(
                "General Ledger Reconciliation",
                "Reconcile authoritative economic facts and approved close outputs against the general ledger.",
                "business-economics-foundation",
                ["Financial Close"],
                "4 engineering days",
            ),
            approved_milestone(
                "Projection Publication",
                "Publish approved projections from reconciled financial facts with versioned evidence.",
                "business-economics-foundation",
                ["General Ledger Reconciliation"],
                "4 engineering days",
            ),
        ),
    },
    {
        "title": "Beacon",
        # Dispatch must target the repository registry's approved active branch.
        # The Beacon workstream name remains durable milestone metadata; it is
        # not an independently authorized execution branch.
        "branch": "customer-management-v1",
        "head": "eb63fe8ccbc936bcb38104d159bb3742bf967d31",
        "milestones": (
            completed(
                "Beacon Signal Intelligence Engine / BEA.4", "beacon-economics-signals"
            ),
            completed(
                "BEA.5 Business Economics Signal Integration",
                "beacon-economics-signals",
            ),
            draft(
                "Signal Definition Expansion",
                "Define the next approved set of operator-facing business signals.",
                "beacon-economics-signals",
                ["BEA.5 Business Economics Signal Integration"],
            ),
            draft(
                "Signal Evaluation and Lifecycle",
                "Define signal evaluation, acknowledgement, resolution, and retirement semantics.",
                "beacon-economics-signals",
                ["Signal Definition Expansion"],
            ),
            draft(
                "Beacon Owner Experience",
                "Define the phone-first owner experience for reviewed and actionable Beacon signals.",
                "beacon-economics-signals",
                ["Signal Evaluation and Lifecycle"],
            ),
            approved_milestone(
                "BEA.6 Economics Signal Definitions",
                "Define the approved economics-backed Beacon signals and their authoritative inputs.",
                "customer-management-v1",
                ["BEA.5 Business Economics Signal Integration"],
                "4 engineering days",
                ready=True,
            ),
            approved_milestone(
                "BEA.7 Signal Evaluation",
                "Implement deterministic evaluation of approved Beacon signal definitions.",
                "beacon-economics-signals",
                ["BEA.6 Economics Signal Definitions"],
                "5 engineering days",
            ),
            approved_milestone(
                "BEA.8 Signal Lifecycle",
                "Implement the approved acknowledgement, resolution, and retirement lifecycle for Beacon signals.",
                "beacon-economics-signals",
                ["BEA.7 Signal Evaluation"],
                "4 engineering days",
            ),
            approved_milestone(
                "BEA.9 Beacon Dashboard",
                "Deliver the approved owner-facing Beacon dashboard over durable signal truth.",
                "beacon-economics-signals",
                ["BEA.8 Signal Lifecycle"],
                "5 engineering days",
            ),
        ),
    },
    {
        "title": "Operations",
        "branch": "customer-management-v1",
        "head": "eb63fe8ccbc936bcb38104d159bb3742bf967d31",
        "milestones": tuple(
            draft(title, objective, "customer-management-v1", dependencies)
            for title, objective, dependencies in (
                (
                    "Real-Data Scheduling, Dispatch, and Jobs Readiness",
                    "Define the readiness gate for production-like operational scheduling, dispatch, and jobs data.",
                    (),
                ),
                (
                    "Price Book",
                    "Define the authoritative operational price-book milestone.",
                    ("Real-Data Scheduling, Dispatch, and Jobs Readiness",),
                ),
                (
                    "Estimates",
                    "Define the estimate lifecycle milestone.",
                    ("Price Book",),
                ),
                (
                    "Invoicing",
                    "Define the invoice lifecycle milestone.",
                    ("Estimates",),
                ),
                ("Payments", "Define the payment lifecycle milestone.", ("Invoicing",)),
            )
        )
        + (
            approved_milestone(
                "Scheduling Readiness",
                "Establish the approved real-data scheduling readiness boundary and evidence.",
                "customer-management-v1",
                [],
                "5 engineering days",
                ready=True,
            ),
            approved_milestone(
                "Dispatch Readiness",
                "Establish the approved dispatch readiness boundary on validated scheduling truth.",
                "customer-management-v1",
                ["Scheduling Readiness"],
                "4 engineering days",
            ),
            approved_milestone(
                "Estimate Workspace",
                "Deliver the approved estimate workspace on validated operational foundations.",
                "customer-management-v1",
                ["Dispatch Readiness"],
                "5 engineering days",
            ),
        ),
    },
    {
        "title": "Mission Control",
        "branch": "customer-management-v1",
        "head": "eb63fe8ccbc936bcb38104d159bb3742bf967d31",
        "milestones": tuple(
            completed(title, branch)
            for title, branch in (
                ("PHONE.4", "phone4-workstream-control"),
                ("PHONE.5", "phone5-persistent-worker-readiness"),
                ("PHONE.6", "phone6-realtime-engineering-control"),
                ("PHONE.7", "phone7-mission-control-integration"),
                ("Mission Control V1", "mission-control-v1"),
                ("Mission Control V2", "mission-control-v2"),
            )
        )
        + (
            {
                "title": "Mission Control V2.1 Phone Acceptance Rehearsal",
                "objective": (
                    "Run a bounded read-only worker rehearsal that reports the deployed "
                    "Mission Control release and repository HEAD without modifying files, "
                    "committing, pushing, merging, or deploying."
                ),
                "status": "ready",
                "approved": True,
                "requested_code_changes": False,
                "branch": "mission-control-v2.1",
                "authority": [
                    "Read repository identity and report structured validation only."
                ],
                "constraints": [
                    "Do not modify repository files or index state.",
                    "Do not commit, push, merge, deploy, or access production.",
                    "Begin only after an authenticated owner explicitly taps Start.",
                ],
                "dependencies": ["Mission Control V2"],
                "validation": [
                    "Report git branch, HEAD, and clean status through bounded execution.",
                    "Confirm the result reaches Mission Control and returns to truthful idle state.",
                ],
                "deliverables": ["Structured, durable read-only rehearsal result."],
                "evidence": [
                    "Owner-visible timeline from explicit Start through durable result."
                ],
            },
        ),
    },
)


async def _add_milestone(
    session: AsyncSession,
    *,
    company_id: UUID,
    roadmap: EngineeringRoadmap,
    workstream: str,
    position: int,
    definition: Mapping[str, Any],
    now: datetime,
) -> None:
    status = definition["status"]
    evidence = definition["evidence"]
    milestone = EngineeringMilestone(
        company_id=company_id,
        roadmap_id=roadmap.id,
        position=position,
        title=definition["title"],
        objective=definition["objective"],
        owning_workstream=workstream,
        owning_branch=definition["branch"],
        authority=list(definition["authority"]),
        constraints=list(definition["constraints"]),
        dependencies=list(definition["dependencies"]),
        validation=list(definition["validation"]),
        deliverables=list(definition["deliverables"]),
        stop_conditions=STANDARD_STOP,
        expected_completion_evidence=list(evidence),
        status=status,
        definition_approved=definition["approved"],
        requested_code_changes=definition.get("requested_code_changes", True),
        externally_adoptable=definition.get("externally_adoptable", False),
        external_evidence=evidence[0] if status == "externally_running" else None,
        completed_at=now if status == "completed" else None,
        reviewed_at=now if status == "completed" else None,
        created_at=now,
        updated_at=now,
    )
    session.add(milestone)
    await session.flush()
    session.add(
        EngineeringMilestoneEvent(
            company_id=company_id,
            roadmap_id=roadmap.id,
            milestone_id=milestone.id,
            event_type="roadmap_initialized",
            prior_status=None,
            new_status=status,
            actor_user_id=None,
            reason="Repository and Preview truth reconciliation",
            occurred_at=now,
        )
    )


async def initialize(company_code: str = "ACP") -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    async with AsyncSessionFactory() as session, session.begin():
        company = await session.scalar(
            select(Company).where(Company.code == company_code)
        )
        if company is None:
            raise RuntimeError(f"Company {company_code!r} does not exist.")
        existing = {
            item.title: item
            for item in (
                await session.scalars(
                    select(EngineeringRoadmap).where(
                        EngineeringRoadmap.company_id == company.id
                    )
                )
            ).all()
        }
        created_roadmaps = 0
        created_milestones = 0
        for definition in ROADMAPS:
            current = existing.get(definition["title"])
            if current is not None:
                if current.title == "Customer Migration":
                    historical_phase = await session.scalar(
                        select(EngineeringMilestone).where(
                            EngineeringMilestone.company_id == company.id,
                            EngineeringMilestone.roadmap_id == current.id,
                            EngineeringMilestone.title
                            == "Operational Migration Phase 2 — Estimates, Invoices, and Payments",
                            EngineeringMilestone.command_id.is_(None),
                        )
                    )
                    if (
                        historical_phase is not None
                        and historical_phase.status == "externally_running"
                    ):
                        historical_phase.status = "completed"
                        historical_phase.external_evidence = (
                            "Historical Phase 2 completion reconciled from committed "
                            "workstream evidence at 1307b904 and 51f6d059; Mission "
                            "Control did not dispatch this work."
                        )
                        historical_phase.completed_at = now
                        historical_phase.reviewed_at = now
                        historical_phase.version += 1
                        historical_phase.updated_at = now
                if current.title == "Business Economics":
                    legacy_phase4 = await session.scalar(
                        select(EngineeringMilestone).where(
                            EngineeringMilestone.company_id == company.id,
                            EngineeringMilestone.roadmap_id == current.id,
                            EngineeringMilestone.title
                            == "Phase 4 Accounting Integration and Financial Close",
                        )
                    )
                    if legacy_phase4 is not None:
                        legacy_phase4.title = (
                            "Phase 4 — Accounting Integration and Financial Close"
                        )
                        legacy_phase4.version += 1
                        legacy_phase4.updated_at = now
                if current.title in {
                    "Customer Migration",
                    "Business Economics",
                    "Mission Control",
                    "Beacon",
                }:
                    dispatched = await session.scalar(
                        select(EngineeringMilestone.id).where(
                            EngineeringMilestone.company_id == company.id,
                            EngineeringMilestone.roadmap_id == current.id,
                            EngineeringMilestone.command_id.is_not(None),
                        )
                    )
                    if dispatched is None and (
                        current.expected_branch != definition["branch"]
                        or current.expected_head != definition["head"]
                    ):
                        current.expected_branch = definition["branch"]
                        current.expected_head = definition["head"]
                        current.version += 1
                        current.updated_at = now
                if current.title == "Beacon":
                    bea6 = await session.scalar(
                        select(EngineeringMilestone).where(
                            EngineeringMilestone.company_id == company.id,
                            EngineeringMilestone.roadmap_id == current.id,
                            EngineeringMilestone.title
                            == "BEA.6 Economics Signal Definitions",
                            EngineeringMilestone.command_id.is_(None),
                        )
                    )
                    if bea6 is not None and bea6.owning_branch != definition["branch"]:
                        bea6.owning_branch = definition["branch"]
                        bea6.version += 1
                        bea6.updated_at = now
                existing_titles = set(
                    (
                        await session.scalars(
                            select(EngineeringMilestone.title).where(
                                EngineeringMilestone.company_id == company.id,
                                EngineeringMilestone.roadmap_id == current.id,
                            )
                        )
                    ).all()
                )
                next_position = (
                    await session.scalar(
                        select(func.max(EngineeringMilestone.position)).where(
                            EngineeringMilestone.company_id == company.id,
                            EngineeringMilestone.roadmap_id == current.id,
                        )
                    )
                    or 0
                ) + 1
                added = 0
                for milestone_definition in definition["milestones"]:
                    if milestone_definition["title"] in existing_titles:
                        continue
                    await _add_milestone(
                        session,
                        company_id=company.id,
                        roadmap=current,
                        workstream=definition["title"],
                        position=next_position,
                        definition=milestone_definition,
                        now=now,
                    )
                    existing_titles.add(milestone_definition["title"])
                    next_position += 1
                    added += 1
                if added:
                    current.version += 1
                    current.updated_at = now
                    created_milestones += added
                continuation = {
                    "Customer Migration": (
                        ("Multi-Property Customer Expansion", [], "draft", True),
                        (
                            "Historical Notes Migration",
                            ["Multi-Property Customer Expansion"],
                            "draft",
                            False,
                        ),
                        (
                            "Attachment Migration",
                            ["Historical Notes Migration"],
                            "draft",
                            False,
                        ),
                        (
                            "Remaining Customer/Location Owner Disposition",
                            ["Attachment Migration"],
                            "draft",
                            False,
                        ),
                        (
                            "Complete Historical Job Boundary",
                            ["Remaining Customer/Location Owner Disposition"],
                            "blocked",
                            False,
                        ),
                    ),
                    "Business Economics": (
                        (
                            "Phase 4 — Accounting Integration and Financial Close",
                            [
                                "Phase 3 Allocation Integrity and Accounting Period Control"
                            ],
                            "planned",
                            True,
                        ),
                        (
                            "Phase 5 — Accounting Operationalization",
                            ["Phase 4 — Accounting Integration and Financial Close"],
                            "draft",
                            False,
                        ),
                        (
                            "General Ledger Reconciliation and Export Readiness",
                            ["Phase 5 — Accounting Operationalization"],
                            "draft",
                            False,
                        ),
                        (
                            "Period Audit and Projection Publication",
                            ["General Ledger Reconciliation and Export Readiness"],
                            "draft",
                            False,
                        ),
                        (
                            "Financial Integrity Gate for Beacon",
                            ["Period Audit and Projection Publication"],
                            "draft",
                            False,
                        ),
                    ),
                }.get(current.title)
                if continuation is not None:
                    from .external_adoption import ExternalMilestoneAdoption

                    continuation_titles = [item[0] for item in continuation]
                    base_position = (
                        await session.scalar(
                            select(func.max(EngineeringMilestone.position)).where(
                                EngineeringMilestone.roadmap_id == current.id,
                                EngineeringMilestone.title.not_in(continuation_titles),
                            )
                        )
                        or 0
                    ) + 1
                    continuation_items = []
                    for definition_item in continuation:
                        title = definition_item[0]
                        item = await session.scalar(
                            select(EngineeringMilestone).where(
                                EngineeringMilestone.company_id == company.id,
                                EngineeringMilestone.roadmap_id == current.id,
                                EngineeringMilestone.title == title,
                            )
                        )
                        assert item is not None
                        adoption = await session.scalar(
                            select(ExternalMilestoneAdoption.id).where(
                                ExternalMilestoneAdoption.company_id == company.id,
                                ExternalMilestoneAdoption.milestone_id == item.id,
                            )
                        )
                        continuation_items.append((item, definition_item, adoption))
                    needs_reorder = any(
                        item.position != base_position + offset
                        for offset, (item, _, _) in enumerate(continuation_items)
                    )
                    if needs_reorder:
                        temporary = base_position + len(continuation_items) + 100
                        for offset, (item, _, _) in enumerate(continuation_items):
                            item.position = temporary + offset
                        await session.flush()
                    for offset, (item, definition_item, adoption_id) in enumerate(
                        continuation_items
                    ):
                        _, dependencies, status, adoptable = definition_item
                        changed = (
                            item.position != base_position + offset
                            or item.dependencies != dependencies
                            or item.status != status
                            or item.externally_adoptable != adoptable
                        )
                        if changed and item.command_id is None and adoption_id is None:
                            item.position = base_position + offset
                            item.dependencies = dependencies
                            item.status = status
                            item.externally_adoptable = adoptable
                            item.version += 1
                            item.updated_at = now
                    superseded_titles = {
                        "Customer Migration": {
                            "Notes and Attachments Migration",
                            "Owner Disposition Resolution",
                            "Cutover Reconciliation",
                        },
                        "Business Economics": {
                            "Financial Integrity Readiness Gate for Beacon",
                            "Profitability Intelligence Projections",
                            "Accounting Integration",
                            "Financial Close",
                            "General Ledger Reconciliation",
                            "Projection Publication",
                        },
                    }[current.title]
                    superseded = tuple(
                        (
                            await session.scalars(
                                select(EngineeringMilestone).where(
                                    EngineeringMilestone.company_id == company.id,
                                    EngineeringMilestone.roadmap_id == current.id,
                                    EngineeringMilestone.title.in_(superseded_titles),
                                    EngineeringMilestone.command_id.is_(None),
                                    EngineeringMilestone.status.in_(
                                        {"draft", "planned"}
                                    ),
                                )
                            )
                        ).all()
                    )
                    for item in superseded:
                        item.status = "archived"
                        item.external_evidence = (
                            "Superseded by the approved V2.3 continuation chain."
                        )
                        item.version += 1
                        item.updated_at = now
                continue
            roadmap = EngineeringRoadmap(
                company_id=company.id,
                title=definition["title"],
                repository_key="acp-enterprise",
                expected_branch=definition["branch"],
                expected_head=definition["head"],
                status="active",
                created_at=now,
                updated_at=now,
            )
            session.add(roadmap)
            await session.flush()
            created_roadmaps += 1
            for position, milestone_definition in enumerate(
                definition["milestones"], start=1
            ):
                await _add_milestone(
                    session,
                    company_id=company.id,
                    roadmap=roadmap,
                    workstream=definition["title"],
                    position=position,
                    definition=milestone_definition,
                    now=now,
                )
                created_milestones += 1
        return created_roadmaps, created_milestones


if __name__ == "__main__":
    roadmaps, milestones = asyncio.run(initialize())
    print(f"initialized_roadmaps={roadmaps} initialized_milestones={milestones}")
