"""Read-only conversion evidence from issued Estimates and explicit decisions."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.estimates.models import (
    Estimate,
    EstimateCustomerDecision,
    EstimateJobConversion,
    EstimateRevision,
)
from app.platform.permissions.authorization import AuthorizationContext

CONTRACT_VERSION: Final = "economics.conversion-readiness.v1"
MAX_SOURCE_ROWS: Final = 5000


class ConversionReadinessService:
    async def project(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        period_start: date,
        period_end: date,
    ) -> dict[str, object]:
        if period_end < period_start:
            raise ValueError("period end cannot precede period start")
        start_at = datetime.combine(period_start, time.min, tzinfo=timezone.utc)
        end_at = datetime.combine(period_end, time.max, tzinfo=timezone.utc)
        estimates_query = (
            select(Estimate, EstimateRevision)
            .join(
                EstimateRevision,
                (EstimateRevision.company_id == Estimate.company_id)
                & (EstimateRevision.id == Estimate.current_revision_id),
            )
            .where(
                Estimate.company_id == context.company.id,
                Estimate.branch_id.in_(context.authorized_branch_ids),
                EstimateRevision.issued_at >= start_at,
                EstimateRevision.issued_at <= end_at,
            )
            .order_by(EstimateRevision.issued_at, Estimate.id)
            .limit(MAX_SOURCE_ROWS)
        )
        if context.active_branch is not None:
            estimates_query = estimates_query.where(
                Estimate.branch_id == context.active_branch.id
            )
        rows = tuple((await session.execute(estimates_query)).all())
        estimate_ids = {estimate.id for estimate, _ in rows}
        decisions: tuple[EstimateCustomerDecision, ...] = ()
        conversions: tuple[EstimateJobConversion, ...] = ()
        if estimate_ids:
            decisions = tuple(
                (
                    await session.scalars(
                        select(EstimateCustomerDecision)
                        .where(
                            EstimateCustomerDecision.company_id
                            == context.company.id,
                            EstimateCustomerDecision.estimate_id.in_(estimate_ids),
                        )
                        .order_by(
                            EstimateCustomerDecision.occurred_at,
                            EstimateCustomerDecision.id,
                        )
                        .limit(MAX_SOURCE_ROWS)
                    )
                ).all()
            )
            conversions = tuple(
                (
                    await session.scalars(
                        select(EstimateJobConversion)
                        .where(
                            EstimateJobConversion.company_id == context.company.id,
                            EstimateJobConversion.estimate_id.in_(estimate_ids),
                        )
                        .limit(MAX_SOURCE_ROWS)
                    )
                ).all()
            )
        return project_conversion_readiness(
            rows=rows,
            decisions=decisions,
            conversions=conversions,
            period_start=period_start,
            period_end=period_end,
        )


def project_conversion_readiness(
    *,
    rows: tuple[Any, ...],
    decisions: tuple[EstimateCustomerDecision, ...],
    conversions: tuple[EstimateJobConversion, ...],
    period_start: date,
    period_end: date,
) -> dict[str, object]:
    decision_by_estimate: dict[object, set[str]] = {}
    for decision in decisions:
        decision_by_estimate.setdefault(decision.estimate_id, set()).add(
            decision.decision
        )
    conversion_by_estimate = {item.estimate_id: item for item in conversions}
    outcomes = []
    accepted = declined = expired = pending = conflicting = 0
    currencies: set[str] = set()
    presented_value = Decimal(0)
    accepted_value = Decimal(0)
    for estimate, revision in rows:
        if revision.issued_at is None:
            raise ValueError("presented Estimate requires issued timestamp")
        explicit = decision_by_estimate.get(estimate.id, set())
        accepted_signal = bool(explicit & {"approved"}) or estimate.acceptance_status in {
            "approved",
            "accepted",
        }
        declined_signal = bool(explicit & {"rejected"}) or estimate.acceptance_status in {
            "rejected",
            "declined",
            "withdrawn",
        }
        if accepted_signal and declined_signal:
            outcome = "CONFLICTING"
            conflicting += 1
        elif accepted_signal:
            outcome = "ACCEPTED"
            accepted += 1
            accepted_value += revision.total_amount
        elif declined_signal:
            outcome = "DECLINED"
            declined += 1
        elif estimate.acceptance_status == "expired" or estimate.status == "expired":
            outcome = "EXPIRED"
            expired += 1
        else:
            outcome = "PENDING"
            pending += 1
        currencies.add(revision.currency.upper())
        presented_value += revision.total_amount
        conversion = conversion_by_estimate.get(estimate.id)
        outcomes.append(
            {
                "estimate_id": str(estimate.id),
                "branch_id": str(estimate.branch_id),
                "customer_id": str(estimate.customer_id),
                "revision_id": str(revision.id),
                "presented_at": revision.issued_at.isoformat(),
                "presented_amount": str(revision.total_amount),
                "currency": revision.currency.upper(),
                "outcome": outcome,
                "job_id": str(conversion.job_id) if conversion else None,
                "evidence": (
                    f"estimate_revision:{revision.id}:{revision.revision_number}",
                    *(f"customer_decision:{item.id}" for item in decisions if item.estimate_id == estimate.id),
                ),
            }
        )
    terminal = accepted + declined + expired
    complete = bool(rows) and not pending and not conflicting and len(currencies) == 1
    payload: dict[str, object] = {
        "contract_version": CONTRACT_VERSION,
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "readiness": (
            "CONFLICTING_EVIDENCE"
            if conflicting or len(currencies) > 1
            else "READY"
            if complete
            else "PARTIAL"
            if rows
            else "SOURCE_MISSING"
        ),
        "presented_count": len(rows),
        "accepted_count": accepted,
        "declined_count": declined,
        "expired_count": expired,
        "pending_count": pending,
        "conflicting_count": conflicting,
        "job_conversion_count": len(conversions),
        "presented_value": str(presented_value) if rows and len(currencies) == 1 else None,
        "accepted_value": str(accepted_value) if rows and len(currencies) == 1 else None,
        "currency": next(iter(currencies)) if len(currencies) == 1 else None,
        "close_rate": str(Decimal(accepted) / Decimal(terminal)) if complete and terminal else None,
        "outcomes": outcomes,
        "limitations": (
            "Only issued Estimate revisions are comparable presented opportunities.",
            "Open outcomes prevent a complete cohort close rate.",
            "Price and outcome association is not a causal claim.",
            "No market-share conclusion is available without external market evidence.",
        ),
        "mutation_authority": "none",
    }
    payload["evidence_digest"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    return payload
