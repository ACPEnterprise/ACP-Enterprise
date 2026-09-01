from enum import StrEnum


class CommunicationChannel(StrEnum):
    EMAIL = "email"
    SMS = "sms"


class CommunicationType(StrEnum):
    APPOINTMENT_CONFIRMATION = "appointment_confirmation"
    APPOINTMENT_REMINDER = "appointment_reminder"
    APPOINTMENT_RESCHEDULED = "appointment_rescheduled"
    APPOINTMENT_CANCELLED = "appointment_cancelled"
    TECHNICIAN_EN_ROUTE = "technician_en_route"
    TECHNICIAN_ARRIVED = "technician_arrived"
    ESTIMATE_ACTION_REQUESTED = "estimate_action_requested"
    ESTIMATE_STATUS_NOTICE = "estimate_status_notice"


class CommunicationDeliveryState(StrEnum):
    PREPARED = "prepared"
    PENDING = "pending"
    CLAIMED = "claimed"
    RETRY_SCHEDULED = "retry_scheduled"
    ACCEPTED = "accepted"
    DELIVERED = "delivered"
    DEFERRED = "deferred"
    BOUNCED = "bounced"
    REJECTED = "rejected"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
    CANCELED = "canceled"
    SUPPRESSED = "suppressed"
