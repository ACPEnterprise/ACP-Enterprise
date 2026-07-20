from enum import Enum


class EventType(str, Enum):
    # System
    SYSTEM_STARTED = "system.started"
    MEMBERSHIP_CREATED = "membership.created"
    MEMBERSHIP_ACTIVATED = "membership.activated"
    MEMBERSHIP_SUSPENDED = "membership.suspended"
    MEMBERSHIP_REVOKED = "membership.revoked"
    BRANCH_ACCESS_CHANGED = "branch_access.changed"
    ROLE_CREATED = "role.created"
    ROLE_STATUS_CHANGED = "role.status_changed"
    ROLE_ASSIGNED = "role.assigned"
    ROLE_REVOKED = "role.revoked"
    ROLE_PERMISSIONS_CHANGED = "role_permissions.changed"
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"

    # CRM
    CUSTOMER_CREATED = "customer.created"
    CUSTOMER_UPDATED = "customer.updated"
    CUSTOMER_STATUS_CHANGED = "customer.status_changed"
    CUSTOMER_ARCHIVED = "customer.archived"
    CUSTOMER_RESTORED = "customer.restored"
    PROPERTY_CREATED = "property.created"
    PROPERTY_UPDATED = "property.updated"
    CONTACT_CREATED = "contact.created"
    CONTACT_UPDATED = "contact.updated"
    CONTACT_DEACTIVATED = "contact.deactivated"
    SERVICE_LOCATION_CREATED = "service_location.created"
    SERVICE_LOCATION_UPDATED = "service_location.updated"
    SERVICE_LOCATION_DEACTIVATED = "service_location.deactivated"
    CUSTOMER_NOTE_ADDED = "customer.note_added"
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
