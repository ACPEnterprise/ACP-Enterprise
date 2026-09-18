"""Read-only Price Book lineage readiness for converted Jobs."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.estimates.models import (
    EstimateCommercialSnapshotReference,
    EstimateJobConversion,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.price_book.models import PriceBookCommercialSnapshot

CONTRACT_VERSION: Final = "economics.pricebook-feedback-readiness.v1"
MAX_SOURCE_ROWS: Final = 10_000


class PriceBookFeedbackReadinessService:
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
        query = (
            select(
                EstimateJobConversion,
                EstimateCommercialSnapshotReference,
                PriceBookCommercialSnapshot,
            )
            .outerjoin(
                EstimateCommercialSnapshotReference,
                (
                    EstimateCommercialSnapshotReference.company_id
                    == EstimateJobConversion.company_id
                )
                & (
                    EstimateCommercialSnapshotReference.revision_id
                    == EstimateJobConversion.estimate_revision_id
                ),
            )
            .outerjoin(
                PriceBookCommercialSnapshot,
                (
                    PriceBookCommercialSnapshot.company_id
                    == EstimateCommercialSnapshotReference.company_id
                )
                & (
                    PriceBookCommercialSnapshot.id
                    == EstimateCommercialSnapshotReference.snapshot_id
                ),
            )
            .where(
                EstimateJobConversion.company_id == context.company.id,
                EstimateJobConversion.branch_id.in_(context.authorized_branch_ids),
                EstimateJobConversion.converted_at >= start_at,
                EstimateJobConversion.converted_at <= end_at,
            )
            .order_by(EstimateJobConversion.converted_at, EstimateJobConversion.id)
            .limit(MAX_SOURCE_ROWS)
        )
        if context.active_branch is not None:
            query = query.where(
                EstimateJobConversion.branch_id == context.active_branch.id
            )
        return project_pricebook_feedback(
            rows=tuple((await session.execute(query)).all()),
            period_start=period_start,
            period_end=period_end,
        )


def project_pricebook_feedback(
    *, rows: tuple[Any, ...], period_start: date, period_end: date
) -> dict[str, object]:
    by_job: dict[str, dict[str, object]] = {}
    seen_snapshots: dict[str, set[str]] = defaultdict(set)
    conflicts = 0
    for conversion, reference, snapshot in rows:
        job_id = str(conversion.job_id)
        job = by_job.setdefault(
            job_id,
            {
                "job_id": job_id,
                "branch_id": str(conversion.branch_id),
                "estimate_id": str(conversion.estimate_id),
                "estimate_revision_id": str(conversion.estimate_revision_id),
                "snapshot_count": 0,
                "configured_selling_value": None,
                "currency": None,
                "snapshot_references": [],
                "readiness": "MAPPING_MISSING",
                "exact_blocker": "estimate_revision_has_no_commercial_snapshot_reference",
            },
        )
        if reference is None or snapshot is None:
            continue
        if reference.snapshot_digest != snapshot.digest:
            job["readiness"] = "CONFLICTING"
            job["exact_blocker"] = "commercial_snapshot_digest_mismatch"
            conflicts += 1
            continue
        snapshot_id = str(snapshot.id)
        if snapshot_id in seen_snapshots[job_id]:
            continue
        seen_snapshots[job_id].add(snapshot_id)
        currencies = {str(job["currency"]), snapshot.currency.upper()} - {"None"}
        if len(currencies) > 1:
            job["readiness"] = "CONFLICTING"
            job["exact_blocker"] = "multiple_snapshot_currencies"
            conflicts += 1
            continue
        job["currency"] = snapshot.currency.upper()
        snapshot_count = job["snapshot_count"]
        if not isinstance(snapshot_count, int):
            raise TypeError("snapshot count projection is malformed")
        job["snapshot_count"] = snapshot_count + 1
        prior = job["configured_selling_value"]
        job["configured_selling_value"] = str(
            snapshot.extended_amount
            + (Decimal(str(prior)) if prior is not None else Decimal(0))
        )
        snapshot_references = job["snapshot_references"]
        if not isinstance(snapshot_references, list):
            raise TypeError("snapshot reference projection is malformed")
        snapshot_references.append(
            {
                "snapshot_id": snapshot_id,
                "service_item_id": str(snapshot.service_item_id),
                "price_version_id": str(snapshot.price_version_id),
                "snapshot_digest": snapshot.digest,
                "effective_at": snapshot.effective_at.isoformat(),
            }
        )
        if job["readiness"] != "CONFLICTING":
            job["readiness"] = "COST_EVIDENCE_REQUIRED"
            job["exact_blocker"] = (
                "complete_measured_direct_cost_and_contribution_required_for_review"
            )
    jobs = sorted(by_job.values(), key=lambda item: str(item["job_id"]))
    payload: dict[str, object] = {
        "contract_version": CONTRACT_VERSION,
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "converted_job_count": len(jobs),
        "mapped_job_count": sum(bool(item["snapshot_count"]) for item in jobs),
        "mapping_missing_job_count": sum(
            not bool(item["snapshot_count"]) for item in jobs
        ),
        "conflicting_job_count": conflicts,
        "review_ready_job_count": 0,
        "jobs": jobs,
        "limitations": (
            "Commercial snapshot price is configured/presented evidence, not invoiced or earned revenue.",
            "Price Book expected cost is never substituted for measured direct cost.",
            "No review candidate activates or changes a price.",
        ),
        "mutation_authority": "none",
    }
    payload["evidence_digest"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    return payload
