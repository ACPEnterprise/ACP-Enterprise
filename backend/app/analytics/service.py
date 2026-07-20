from datetime import datetime, time, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.schemas import (
    AnalyticsSummaryResponse,
    CountMetric,
    MetricValue,
    RecentActivityItem,
)
from app.core.config import settings
from app.events.models import BusinessEvent


class AnalyticsService:
    PAYMENT_RECEIVED = "payment.received"
    ESTIMATE_APPROVED = "estimate.approved"
    CUSTOMER_CREATED = "customer.created"
    APPOINTMENT_BOOKED = "appointment.booked"

    @staticmethod
    def _decimal_from_payload(
        payload: dict[str, Any],
        field_names: tuple[str, ...],
    ) -> Decimal:
        for field_name in field_names:
            raw_value = payload.get(field_name)

            if raw_value is None:
                continue

            try:
                return Decimal(str(raw_value))
            except (InvalidOperation, TypeError, ValueError):
                continue

        return Decimal("0.00")

    @staticmethod
    def _today_utc_range() -> tuple[datetime, datetime]:
        business_zone = ZoneInfo(settings.business_timezone)
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
        customer_count = 0
        appointment_count = 0

        for event in events:
            if event.event_type == cls.PAYMENT_RECEIVED:
                payment_count += 1
                cash_collected += cls._decimal_from_payload(
                    event.payload,
                    (
                        "amount",
                        "payment_amount",
                        "total",
                    ),
                )

            elif event.event_type == cls.ESTIMATE_APPROVED:
                estimate_count += 1
                booked_revenue += cls._decimal_from_payload(
                    event.payload,
                    (
                        "amount",
                        "approved_amount",
                        "estimate_total",
                        "total",
                    ),
                )

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
                value=cash_collected,
                event_count=payment_count,
            ),
            booked_revenue=MetricValue(
                name="Booked Revenue Today",
                value=booked_revenue,
                event_count=estimate_count,
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
