from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class MetricValue(BaseModel):
    name: str
    value: Decimal = Decimal("0.00")
    event_count: int = 0


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
