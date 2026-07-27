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
    IDENTITY_EMAIL_CHANGE_REQUESTED = "identity.email_change_requested"
    IDENTITY_EMAIL_CHANGED = "identity.email_changed"
    IDENTITY_EMAIL_CHANGE_REVOKED = "identity.email_change_revoked"
    IDENTITY_PASSWORD_RESET_REQUIRED = "identity.password_reset_required"
    IDENTITY_PASSWORD_RESET_CLEARED = "identity.password_reset_cleared"

    # Engineering Control
    ENGINEERING_COMMAND_CREATED = "engineering.command_created"
    ENGINEERING_COMMAND_APPROVED = "engineering.command_approved"
    ENGINEERING_COMMAND_CANCELED = "engineering.command_canceled"
    ENGINEERING_COMMAND_EXPIRED = "engineering.command_expired"
    ENGINEERING_EXECUTION_REQUESTED = "engineering.execution_requested"
    WORKER_IDENTITY_REGISTERED = "engineering.worker_identity_registered"
    WORKER_IDENTITY_STATE_CHANGED = "engineering.worker_identity_state_changed"
    WORKER_CREDENTIAL_ISSUED = "engineering.worker_credential_issued"
    WORKER_CREDENTIAL_ACTIVATED = "engineering.worker_credential_activated"
    WORKER_CREDENTIAL_REVOKED = "engineering.worker_credential_revoked"
    WORKER_CREDENTIAL_EXPIRED = "engineering.worker_credential_expired"
    EXECUTION_PROVIDER_SELECTED = "engineering.execution_provider_selected"
    PROVIDER_EXECUTION_STARTED = "engineering.provider_execution_started"
    PROVIDER_EXECUTION_COMPLETED = "engineering.provider_execution_completed"
    PROVIDER_EXECUTION_FAILED = "engineering.provider_execution_failed"
    EXECUTION_PROVIDER_UNAVAILABLE = "engineering.execution_provider_unavailable"
    EXECUTION_PROVIDER_CAPABILITY_MISMATCH = (
        "engineering.execution_provider_capability_mismatch"
    )
    ENGINEERING_EXECUTION_COMPOSITION_CREATED = (
        "engineering_execution.composition_created"
    )
    ENGINEERING_EXECUTION_COMPOSITION_RECEIPT_CREATED = (
        "engineering_execution.composition_receipt_created"
    )
    ENGINEERING_EXECUTION_ATTEMPT_PREPARED = "engineering_execution.attempt_prepared"
    ENGINEERING_EXECUTION_ATTEMPT_STATE_CHANGED = (
        "engineering_execution.attempt_state_changed"
    )
    ENGINEERING_EXECUTION_PROGRESS_RECORDED = "engineering_execution.progress_recorded"
    ENGINEERING_EXECUTION_RESULT_RECORDED = "engineering_execution.result_recorded"
    ENGINEERING_EXECUTION_RESULT_QUARANTINED = (
        "engineering_execution.result_quarantined"
    )
    ENGINEERING_EXECUTION_CANCELLATION_ACKNOWLEDGED = (
        "engineering_execution.cancellation_acknowledged"
    )
    ENGINEERING_SUPERVISOR_STARTED = "engineering_execution.supervisor_started"
    ENGINEERING_SUPERVISOR_RECOVERED = "engineering_execution.supervisor_recovered"
    ENGINEERING_PROVIDER_SESSION_CREATED = (
        "engineering_execution.provider_session_created"
    )
    ENGINEERING_PROVIDER_SESSION_READY = "engineering_execution.provider_session_ready"
    ENGINEERING_PROVIDER_SESSION_CLOSED = (
        "engineering_execution.provider_session_closed"
    )
    ENGINEERING_PROVIDER_SESSION_STATE_CHANGED = (
        "engineering_execution.provider_session_state_changed"
    )
    ENGINEERING_PROVIDER_RUNTIME_INITIALIZED = (
        "engineering_execution.provider_runtime_initialized"
    )
    ENGINEERING_PROVIDER_CREDENTIAL_VALIDATED = (
        "engineering_execution.provider_credential_validated"
    )
    ENGINEERING_PROVIDER_READY = "engineering_execution.provider_ready"
    ENGINEERING_PROVIDER_SESSION_ESTABLISHED = (
        "engineering_execution.provider_session_established"
    )
    ENGINEERING_PROVIDER_READINESS_VERIFIED = (
        "engineering_execution.provider_readiness_verified"
    )
    ENGINEERING_PROVIDER_EXECUTION_STARTED = (
        "engineering_execution.provider_execution_started"
    )
    ENGINEERING_PROVIDER_EXECUTION_COMPLETED = (
        "engineering_execution.provider_execution_completed"
    )
    ENGINEERING_PROVIDER_EXECUTION_FAILED = (
        "engineering_execution.provider_execution_failed"
    )
    ENGINEERING_REVIEW_PREPARED = "engineering_control.review_prepared"
    ENGINEERING_REVIEW_DECIDED = "engineering_control.review_decided"
    ENGINEERING_REPOSITORY_AUTHORIZATION_REQUESTED = (
        "engineering_control.repository_authorization_requested"
    )
    ENGINEERING_REPOSITORY_AUTHORIZATION_GRANTED = (
        "engineering_control.repository_authorization_granted"
    )
    ENGINEERING_REPOSITORY_AUTHORIZATION_REVOKED = (
        "engineering_control.repository_authorization_revoked"
    )
    ENGINEERING_REPOSITORY_AUTHORIZATION_EXPIRED = (
        "engineering_control.repository_authorization_expired"
    )
    ENGINEERING_REPOSITORY_AUTHORIZATION_CONSUMED = (
        "engineering_control.repository_authorization_consumed"
    )
    ENGINEERING_PROVIDER_RUNTIME_CLOSED = (
        "engineering_execution.provider_runtime_closed"
    )
    ENGINEERING_PROVIDER_RUNTIME_FAILED = (
        "engineering_execution.provider_runtime_failed"
    )

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
    APPOINTMENT_CREATED = "appointment.created"
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
    JOB_CREATED = "job.created"
    JOB_UPDATED = "job.updated"
    JOB_ACTIVATED = "job.activated"
    JOB_APPOINTMENT_LINKED = "job.appointment_linked"
    JOB_STARTED = "job.started"
    JOB_PAUSED = "job.paused"
    JOB_RESUMED = "job.resumed"
    JOB_COMPLETED = "job.completed"
    JOB_CANCELLED = "job.cancelled"
    JOB_REOPENED = "job.reopened"

    # Financial
    INVOICE_CREATED = "invoice.created"
    PAYMENT_RECEIVED = "payment.received"
    PAYMENT_REFUNDED = "payment.refunded"
