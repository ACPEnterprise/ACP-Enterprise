from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, TypedDict
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.schemas import (
    AnalyticsSummaryResponse,
    CountMetric,
    MetricValue,
    RecentActivityItem,
    RevenueTrendPoint,
    RevenueTrendResponse,
)
from app.core.config import settings
from app.events.models import BusinessEvent


class RevenueTrendDailyValues(TypedDict):
    booked_revenue: Decimal | None
    cash_collected: Decimal | None
    booked_event_count: int
    payment_event_count: int
    excluded_booked_event_count: int
    excluded_payment_event_count: int


class AnalyticsService:
    PAYMENT_RECEIVED = "payment.received"
    ESTIMATE_APPROVED = "estimate.approved"
    CUSTOMER_CREATED = "customer.created"
    APPOINTMENT_BOOKED = "appointment.booked"

    @staticmethod
    def _decimal_from_payload(
        payload: dict[str, Any],
        field_names: tuple[str, ...],
    ) -> Decimal | None:
        for field_name in field_names:
            raw_value = payload.get(field_name)

            if raw_value is None:
                continue

            try:
                parsed = Decimal(str(raw_value))
                return parsed if parsed.is_finite() else None
            except (InvalidOperation, TypeError, ValueError):
                continue

        return None

    @staticmethod
    def _completeness(observed: int, excluded: int) -> str:
        if observed == 0:
            return "NO_EVENTS"
        return "PARTIAL" if excluded else "COMPLETE"

    @staticmethod
    def _business_zone() -> ZoneInfo:
        return ZoneInfo(settings.business_timezone)

    @classmethod
    def _today_utc_range(cls) -> tuple[datetime, datetime]:
        business_zone = cls._business_zone()
        now_local = datetime.now(business_zone)

        start_local = datetime.combine(
            now_local.date(),
            time.min,
            tzinfo=business_zone,
        )

        end_local = datetime.combine(
            now_local.date(),
            time.max,
            tzinfo=business_zone,
        )

        return (
            start_local.astimezone(timezone.utc),
            end_local.astimezone(timezone.utc),
        )

    @classmethod
    def _trend_utc_range(
        cls,
        days: int,
    ) -> tuple[datetime, datetime, date]:
        business_zone = cls._business_zone()
        today_local = datetime.now(business_zone).date()
        first_date = today_local - timedelta(days=days - 1)

        start_local = datetime.combine(
            first_date,
            time.min,
            tzinfo=business_zone,
        )

        end_local = datetime.combine(
            today_local,
            time.max,
            tzinfo=business_zone,
        )

        return (
            start_local.astimezone(timezone.utc),
            end_local.astimezone(timezone.utc),
            first_date,
        )

    @classmethod
    async def get_today_summary(
        cls,
        session: AsyncSession,
        company_id: UUID,
        recent_limit: int = 10,
    ) -> AnalyticsSummaryResponse:
        period_start, period_end = cls._today_utc_range()

        statement = (
            select(BusinessEvent)
            .where(
                BusinessEvent.company_id == company_id,
                BusinessEvent.occurred_at >= period_start,
                BusinessEvent.occurred_at <= period_end,
            )
            .order_by(
                BusinessEvent.occurred_at.desc(),
                BusinessEvent.created_at.desc(),
            )
        )

        result = await session.execute(statement)
        events = list(result.scalars().all())

        cash_collected = Decimal("0.00")
        booked_revenue = Decimal("0.00")

        payment_count = 0
        estimate_count = 0
        observed_payment_count = 0
        observed_estimate_count = 0
        excluded_payment_count = 0
        excluded_estimate_count = 0
        customer_count = 0
        appointment_count = 0

        for event in events:
            if event.event_type == cls.PAYMENT_RECEIVED:
                observed_payment_count += 1
                amount = cls._decimal_from_payload(
                    event.payload,
                    ("amount", "payment_amount", "total"),
                )
                if amount is None:
                    excluded_payment_count += 1
                else:
                    payment_count += 1
                    cash_collected += amount

            elif event.event_type == cls.ESTIMATE_APPROVED:
                observed_estimate_count += 1
                amount = cls._decimal_from_payload(
                    event.payload,
                    ("amount", "approved_amount", "estimate_total", "total"),
                )
                if amount is None:
                    excluded_estimate_count += 1
                else:
                    estimate_count += 1
                    booked_revenue += amount

            elif event.event_type == cls.CUSTOMER_CREATED:
                customer_count += 1

            elif event.event_type == cls.APPOINTMENT_BOOKED:
                appointment_count += 1

        recent_activity = [
            RecentActivityItem(
                event_type=event.event_type,
                entity_type=event.entity_type,
                payload=event.payload,
                occurred_at=event.occurred_at,
            )
            for event in events[:recent_limit]
        ]

        return AnalyticsSummaryResponse(
            period_start=period_start,
            period_end=period_end,
            timezone=settings.business_timezone,
            cash_collected=MetricValue(
                name="Cash Collected Today",
                value=None
                if excluded_payment_count and not payment_count
                else cash_collected,
                event_count=payment_count,
                observed_event_count=observed_payment_count,
                excluded_event_count=excluded_payment_count,
                completeness=cls._completeness(
                    observed_payment_count, excluded_payment_count
                ),
            ),
            booked_revenue=MetricValue(
                name="Booked Revenue Today",
                value=None
                if excluded_estimate_count and not estimate_count
                else booked_revenue,
                event_count=estimate_count,
                observed_event_count=observed_estimate_count,
                excluded_event_count=excluded_estimate_count,
                completeness=cls._completeness(
                    observed_estimate_count, excluded_estimate_count
                ),
            ),
            new_customers=CountMetric(
                name="New Customers Today",
                value=customer_count,
            ),
            appointments_booked=CountMetric(
                name="Appointments Booked Today",
                value=appointment_count,
            ),
            total_events=CountMetric(
                name="Business Events Today",
                value=len(events),
            ),
            recent_activity=recent_activity,
        )

    @classmethod
    async def get_revenue_trend(
        cls,
        session: AsyncSession,
        company_id: UUID,
        days: int = 7,
    ) -> RevenueTrendResponse:
        period_start, period_end, first_date = cls._trend_utc_range(days)
        business_zone = cls._business_zone()

        statement = (
            select(BusinessEvent)
            .where(
                BusinessEvent.company_id == company_id,
                BusinessEvent.occurred_at >= period_start,
                BusinessEvent.occurred_at <= period_end,
                BusinessEvent.event_type.in_(
                    [cls.PAYMENT_RECEIVED, cls.ESTIMATE_APPROVED]
                ),
            )
            .order_by(BusinessEvent.occurred_at.asc())
        )

        result = await session.execute(statement)
        events = list(result.scalars().all())

        daily_values: dict[date, RevenueTrendDailyValues] = {}

        for offset in range(days):
            day = first_date + timedelta(days=offset)
            daily_values[day] = {
                "booked_revenue": Decimal("0.00"),
                "cash_collected": Decimal("0.00"),
                "booked_event_count": 0,
                "payment_event_count": 0,
                "excluded_booked_event_count": 0,
                "excluded_payment_event_count": 0,
            }

        for event in events:
            local_date = event.occurred_at.astimezone(business_zone).date()
            values = daily_values.get(local_date)

            if values is None:
                continue

            if event.event_type == cls.ESTIMATE_APPROVED:
                amount = cls._decimal_from_payload(
                    event.payload,
                    ("amount", "approved_amount", "estimate_total", "total"),
                )
                if amount is None:
                    values["excluded_booked_event_count"] += 1
                    if not values["booked_event_count"]:
                        values["booked_revenue"] = None
                else:
                    values["booked_revenue"] = (
                        values["booked_revenue"] or Decimal()
                    ) + amount
                    values["booked_event_count"] += 1

            elif event.event_type == cls.PAYMENT_RECEIVED:
                amount = cls._decimal_from_payload(
                    event.payload,
                    ("amount", "payment_amount", "total"),
                )
                if amount is None:
                    values["excluded_payment_event_count"] += 1
                    if not values["payment_event_count"]:
                        values["cash_collected"] = None
                else:
                    values["cash_collected"] = (
                        values["cash_collected"] or Decimal()
                    ) + amount
                    values["payment_event_count"] += 1

        points = [
            RevenueTrendPoint(
                date=day,
                booked_revenue=values["booked_revenue"],
                cash_collected=values["cash_collected"],
                booked_event_count=values["booked_event_count"],
                payment_event_count=values["payment_event_count"],
                excluded_booked_event_count=values["excluded_booked_event_count"],
                excluded_payment_event_count=values["excluded_payment_event_count"],
            )
            for day, values in daily_values.items()
        ]

        excluded_event_count = sum(
            value["excluded_booked_event_count"] + value["excluded_payment_event_count"]
            for value in daily_values.values()
        )
        observed_event_count = sum(
            value["booked_event_count"]
            + value["payment_event_count"]
            + value["excluded_booked_event_count"]
            + value["excluded_payment_event_count"]
            for value in daily_values.values()
        )
        return RevenueTrendResponse(
            period_start=period_start,
            period_end=period_end,
            timezone=settings.business_timezone,
            days=days,
            completeness=cls._completeness(observed_event_count, excluded_event_count),
            excluded_event_count=excluded_event_count,
            points=points,
        )
