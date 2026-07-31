"""Approved ACP Enterprise roadmap catalog and one-time Preview initialization."""

import asyncio
import os
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

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


ROADMAPS: tuple[Mapping[str, Any], ...] = (
    {
        "title": "Customer Migration",
        "branch": "customer-migration-workstream",
        "head": "51f6d059c69c359761eb9aa63d081439a6e3d7d0",
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
        ),
    },
    {
        "title": "Business Economics",
        "branch": "business-economics-foundation",
        "head": "3940d1d076649a2e2f83ff614a5a228fbaa0a8b4",
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
                "title": "Phase 4 Accounting Integration and Financial Close",
                "objective": "Integrate approved accounting boundaries and establish a controlled financial-close workflow on authoritative economic facts.",
                "status": "externally_running",
                "approved": True,
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
                ["Phase 4 Accounting Integration and Financial Close"],
            ),
            draft(
                "Profitability Intelligence Projections",
                "Define bounded profitability projections from authoritative economic facts.",
                "business-economics-foundation",
                ["Financial Integrity Readiness Gate for Beacon"],
            ),
        ),
    },
    {
        "title": "Beacon",
        "branch": "beacon-economics-signals",
        "head": "b843f74dd594fe5ecdb17d97a468cedfc66dac44",
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
        ),
    },
    {
        "title": "Mission Control",
        "branch": "mission-control-v2.1",
        "head": "a7667cb0c4f437388965bff0028d4d59d9c227a2",
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


async def initialize(company_code: str = "ACP") -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    async with AsyncSessionFactory() as session, session.begin():
        company = await session.scalar(
            select(Company).where(Company.code == company_code)
        )
        if company is None:
            raise RuntimeError(f"Company {company_code!r} does not exist.")
        existing = set(
            (
                await session.scalars(
                    select(EngineeringRoadmap.title).where(
                        EngineeringRoadmap.company_id == company.id
                    )
                )
            ).all()
        )
        created_roadmaps = 0
        created_milestones = 0
        for definition in ROADMAPS:
            if definition["title"] in existing:
                continue
            expected_head = definition["head"]
            if definition["title"] == "Mission Control":
                release_head = os.environ.get("ACP_ROADMAP_RELEASE_SHA")
                if release_head:
                    if len(release_head) != 40 or any(
                        character not in "0123456789abcdef"
                        for character in release_head
                    ):
                        raise RuntimeError(
                            "ACP_ROADMAP_RELEASE_SHA must be a full Git SHA."
                        )
                    expected_head = release_head
            roadmap = EngineeringRoadmap(
                company_id=company.id,
                title=definition["title"],
                repository_key="acp-enterprise",
                expected_branch=definition["branch"],
                expected_head=expected_head,
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
                status = milestone_definition["status"]
                evidence = milestone_definition["evidence"]
                milestone = EngineeringMilestone(
                    company_id=company.id,
                    roadmap_id=roadmap.id,
                    position=position,
                    title=milestone_definition["title"],
                    objective=milestone_definition["objective"],
                    owning_workstream=definition["title"],
                    owning_branch=milestone_definition["branch"],
                    authority=list(milestone_definition["authority"]),
                    constraints=list(milestone_definition["constraints"]),
                    dependencies=list(milestone_definition["dependencies"]),
                    validation=list(milestone_definition["validation"]),
                    deliverables=list(milestone_definition["deliverables"]),
                    stop_conditions=STANDARD_STOP,
                    expected_completion_evidence=list(evidence),
                    status=status,
                    definition_approved=milestone_definition["approved"],
                    requested_code_changes=milestone_definition.get(
                        "requested_code_changes", True
                    ),
                    external_evidence=(
                        evidence[0] if status == "externally_running" else None
                    ),
                    completed_at=now if status == "completed" else None,
                    reviewed_at=now if status == "completed" else None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(milestone)
                await session.flush()
                session.add(
                    EngineeringMilestoneEvent(
                        company_id=company.id,
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
                created_milestones += 1
        return created_roadmaps, created_milestones


if __name__ == "__main__":
    roadmaps, milestones = asyncio.run(initialize())
    print(f"initialized_roadmaps={roadmaps} initialized_milestones={milestones}")
