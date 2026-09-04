"""Singleton operational runner for the reviewed headless factory queue."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_control.models import EngineeringCommand
from app.engineering_execution.models import EngineeringExecution
from app.platform.permissions.authorization import AuthorizationContext
from app.worker_control.contracts import AuthenticatedWorkerContext

from .application import HeadlessApplicationService
from .approved_queue import ApprovedWork, load_approved_factory_queue
from .headless import HeadlessProposal

LOCK_KEY = "ACP.72H.HEADLESS.RUNNER.V1"
TERMINAL_SUCCESS = {"completed"}
ACTIVE = {"execution_not_connected", "queued", "starting", "running"}


class HeadlessRunner:
    def __init__(self, application: HeadlessApplicationService | None = None) -> None:
        self.application = application or HeadlessApplicationService()

    async def run_once(
        self,
        session: AsyncSession,
        *,
        admin_context: AuthorizationContext,
        worker_context: AuthenticatedWorkerContext,
        expected_authority_sha: str,
        now: datetime,
    ) -> tuple[str, ...]:
        """Reconcile stale leases and fill free capacities once, idempotently."""

        acquired = bool(
            await session.scalar(
                text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"),
                {"key": LOCK_KEY},
            )
        )
        if not acquired:
            return ()
        try:
            await session.commit()
            await self.application.reconcile_stale_executions(
                session, worker_context=worker_context, now=now
            )
            queue = load_approved_factory_queue()
            if queue.authoritative_repository_sha != expected_authority_sha:
                return ()
            rows = (
                await session.execute(
                    select(EngineeringCommand.idempotency_key, EngineeringExecution.state)
                    .join(
                        EngineeringExecution,
                        EngineeringExecution.command_id == EngineeringCommand.id,
                    )
                    .where(
                        EngineeringCommand.company_id == admin_context.company.id,
                        EngineeringCommand.idempotency_key.like(f"{queue.queue_id}:%"),
                    )
                )
            ).all()
            await session.rollback()
            states = self._states(queue.queue_id, rows)
            completed = frozenset(
                milestone_id
                for milestone_id, state in states.items()
                if state in TERMINAL_SUCCESS
            )
            occupied = {
                item.capacity_identity
                for item in queue.items
                if states.get(item.milestone_id) in ACTIVE
            }
            applied: list[str] = []
            for work in queue.items:
                if work.capacity_identity in occupied or work.milestone_id in states:
                    continue
                if not self._eligible(work, queue.items, completed):
                    continue
                await self.application.apply_proposal(
                    session,
                    manage_context=admin_context,
                    approve_context=admin_context,
                    execution_context=admin_context,
                    proposal=HeadlessProposal(
                        kind="refill" if work.dependencies else "activate",
                        milestone_id=work.milestone_id,
                        capacity_identity=work.capacity_identity,
                        reason="reviewed 72-hour queue runner",
                    ),
                    expected_authority_sha=expected_authority_sha,
                    now=now,
                    completed_milestone_ids=completed,
                )
                occupied.add(work.capacity_identity)
                applied.append(work.milestone_id)
            return tuple(applied)
        finally:
            await session.scalar(
                text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"),
                {"key": LOCK_KEY},
            )
            await session.commit()

    @staticmethod
    def _states(queue_id: str, rows: Iterable[Any]) -> dict[str, str]:
        result: dict[str, str] = {}
        prefix = f"{queue_id}:"
        for key, state in rows:
            if not key.startswith(prefix):
                continue
            milestone_id = key[len(prefix) :].rsplit(":", 1)[0]
            value = getattr(state, "value", state)
            result[milestone_id] = str(value)
        return result

    @staticmethod
    def _eligible(
        work: ApprovedWork,
        items: tuple[ApprovedWork, ...],
        completed: frozenset[str],
    ) -> bool:
        if (
            work.execution_mode != "repository_only"
            or work.hard_boundary_operations
            or work.queue_state not in {"READY", "BLOCKED_DEPENDENCY"}
        ):
            return False
        by_id = {item.milestone_id: item for item in items}
        return all(
            by_id[value].queue_state == "AUTHORITATIVE" or value in completed
            for value in work.dependencies
        )


__all__ = ["HeadlessRunner"]
