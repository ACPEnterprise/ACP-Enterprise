from enum import Enum


class EventType(str, Enum):
    # System
    SYSTEM_STARTED = "system.started"
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"

    # CRM
    CUSTOMER_CREATED = "customer.created"
    CUSTOMER_UPDATED = "customer.updated"
    LEAD_CREATED = "lead.created"
    LEAD_QUALIFIED = "lead.qualified"
    LEAD_CONVERTED = "lead.converted"

    # Communications
    CALL_RECEIVED = "call.received"
    CALL_ANSWERED = "call.answered"

    # Scheduling
    APPOINTMENT_BOOKED = "appointment.booked"
    APPOINTMENT_RESCHEDULED = "appointment.rescheduled"
    APPOINTMENT_CANCELLED = "appointment.cancelled"

    # Dispatch
    TECHNICIAN_DISPATCHED = "technician.dispatched"
    TECHNICIAN_EN_ROUTE = "technician.en_route"
    TECHNICIAN_ARRIVED = "technician.arrived"

    # Sales
    ESTIMATE_CREATED = "estimate.created"
    ESTIMATE_PRESENTED = "estimate.presented"
    ESTIMATE_APPROVED = "estimate.approved"
    ESTIMATE_DECLINED = "estimate.declined"

    # Jobs
    JOB_STARTED = "job.started"
    JOB_COMPLETED = "job.completed"

    # Financial
    INVOICE_CREATED = "invoice.created"
    PAYMENT_RECEIVED = "payment.received"
    PAYMENT_REFUNDED = "payment.refunded"
