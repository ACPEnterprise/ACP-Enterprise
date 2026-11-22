from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class MetricValue(BaseModel):
    name: str
    value: Decimal | None = Decimal("0.00")
    event_count: int = 0
    observed_event_count: int = 0
    excluded_event_count: int = 0
    completeness: str = "NO_EVENTS"
    authority: str = "business_event_projection"


class CountMetric(BaseModel):
    name: str
    value: int = 0


class RecentActivityItem(BaseModel):
    event_type: str
    entity_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime


class AnalyticsSummaryResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    timezone: str

    cash_collected: MetricValue
    booked_revenue: MetricValue
    new_customers: CountMetric
    appointments_booked: CountMetric
    total_events: CountMetric

    recent_activity: list[RecentActivityItem]


AnalyticsMetricKey = Literal[
    "cash_collected",
    "booked_revenue",
    "new_customers",
    "appointments_booked",
    "total_events",
]


class AnalyticsDrilldownEvent(BaseModel):
    id: UUID
    event_type: str
    entity_type: str
    entity_id: UUID | None
    occurred_at: datetime
    amount: Decimal | None = None


class AnalyticsDrilldownResponse(BaseModel):
    metric: AnalyticsMetricKey
    metric_name: str
    company_id: UUID
    company_name: str
    period_start: datetime
    period_end: datetime
    timezone: str
    value: Decimal | None
    event_count: int
    observed_event_count: int
    excluded_event_count: int
    completeness: str
    authority: str = "business_event_projection"
    events: list[AnalyticsDrilldownEvent]


class RevenueTrendPoint(BaseModel):
    date: date
    booked_revenue: Decimal | None = Decimal("0.00")
    cash_collected: Decimal | None = Decimal("0.00")
    booked_event_count: int = 0
    payment_event_count: int = 0
    excluded_booked_event_count: int = 0
    excluded_payment_event_count: int = 0


class RevenueTrendResponse(BaseModel):
    period_start: datetime
    period_end: datetime
    timezone: str
    days: int
    authority: str = "business_event_projection"
    completeness: str = "NO_EVENTS"
    excluded_event_count: int = 0
    points: list[RevenueTrendPoint]
