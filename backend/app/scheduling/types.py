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


class AppointmentCapacityState(StrEnum):
    RESERVED = "reserved"
    INTENTIONALLY_UNASSIGNED = "intentionally_unassigned"
    LEGACY_UNRECONCILED = "legacy_unreconciled"


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


class SchedulingOverrideReason(StrEnum):
    EMERGENCY_SERVICE = "emergency_service"
    CUSTOMER_REQUESTED = "customer_requested"
    DISPATCHER_OVERRIDE = "dispatcher_override"
    OWNER_OVERRIDE = "owner_override"
    AFTER_HOURS_CALL = "after_hours_call"
    OTHER = "other"
