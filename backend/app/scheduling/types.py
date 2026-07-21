from enum import StrEnum


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
