"""Append-only authority for immutable Economics profitability result history."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import exists, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EconomicsPolicyPermission

from .models import (
    EconomicsProfitabilityResultRecord,
    EconomicsProfitabilityResultSupersessionRecord,
)


class ResultSupersessionReason(StrEnum):
    SOURCE_CORRECTION = "source_correction"
    POLICY_RECOMPUTATION = "policy_recomputation"
    COMPUTATION_VERSION = "computation_version"
    ATTRIBUTION_CORRECTION = "attribution_correction"


class EconomicsResultHistoryError(ValueError):
    """Raised when immutable result history cannot accept a command."""


@dataclass(frozen=True, slots=True)
class EconomicsResultLineage:
    current: EconomicsProfitabilityResultRecord
    results: tuple[EconomicsProfitabilityResultRecord, ...]
    supersessions: tuple[EconomicsProfitabilityResultSupersessionRecord, ...]


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class EconomicsResultHistoryService:
    async def supersede(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        predecessor_result_id: UUID,
        successor_result_id: UUID,
        reason: ResultSupersessionReason,
    ) -> EconomicsProfitabilityResultSupersessionRecord:
        if not context.has_permission(EconomicsPolicyPermission.MEASUREMENT_EXECUTE):
            raise EconomicsResultHistoryError(
                "Economics recomputation permission denied"
            )
        lock_key = f"eco-result-lineage:{context.company.id}:{predecessor_result_id}"
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": lock_key},
        )
        records = (
            await session.scalars(
                select(EconomicsProfitabilityResultRecord).where(
                    EconomicsProfitabilityResultRecord.company_id == context.company.id,
                    EconomicsProfitabilityResultRecord.id.in_(
                        (predecessor_result_id, successor_result_id)
                    ),
                )
            )
        ).all()
        by_id = {item.id: item for item in records}
        predecessor = by_id.get(predecessor_result_id)
        successor = by_id.get(successor_result_id)
        if predecessor is None or successor is None:
            raise EconomicsResultHistoryError("result lineage is not available")
        if context.active_branch is not None and (
            predecessor.branch_id != context.active_branch.id
            or successor.branch_id != context.active_branch.id
        ):
            raise EconomicsResultHistoryError("cross-Branch result supersession")
        lineage = (
            predecessor.subject_id,
            predecessor.subject_kind,
            predecessor.scope,
            predecessor.basis,
            predecessor.period_start,
            predecessor.period_end,
            predecessor.currency,
        )
        if lineage != (
            successor.subject_id,
            successor.subject_kind,
            successor.scope,
            successor.basis,
            successor.period_start,
            successor.period_end,
            successor.currency,
        ):
            raise EconomicsResultHistoryError(
                "successor belongs to a different lineage"
            )
        canonical = {
            "company_id": str(context.company.id),
            "predecessor_result_id": str(predecessor.id),
            "predecessor_digest": predecessor.result_digest,
            "successor_result_id": str(successor.id),
            "successor_digest": successor.result_digest,
            "reason": reason.value,
        }
        digest = _digest(canonical)
        existing = await session.scalar(
            select(EconomicsProfitabilityResultSupersessionRecord).where(
                EconomicsProfitabilityResultSupersessionRecord.company_id
                == context.company.id,
                EconomicsProfitabilityResultSupersessionRecord.predecessor_result_id
                == predecessor.id,
            )
        )
        if existing is not None:
            if (
                existing.successor_result_id == successor.id
                and existing.supersession_digest == digest
            ):
                return existing
            raise EconomicsResultHistoryError(
                "profitability lineage already has a successor"
            )
        edge = EconomicsProfitabilityResultSupersessionRecord(
            company_id=context.company.id,
            predecessor_result_id=predecessor.id,
            successor_result_id=successor.id,
            subject_id=predecessor.subject_id,
            subject_kind=predecessor.subject_kind,
            scope=predecessor.scope,
            basis=predecessor.basis,
            period_start=predecessor.period_start,
            period_end=predecessor.period_end,
            currency=predecessor.currency,
            predecessor_digest=predecessor.result_digest,
            successor_digest=successor.result_digest,
            predecessor_package_digest=predecessor.package_digest,
            successor_package_digest=successor.package_digest,
            predecessor_computation_digest=predecessor.computation_digest,
            successor_computation_digest=successor.computation_digest,
            reason=reason.value,
            supersession_digest=digest,
            created_by_user_id=context.user.id,
        )
        session.add(edge)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise EconomicsResultHistoryError(
                "concurrent profitability supersession conflict"
            ) from exc
        await session.commit()
        return edge

    async def current(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        subject_id: UUID,
        period_start: object,
        period_end: object,
    ) -> EconomicsProfitabilityResultRecord:
        superseded = exists().where(
            EconomicsProfitabilityResultSupersessionRecord.predecessor_result_id
            == EconomicsProfitabilityResultRecord.id
        )
        query = select(EconomicsProfitabilityResultRecord).where(
            EconomicsProfitabilityResultRecord.company_id == context.company.id,
            EconomicsProfitabilityResultRecord.subject_id == subject_id,
            EconomicsProfitabilityResultRecord.period_start == period_start,
            EconomicsProfitabilityResultRecord.period_end == period_end,
            ~superseded,
        )
        if context.active_branch is not None:
            query = query.where(
                EconomicsProfitabilityResultRecord.branch_id == context.active_branch.id
            )
        values = tuple((await session.scalars(query)).all())
        if len(values) != 1:
            raise EconomicsResultHistoryError(
                "profitability lineage has no unique current result"
            )
        return values[0]

    async def lineage(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        result_id: UUID,
    ) -> EconomicsResultLineage:
        seed = await session.scalar(
            select(EconomicsProfitabilityResultRecord).where(
                EconomicsProfitabilityResultRecord.company_id == context.company.id,
                EconomicsProfitabilityResultRecord.id == result_id,
            )
        )
        if seed is None:
            raise EconomicsResultHistoryError("profitability result not found")
        if (
            context.active_branch is not None
            and seed.branch_id != context.active_branch.id
        ):
            raise EconomicsResultHistoryError("profitability result not found")
        edges = tuple(
            (
                await session.scalars(
                    select(EconomicsProfitabilityResultSupersessionRecord)
                    .where(
                        EconomicsProfitabilityResultSupersessionRecord.company_id
                        == context.company.id,
                        EconomicsProfitabilityResultSupersessionRecord.subject_id
                        == seed.subject_id,
                        EconomicsProfitabilityResultSupersessionRecord.subject_kind
                        == seed.subject_kind,
                        EconomicsProfitabilityResultSupersessionRecord.scope
                        == seed.scope,
                        EconomicsProfitabilityResultSupersessionRecord.basis
                        == seed.basis,
                        EconomicsProfitabilityResultSupersessionRecord.period_start
                        == seed.period_start,
                        EconomicsProfitabilityResultSupersessionRecord.period_end
                        == seed.period_end,
                        EconomicsProfitabilityResultSupersessionRecord.currency
                        == seed.currency,
                    )
                    .order_by(EconomicsProfitabilityResultSupersessionRecord.created_at)
                )
            ).all()
        )
        ids = {seed.id}
        for edge in edges:
            ids.update((edge.predecessor_result_id, edge.successor_result_id))
        results = tuple(
            (
                await session.scalars(
                    select(EconomicsProfitabilityResultRecord)
                    .where(EconomicsProfitabilityResultRecord.id.in_(ids))
                    .order_by(EconomicsProfitabilityResultRecord.created_at)
                )
            ).all()
        )
        predecessors = {edge.predecessor_result_id for edge in edges}
        current = [item for item in results if item.id not in predecessors]
        if len(current) != 1:
            raise EconomicsResultHistoryError(
                "profitability lineage has no unique current result"
            )
        return EconomicsResultLineage(current[0], results, edges)
