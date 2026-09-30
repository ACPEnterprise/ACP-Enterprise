"""Read-only readiness for attributing authoritative wage cost to Jobs.

Accepted Job-work intervals establish duration and Employee attribution. They do
not, by themselves, establish whether an hourly minute is regular/overtime or
how salaried compensation is allocated. This projection therefore exposes the
smallest exact blocker without disclosing compensation values.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime, time, timezone
from enum import StrEnum
from typing import Final
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.payroll.models import EmployeeCompensationAuthorityVersion
from app.platform.permissions.authorization import AuthorizationContext
from app.timekeeping.models import JobWorkedIntervalRevision

CONTRACT_VERSION: Final = "economics.direct-wage-cost-readiness.v1"
MAX_SOURCE_ROWS: Final = 10_000


class DirectWageCostReadiness(StrEnum):
    READY = "DIRECT_WAGE_COST_READY"
    COMPENSATION_MISSING = "COMPENSATION_MISSING"
    EFFECTIVE_DATE_MISSING = "EFFECTIVE_DATE_MISSING"
    TIME_EVIDENCE_MISSING = "TIME_EVIDENCE_MISSING"
    JOB_ATTRIBUTION_MISSING = "JOB_ATTRIBUTION_MISSING"
    OVERTIME_POLICY_REQUIRED = "OVERTIME_POLICY_REQUIRED"
    OWNER_CERTIFICATION_REQUIRED = "OWNER_CERTIFICATION_REQUIRED"
    SOURCE_MISSING = "SOURCE_MISSING"
    CONFLICTING = "CONFLICTING"


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


class DirectWageCostReadinessService:
    """Evaluate accepted Job intervals against approved compensation authority."""

    async def project(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        period_start: date,
        period_end: date,
    ) -> dict[str, object]:
        if period_end < period_start:
            raise ValueError("period end must not precede period start")
        start_at = datetime.combine(period_start, time.min, tzinfo=timezone.utc)
        end_at = datetime.combine(period_end, time.max, tzinfo=timezone.utc)
        branch_ids = context.authorized_branch_ids
        interval_query = (
            select(JobWorkedIntervalRevision)
            .where(
                JobWorkedIntervalRevision.company_id == context.company.id,
                JobWorkedIntervalRevision.branch_id.in_(branch_ids),
                JobWorkedIntervalRevision.start_at <= end_at,
                JobWorkedIntervalRevision.stop_at >= start_at,
                JobWorkedIntervalRevision.validity == "valid",
                JobWorkedIntervalRevision.confidence == "authoritative",
                JobWorkedIntervalRevision.correction_state != "superseded",
                ~exists().where(
                    JobWorkedIntervalRevision.supersedes_revision_id
                    == JobWorkedIntervalRevision.id
                ),
            )
            .order_by(JobWorkedIntervalRevision.start_at, JobWorkedIntervalRevision.id)
            .limit(MAX_SOURCE_ROWS)
        )
        if context.active_branch is not None:
            interval_query = interval_query.where(
                JobWorkedIntervalRevision.branch_id == context.active_branch.id
            )
        intervals = tuple((await session.scalars(interval_query)).all())
        employee_ids = {item.employee_id for item in intervals}
        authorities: tuple[EmployeeCompensationAuthorityVersion, ...] = ()
        if employee_ids:
            authority_query = (
                select(EmployeeCompensationAuthorityVersion)
                .where(
                    EmployeeCompensationAuthorityVersion.company_id
                    == context.company.id,
                    EmployeeCompensationAuthorityVersion.employee_id.in_(employee_ids),
                    EmployeeCompensationAuthorityVersion.lifecycle == "approved",
                    EmployeeCompensationAuthorityVersion.effective_start <= period_end,
                    (
                        EmployeeCompensationAuthorityVersion.effective_end.is_(None)
                        | (
                            EmployeeCompensationAuthorityVersion.effective_end
                            > period_start
                        )
                    ),
                )
                .order_by(
                    EmployeeCompensationAuthorityVersion.employee_id,
                    EmployeeCompensationAuthorityVersion.effective_start,
                    EmployeeCompensationAuthorityVersion.authority_version,
                )
                .limit(MAX_SOURCE_ROWS)
            )
            authorities = tuple((await session.scalars(authority_query)).all())

        by_employee: dict[UUID, list[EmployeeCompensationAuthorityVersion]] = (
            defaultdict(list)
        )
        for compensation_authority in authorities:
            by_employee[compensation_authority.employee_id].append(
                compensation_authority
            )

        results: list[dict[str, object]] = []
        for interval in intervals:
            work_date = interval.start_at.date()
            employee_authorities = by_employee[interval.employee_id]
            effective = [
                authority
                for authority in employee_authorities
                if authority.effective_start <= work_date
                and (
                    authority.effective_end is None
                    or work_date < authority.effective_end
                )
            ]
            if not employee_authorities:
                state = DirectWageCostReadiness.COMPENSATION_MISSING
                blocker = "approved_effective_dated_compensation_authority_missing"
            elif not effective:
                state = DirectWageCostReadiness.EFFECTIVE_DATE_MISSING
                blocker = "approved_compensation_does_not_cover_work_date"
            elif len(effective) > 1:
                state = DirectWageCostReadiness.CONFLICTING
                blocker = "multiple_approved_compensation_authorities_cover_work_date"
            elif effective[0].compensation_type == "salaried":
                state = DirectWageCostReadiness.OWNER_CERTIFICATION_REQUIRED
                blocker = "approved_salary_to_job_allocation_method_missing"
            else:
                state = DirectWageCostReadiness.OVERTIME_POLICY_REQUIRED
                blocker = (
                    "job_interval_cannot_determine_regular_vs_overtime_without_"
                    "complete_accepted_workweek_allocation"
                )
            resolved_authority = effective[0] if len(effective) == 1 else None
            result = {
                "interval_revision_id": str(interval.id),
                "interval_id": str(interval.interval_id),
                "employee_id": str(interval.employee_id),
                "job_id": str(interval.job_id),
                "branch_id": str(interval.branch_id),
                "work_date": work_date.isoformat(),
                "accepted_worked_seconds": interval.duration_seconds,
                "readiness": state.value,
                "exact_blocker": blocker,
                "direct_wage_cost_minor": None,
                "compensation_authority_id": (
                    str(resolved_authority.id) if resolved_authority else None
                ),
                "compensation_authority_version": (
                    resolved_authority.authority_version
                    if resolved_authority
                    else None
                ),
                "compensation_authority_digest": (
                    resolved_authority.authority_digest
                    if resolved_authority
                    else None
                ),
            }
            result["evidence_digest"] = _digest(result)
            results.append(result)

        counts = Counter(item["readiness"] for item in results)
        payload: dict[str, object] = {
            "contract_version": CONTRACT_VERSION,
            "company_id": str(context.company.id),
            "branch_id": (
                str(context.active_branch.id) if context.active_branch else None
            ),
            "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
            "accepted_job_interval_count": len(intervals),
            "approved_compensation_authority_count": len(authorities),
            "readiness_counts": {
                state.value: counts[state.value] for state in DirectWageCostReadiness
            },
            "employee_job_periods": results,
            "limitations": (
                "Compensation amounts are not exposed by this Economics projection.",
                "Accepted Job-work time is not paid time and is not scheduled time.",
                "Missing wage cost remains missing; it is never converted to zero.",
                "No Payroll calculation, execution, Accounting posting, or employment conclusion occurs.",
            ),
        }
        payload["packet_digest"] = _digest(payload)
        return payload
