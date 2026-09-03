from enum import StrEnum


class CommunicationChannel(StrEnum):
    EMAIL = "email"
    SMS = "sms"
    PROTECTED_LINK = "protected_link"
    PRINT = "print"
    IN_APP = "in_app"


class CommunicationPurpose(StrEnum):
    ACCOUNT_SECURITY = "account_security"
    TRANSACTIONAL = "transactional"
    OPERATIONAL = "operational"
    MARKETING_OUTREACH = "marketing_outreach"
    INTERNAL = "internal"


class CommunicationType(StrEnum):
    EMPLOYEE_INVITATION = "employee_invitation"
    ACCOUNT_ACTIVATION = "account_activation"
    SECURITY_NOTIFICATION = "security_notification"
    APPOINTMENT_CONFIRMATION = "appointment_confirmation"
    APPOINTMENT_REMINDER = "appointment_reminder"
    APPOINTMENT_RESCHEDULED = "appointment_rescheduled"
    APPOINTMENT_CANCELLED = "appointment_cancelled"
    TECHNICIAN_EN_ROUTE = "technician_en_route"
    TECHNICIAN_ASSIGNED = "technician_assigned"
    TECHNICIAN_ARRIVED = "technician_arrived"
    WORK_COMPLETED = "work_completed"
    ESTIMATE_ACTION_REQUESTED = "estimate_action_requested"
    ESTIMATE_STATUS_NOTICE = "estimate_status_notice"
    ESTIMATE_FOLLOW_UP = "estimate_follow_up"
    INVOICE_READY = "invoice_ready"
    PAYMENT_RECEIPT = "payment_receipt"
    PAYMENT_STATUS_NOTIFICATION = "payment_status_notification"
    SERVICE_AGREEMENT_NOTICE = "service_agreement_notice"


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
