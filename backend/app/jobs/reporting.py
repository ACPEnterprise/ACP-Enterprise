from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.estimates.models import EstimateJobConversion, EstimateRevision
from app.jobs.errors import JobQueryValidationError
from app.jobs.models import Job
from app.platform.permissions.authorization import AuthorizationContext


def _bucket_start(value: date, granularity: str) -> date:
    if granularity == "day":
        return value
    if granularity == "week":
        return value - timedelta(days=value.weekday())
    if granularity == "month":
        return value.replace(day=1)
    return value.replace(month=1, day=1)


def _next_bucket(value: date, granularity: str) -> date:
    if granularity == "day":
        return value + timedelta(days=1)
    if granularity == "week":
        return value + timedelta(days=7)
    if granularity == "month":
        return date(value.year + (value.month == 12), 1 if value.month == 12 else value.month + 1, 1)
    return date(value.year + 1, 1, 1)


class JobReportingService:
    async def completed_trend(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        period_start: date,
        period_end: date,
        granularity: str,
        branch_id: UUID | None = None,
    ) -> dict[str, object]:
        if period_end < period_start or (period_end - period_start).days > 2192:
            raise JobQueryValidationError("Job reporting period is invalid.")
        if granularity not in {"day", "week", "month", "year"}:
            raise JobQueryValidationError("Job reporting granularity is invalid.")
        if branch_id is not None and not context.can_access_branch(branch_id):
            from app.jobs.errors import JobNotFoundError

            raise JobNotFoundError(branch_id)
        branches = context.authorized_branch_ids if branch_id is None else frozenset({branch_id})
        local_zone = ZoneInfo(context.company.timezone)
        range_start = datetime.combine(period_start, time.min, local_zone).astimezone(timezone.utc)
        range_end = datetime.combine(period_end + timedelta(days=1), time.min, local_zone).astimezone(timezone.utc)
        rows = tuple(
            (
                await session.execute(
                    select(
                        Job.completed_at,
                        EstimateRevision.total_amount,
                        EstimateRevision.currency,
                    )
                    .outerjoin(
                        EstimateJobConversion,
                        and_(
                            EstimateJobConversion.company_id == Job.company_id,
                            EstimateJobConversion.job_id == Job.id,
                        ),
                    )
                    .outerjoin(
                        EstimateRevision,
                        and_(
                            EstimateRevision.company_id == EstimateJobConversion.company_id,
                            EstimateRevision.id == EstimateJobConversion.estimate_revision_id,
                        ),
                    )
                    .where(
                        Job.company_id == context.company.id,
                        Job.branch_id.in_(branches),
                        Job.status == "completed",
                        Job.completed_at >= range_start,
                        Job.completed_at < range_end,
                    )
                )
            ).all()
        )
        grouped: dict[date, list[tuple[Decimal | None, str | None]]] = defaultdict(list)
        all_currencies: set[str] = set()
        for completed_at, amount, currency in rows:
            local_date = completed_at.astimezone(local_zone).date()
            grouped[_bucket_start(local_date, granularity)].append((amount, currency))
            if currency is not None:
                all_currencies.add(currency)
        currency = next(iter(all_currencies)) if len(all_currencies) == 1 else None
        points: list[dict[str, object]] = []
        cursor = _bucket_start(period_start, granularity)
        while cursor <= period_end:
            next_cursor = _next_bucket(cursor, granularity)
            visible_start = max(cursor, period_start)
            visible_end_exclusive = min(next_cursor, period_end + timedelta(days=1))
            bucket_rows = grouped.get(cursor, [])
            missing_count = sum(1 for amount, _ in bucket_rows if amount is None)
            currencies = {row_currency for _, row_currency in bucket_rows if row_currency}
            known_value = sum(
                (amount for amount, _ in bucket_rows if amount is not None), Decimal("0.00")
            )
            if len(currencies) > 1:
                evidence_state = "CONFLICTING_CURRENCIES"
                produced_value = None
            elif missing_count:
                evidence_state = "INCOMPLETE_SOLD_SNAPSHOT"
                produced_value = None
            elif not bucket_rows:
                evidence_state = "MEASURED_ZERO"
                produced_value = Decimal("0.00")
            else:
                evidence_state = "AVAILABLE"
                produced_value = known_value
            start_at = datetime.combine(visible_start, time.min, local_zone).astimezone(timezone.utc)
            end_at = datetime.combine(visible_end_exclusive, time.min, local_zone).astimezone(timezone.utc)
            label = (
                visible_start.strftime("%b %-d")
                if granularity in {"day", "week"}
                else visible_start.strftime("%b %Y")
                if granularity == "month"
                else str(visible_start.year)
            )
            points.append(
                {
                    "label": label,
                    "period_start": visible_start,
                    "period_end": visible_end_exclusive - timedelta(days=1),
                    "completed_start_at": start_at,
                    "completed_end_at": end_at,
                    "job_count": len(bucket_rows),
                    "produced_value": produced_value,
                    "known_produced_value": known_value,
                    "missing_value_count": missing_count,
                    "evidence_state": evidence_state,
                }
            )
            cursor = next_cursor
        return {
            "generated_at": datetime.now(timezone.utc),
            "timezone": context.company.timezone,
            "branch_id": branch_id,
            "currency": currency,
            "granularity": granularity,
            "period_start": period_start,
            "period_end": period_end,
            "points": tuple(points),
        }


job_reporting_service = JobReportingService()
