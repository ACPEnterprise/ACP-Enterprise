from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


@dataclass(frozen=True)
class AppointmentReference:
    id: UUID
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID
    status: "AppointmentStatus"


class AppointmentStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


class AppointmentCancellationReason(StrEnum):
    CUSTOMER_REQUEST = "customer_request"
    DUPLICATE_APPOINTMENT = "duplicate_appointment"
    SCHEDULING_CONFLICT = "scheduling_conflict"
    SERVICE_UNAVAILABLE = "service_unavailable"


class AppointmentRescheduleReason(StrEnum):
    CUSTOMER_REQUEST = "customer_request"
    OPERATIONAL_ADJUSTMENT = "operational_adjustment"
    SCHEDULING_CONFLICT = "scheduling_conflict"
    WEATHER = "weather"
