from enum import Enum


class EventType(str, Enum):
    # Beacon workflow
    BEACON_SIGNAL_ACKNOWLEDGED = "beacon.signal_acknowledged"
    BEACON_SIGNAL_CLAIMED = "beacon.signal_claimed"
    BEACON_SIGNAL_ASSIGNED = "beacon.signal_assigned"
    BEACON_SIGNAL_TRANSFERRED = "beacon.signal_transferred"
    BEACON_SIGNAL_RELEASED = "beacon.signal_released"

    # Workday Time
    WORKDAY_PUNCH_RECORDED = "timekeeping.punch_recorded"
    WORKDAY_MANUAL_TIME_RECORDED = "timekeeping.manual_time_recorded"
    WORKDAY_TIME_SUBMITTED = "timekeeping.time_submitted"
    WORKDAY_TIME_APPROVED = "timekeeping.time_approved"
    WORKDAY_TIME_CORRECTED = "timekeeping.time_corrected"
    WORKDAY_TIME_SUPERSEDED = "timekeeping.time_superseded"
    PAYROLL_POLICY_DRAFTED = "payroll.policy_drafted"
    PAYROLL_POLICY_APPROVED = "payroll.policy_approved"
    PAYROLL_POLICY_SUPERSEDED = "payroll.policy_superseded"
    PAYROLL_POLICY_RETIRED = "payroll.policy_retired"
    PAYROLL_COMPENSATION_DRAFTED = "payroll.compensation_drafted"
    PAYROLL_COMPENSATION_APPROVED = "payroll.compensation_approved"
    PAYROLL_COMPENSATION_SUPERSEDED = "payroll.compensation_superseded"
    PAYROLL_COMPENSATION_RETIRED = "payroll.compensation_retired"
    PAYROLL_ADMISSION_EVALUATED = "payroll.admission_evaluated"
    PAYROLL_GROSS_CALCULATION_PERSISTED = "payroll.gross_calculation_persisted"
    PAYROLL_GROSS_REVIEW_INITIATED = "payroll.gross_review_initiated"
    PAYROLL_GROSS_REVIEW_ACCEPTED = "payroll.gross_review_accepted"
    PAYROLL_GROSS_REVIEW_REJECTED = "payroll.gross_review_rejected"
    PAYROLL_GROSS_CALCULATION_SUPERSEDED = "payroll.gross_calculation_superseded"
    PAYROLL_GROSS_CALCULATION_VOIDED = "payroll.gross_calculation_voided"
    PAYROLL_INPUT_AUTHORITY_DRAFTED = "payroll.input_authority_drafted"
    PAYROLL_INPUT_AUTHORITY_APPROVED = "payroll.input_authority_approved"
    PAYROLL_INPUT_AUTHORITY_SUPERSEDED = "payroll.input_authority_superseded"
    PAYROLL_INPUT_AUTHORITY_RETIRED = "payroll.input_authority_retired"
    PAYROLL_TAX_DEDUCTION_ADMISSION_EVALUATED = (
        "payroll.tax_deduction_admission_evaluated"
    )
    PAYROLL_TAX_RESULT_PERSISTED = "payroll.tax_result_persisted"
    PAYROLL_TAX_RESULT_REVIEW_INITIATED = "payroll.tax_result_review_initiated"
    PAYROLL_TAX_RESULT_REVIEW_ACCEPTED = "payroll.tax_result_review_accepted"
    PAYROLL_TAX_RESULT_REVIEW_REJECTED = "payroll.tax_result_review_rejected"
    PAYROLL_TAX_RESULT_SUPERSEDED = "payroll.tax_result_superseded"
    PAYROLL_TAX_RESULT_VOIDED = "payroll.tax_result_voided"
    PAYROLL_RUN_ASSEMBLED = "payroll.run_assembled"
    PAYROLL_RUN_REVIEW_INITIATED = "payroll.run_review_initiated"
    PAYROLL_RUN_REVIEW_ACCEPTED = "payroll.run_review_accepted"
    PAYROLL_RUN_REVIEW_REJECTED = "payroll.run_review_rejected"
    PAYROLL_RUN_APPROVED = "payroll.run_approved"
    PAYROLL_RUN_SUPERSEDED = "payroll.run_superseded"
    PAYROLL_RUN_VOIDED = "payroll.run_voided"
    PAYROLL_PAYMENT_DESTINATION_CREATED = "payroll.payment_destination_created"
    PAYROLL_PAYMENT_DESTINATION_APPROVED = "payroll.payment_destination_approved"
    PAYROLL_PAYMENT_DESTINATION_REVOKED = "payroll.payment_destination_revoked"
    PAYROLL_PAYMENT_RELEASE_ASSEMBLED = "payroll.payment_release_assembled"
    PAYROLL_PAYMENT_RELEASE_REVIEWED = "payroll.payment_release_reviewed"
    PAYROLL_PAYMENT_RELEASE_APPROVED = "payroll.payment_release_approved"
    PAYROLL_PAYMENT_RELEASE_SUPERSEDED = "payroll.payment_release_superseded"
    PAYROLL_PAYMENT_EXECUTION_AUTHORIZED = "payroll.payment_execution_authorized"
    PAYROLL_PAYMENT_EXECUTION_SUBMITTED = "payroll.payment_execution_submitted"
    PAYROLL_PAYMENT_EXECUTION_ACKNOWLEDGED = "payroll.payment_execution_acknowledged"
    PAYROLL_PAYMENT_SETTLEMENT_RECORDED = "payroll.payment_settlement_recorded"
    PAYROLL_PAYMENT_EXECUTION_FAILED = "payroll.payment_execution_failed"
    PAYROLL_ACCOUNTING_POLICY_CREATED = "payroll.accounting_policy_created"
    PAYROLL_ACCOUNTING_POLICY_APPROVED = "payroll.accounting_policy_approved"
    PAYROLL_ACCOUNTING_MAPPING_CREATED = "payroll.accounting_mapping_created"
    PAYROLL_ACCOUNTING_MAPPING_APPROVED = "payroll.accounting_mapping_approved"
    PAYROLL_ACCOUNTING_FACT_PREPARED = "payroll.accounting_fact_prepared"
    PAYROLL_ACCOUNTING_FACT_POSTED = "payroll.accounting_fact_posted"
    PAYROLL_STATEMENT_CREATED = "payroll.statement_created"
    PAYROLL_STATEMENT_ISSUED = "payroll.statement_issued"
    PAYROLL_STATEMENT_ACCESSED = "payroll.statement_accessed"
    PAYROLL_STATEMENT_ARTIFACT_GENERATED = "payroll.statement_artifact_generated"
    PAYROLL_STATEMENT_ARTIFACT_ACCESSED = "payroll.statement_artifact_accessed"
    PAYROLL_STATEMENT_DELIVERY_PREPARED = "payroll.statement_delivery_prepared"
    PAYROLL_REPORT_CREATED = "payroll.report_created"
    PAYROLL_FILING_PACKAGE_PREPARED = "payroll.filing_package_prepared"
    PAYROLL_REPORT_ARTIFACT_GENERATED = "payroll.report_artifact_generated"
    ECONOMICS_PROFITABILITY_ADMITTED = "economics.profitability_admitted"
    PAYROLL_ADJUSTMENT_CREATED = "payroll.adjustment_created"
    PAYROLL_ADJUSTMENT_REVIEWED = "payroll.adjustment_reviewed"
    PAYROLL_ADJUSTMENT_APPROVED = "payroll.adjustment_approved"
    PAYROLL_ADJUSTMENT_SUPERSEDED = "payroll.adjustment_superseded"
    PAYROLL_ADJUSTMENT_RESULT_PERSISTED = "payroll.adjustment_result_persisted"
    PAYROLL_ADJUSTMENT_RESULT_REVIEWED = "payroll.adjustment_result_reviewed"
    PAYROLL_ADJUSTMENT_RESULT_APPROVED = "payroll.adjustment_result_approved"
    PAYROLL_ADJUSTMENT_RESULT_SUPERSEDED = "payroll.adjustment_result_superseded"
    PAYROLL_ADJUSTMENT_RESULT_APPLIED = "payroll.adjustment_result_applied"
    PAYROLL_REMITTANCE_POLICY_CREATED = "payroll.remittance_policy_created"
    PAYROLL_REMITTANCE_POLICY_APPROVED = "payroll.remittance_policy_approved"
    PAYROLL_REMITTANCE_DESTINATION_CREATED = "payroll.remittance_destination_created"
    PAYROLL_REMITTANCE_DESTINATION_APPROVED = "payroll.remittance_destination_approved"
    PAYROLL_REMITTANCE_OBLIGATION_IDENTIFIED = (
        "payroll.remittance_obligation_identified"
    )
    PAYROLL_REMITTANCE_REVIEWED = "payroll.remittance_reviewed"
    PAYROLL_REMITTANCE_APPROVED = "payroll.remittance_approved"
    PAYROLL_REMITTANCE_INSTRUCTION_PREPARED = "payroll.remittance_instruction_prepared"
    PAYROLL_REMITTANCE_ACKNOWLEDGED = "payroll.remittance_acknowledged"
    PAYROLL_REMITTANCE_SETTLED = "payroll.remittance_settled"
    PAYROLL_REMITTANCE_RETURNED = "payroll.remittance_returned"

    # Accounts Payable
    ACCOUNTS_PAYABLE_VENDOR_CREATED = "accounts_payable.vendor_created"
    ACCOUNTS_PAYABLE_VENDOR_MAPPED = "accounts_payable.vendor_mapped"
    ACCOUNTS_PAYABLE_BILL_APPROVED = "accounts_payable.bill_approved"
    ACCOUNTS_PAYABLE_BILL_REVERSED = "accounts_payable.bill_reversed"
    ACCOUNTS_PAYABLE_VENDOR_CREDIT_ISSUED = "accounts_payable.vendor_credit_issued"
    ACCOUNTS_PAYABLE_VENDOR_CREDIT_APPLIED = "accounts_payable.vendor_credit_applied"
    ACCOUNTS_PAYABLE_DISBURSEMENT_RECORDED = "accounts_payable.disbursement_recorded"
    ACCOUNTS_PAYABLE_DISBURSEMENT_REVERSED = "accounts_payable.disbursement_reversed"
    ACCOUNTS_PAYABLE_RECONCILIATION_REQUIRED = (
        "accounts_payable.reconciliation_required"
    )
    PROCUREMENT_MATCH_EVALUATED = "procurement.match_evaluated"
    PROCUREMENT_MATCH_EXCEPTION_RESOLVED = "procurement.match_exception_resolved"

    # Payments
    PAYMENT_INTENT_CREATED = "payment.intent_created"
    PAYMENT_AUTHORIZATION_RECORDED = "payment.authorization_recorded"
    PAYMENT_RECEIPT_CAPTURED = "payment.receipt_captured"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_REFUND_REQUESTED = "payment.refund_requested"
    PAYMENT_REFUND_SUCCEEDED = "payment.refund_succeeded"
    PAYMENT_REFUND_FAILED = "payment.refund_failed"
    PAYMENT_DISPUTE_RECORDED = "payment.dispute_recorded"
    PAYMENT_DEPOSIT_SUBMITTED = "payment.deposit_submitted"
    PAYMENT_DEPOSIT_REVERSED = "payment.deposit_reversed"
    PAYMENT_SETTLEMENT_RECEIVED = "payment.settlement_received"
    PAYMENT_SETTLEMENT_RECONCILED = "payment.settlement_reconciled"
    PAYMENT_RECONCILIATION_EXCEPTION_OPENED = "payment.reconciliation_exception_opened"
    PAYMENT_RECONCILIATION_EXCEPTION_RESOLVED = (
        "payment.reconciliation_exception_resolved"
    )

    # Accounting
    ACCOUNTING_JOURNAL_POSTED = "accounting.journal_posted"
    ACCOUNTING_JOURNAL_REVERSED = "accounting.journal_reversed"
    ACCOUNTING_PERIOD_CLOSED = "accounting.period_closed"
    ACCOUNTING_PERIOD_REOPENED = "accounting.period_reopened"
    ACCOUNTING_POSTING_FAILED = "accounting.posting_failed"

    # Inventory
    INVENTORY_LOCATION_CREATED = "inventory.location_created"
    INVENTORY_TRANSFER_POSTED = "inventory.transfer_posted"
    INVENTORY_ADJUSTMENT_POSTED = "inventory.adjustment_posted"
    INVENTORY_CYCLE_COUNT_STARTED = "inventory.cycle_count_started"
    INVENTORY_CYCLE_COUNT_RECORDED = "inventory.cycle_count_recorded"
    INVENTORY_CYCLE_COUNT_COMPLETED = "inventory.cycle_count_completed"
    INVENTORY_RESERVATION_CREATED = "inventory.reservation_created"
    INVENTORY_RESERVATION_RELEASED = "inventory.reservation_released"
    INVENTORY_PURCHASE_RECEIPT_POSTED = "inventory.purchase_receipt.posted"
    INVENTORY_PURCHASE_RETURN_POSTED = "inventory.purchase_return.posted"

    # Purchasing
    PURCHASING_VENDOR_CREATED = "purchasing.vendor_created"
    PURCHASING_VENDOR_UPDATED = "purchasing.vendor_updated"
    PURCHASING_PURCHASE_ORDER_CREATED = "purchasing.purchase_order_created"
    PURCHASING_PURCHASE_ORDER_SUBMITTED = "purchasing.purchase_order_submitted"
    PURCHASING_PURCHASE_ORDER_APPROVED = "purchasing.purchase_order_approved"
    PURCHASING_PURCHASE_ORDER_ISSUED = "purchasing.purchase_order_issued"
    PURCHASING_PURCHASE_ORDER_CANCELLED = "purchasing.purchase_order_cancelled"
    PURCHASING_PURCHASE_ORDER_CLOSED = "purchasing.purchase_order_closed"
    PURCHASING_PURCHASE_ORDER_RECEIPT_RECORDED = (
        "purchasing.purchase_order.receipt_recorded"
    )
    PURCHASING_PURCHASE_ORDER_PARTIALLY_RECEIVED = (
        "purchasing.purchase_order.partially_received"
    )
    PURCHASING_PURCHASE_ORDER_FULLY_RECEIVED = (
        "purchasing.purchase_order.fully_received"
    )
    PURCHASING_PURCHASE_ORDER_DISCREPANCY_OPENED = (
        "purchasing.purchase_order.discrepancy_opened"
    )
    PURCHASING_PURCHASE_ORDER_DISCREPANCY_RESOLVED = (
        "purchasing.purchase_order.discrepancy_resolved"
    )
    PURCHASING_PURCHASE_RETURN_CREATED = "purchasing.purchase_return.created"
    PURCHASING_PURCHASE_RETURN_AUTHORIZATION_REQUESTED = (
        "purchasing.purchase_return.authorization_requested"
    )
    PURCHASING_PURCHASE_RETURN_AUTHORIZED = "purchasing.purchase_return.authorized"
    PURCHASING_PURCHASE_RETURN_DENIED = "purchasing.purchase_return.denied"
    PURCHASING_PURCHASE_RETURN_READY = "purchasing.purchase_return.return_ready"
    PURCHASING_PURCHASE_RETURN_RETURNED = "purchasing.purchase_return.returned"
    PURCHASING_PURCHASE_RETURN_VENDOR_RECEIVED = (
        "purchasing.purchase_return.vendor_received"
    )
    PURCHASING_PURCHASE_RETURN_CLOSED = "purchasing.purchase_return.closed"
    PURCHASING_PURCHASE_RETURN_CANCELED = "purchasing.purchase_return.canceled"
    PURCHASING_PURCHASE_ORDER_CHANGE_REQUESTED = (
        "purchasing.purchase_order.change_requested"
    )
    PURCHASING_PURCHASE_ORDER_CHANGE_APPROVED = (
        "purchasing.purchase_order.change_approved"
    )
    PURCHASING_PURCHASE_ORDER_CHANGE_REJECTED = (
        "purchasing.purchase_order.change_rejected"
    )
    PURCHASING_PURCHASE_ORDER_REVISED = "purchasing.purchase_order.revised"
    PURCHASING_PURCHASE_ORDER_COMPLETED = "purchasing.purchase_order.completed"
    PURCHASING_PURCHASE_ORDER_REMAINDER_CANCELED = (
        "purchasing.purchase_order.remainder_canceled"
    )
    PURCHASING_REPLENISHMENT_APPROVED = "purchasing.replenishment.approved"
    PURCHASING_REPLENISHMENT_REJECTED = "purchasing.replenishment.rejected"
    PURCHASING_REPLENISHMENT_LINKED = "purchasing.replenishment.purchase_order_linked"
    PURCHASING_BRANCH_POLICY_CONFIGURED = "purchasing.branch_policy.configured"

    # Operations
    OPERATIONS_SERVICE_REQUEST_ACCEPTED = "operations.service_request.accepted"

    # Technician field execution
    FIELD_NOTE_RECORDED = "field.note_recorded"
    FIELD_CUSTOMER_APPROVAL_RECORDED = "field.customer_approval_recorded"
    FIELD_NON_BILLABLE_AUTHORIZED = "field.non_billable_authorized"
    FIELD_COMPLETION_REQUIREMENTS_SATISFIED = "field.completion_requirements_satisfied"
    FIELD_INVOICE_HANDOFF_REQUESTED = "field.invoice_handoff_requested"
    FIELD_INVOICE_HANDOFF_COMPLETED = "field.invoice_handoff_completed"

    # Price Book
    PRICE_BOOK_PRICE_VERSION_ACTIVATED = "price_book.price_version_activated"

    # Dispatch
    DISPATCH_ASSIGNMENT_CREATED = "dispatch.assignment.created"
    DISPATCH_ASSIGNMENT_REPLACED = "dispatch.assignment.replaced"
    DISPATCH_ASSIGNMENT_RELEASED = "dispatch.assignment.released"
    DISPATCH_CREW_MEMBER_ADDED = "dispatch.crew_member.added"
    DISPATCH_CREW_MEMBER_REMOVED = "dispatch.crew_member.removed"
    DISPATCH_ASSIGNMENT_RECONCILIATION_REQUIRED = (
        "dispatch.assignment.reconciliation_required"
    )
    DISPATCH_ASSIGNMENT_RECONCILED = "dispatch.assignment.reconciled"

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
    IDENTITY_ONBOARDING_INITIATED = "identity.onboarding_initiated"
    IDENTITY_INVITATION_ISSUED = "identity.invitation_issued"
    IDENTITY_INVITATION_REVOKED = "identity.invitation_revoked"
    IDENTITY_INVITATION_SUPERSEDED = "identity.invitation_superseded"
    IDENTITY_ONBOARDING_ACTIVATED = "identity.onboarding_activated"
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
    ENGINEERING_CONTROLLED_OFFER_CREATED = (
        "engineering_execution.controlled_offer_created"
    )
    ENGINEERING_CONTROLLED_OFFER_ACQUIRED = (
        "engineering_execution.controlled_offer_acquired"
    )
    ENGINEERING_CONTROLLED_EXECUTION_COMPLETED = (
        "engineering_execution.controlled_execution_completed"
    )
    ENGINEERING_CONTROLLED_EXECUTION_FAILED = (
        "engineering_execution.controlled_execution_failed"
    )
    ENGINEERING_CONTROLLED_RESULT_ADOPTED = (
        "engineering_execution.controlled_result_adopted"
    )
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
    ENGINEERING_REPOSITORY_OPERATION_REQUESTED = (
        "engineering_control.repository_operation_requested"
    )
    ENGINEERING_REPOSITORY_OPERATION_RESERVED = (
        "engineering_control.repository_operation_reserved"
    )
    ENGINEERING_REPOSITORY_OPERATION_STARTED = (
        "engineering_control.repository_operation_started"
    )
    ENGINEERING_REPOSITORY_OPERATION_SUCCEEDED = (
        "engineering_control.repository_operation_succeeded"
    )
    ENGINEERING_REPOSITORY_OPERATION_FAILED = (
        "engineering_control.repository_operation_failed"
    )
    ENGINEERING_REPOSITORY_OPERATION_RECONCILIATION_REQUIRED = (
        "engineering_control.repository_operation_reconciliation_required"
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
    CUSTOMER_BILLING_ADDRESS_CREATED = "customer.billing_address_created"
    CUSTOMER_NOTE_ADDED = "customer.note_added"
    CUSTOMER_CONSENT_RECORDED = "customer.consent_recorded"
    LEAD_CREATED = "lead.created"
    LEAD_QUALIFIED = "lead.qualified"
    LEAD_CONVERTED = "lead.converted"

    # Communications
    CALL_RECEIVED = "call.received"
    CALL_ANSWERED = "call.answered"
    COMMUNICATION_REQUESTED = "communication.requested"

    # Scheduling
    APPOINTMENT_CREATED = "appointment.created"
    APPOINTMENT_BOOKED = "appointment.booked"
    APPOINTMENT_RESCHEDULED = "appointment.rescheduled"
    APPOINTMENT_CANCELLED = "appointment.cancelled"
    APPOINTMENT_MIGRATED = "appointment.migrated"

    # Dispatch
    TECHNICIAN_DISPATCHED = "technician.dispatched"
    TECHNICIAN_EN_ROUTE = "technician.en_route"
    TECHNICIAN_ARRIVED = "technician.arrived"

    # Sales
    ESTIMATE_CREATED = "estimate.created"
    ESTIMATE_REVISION_CREATED = "estimate.revision_created"
    ESTIMATE_LIFECYCLE_CHANGED = "estimate.lifecycle_changed"
    ESTIMATE_SENT = "estimate.sent"
    ESTIMATE_VIEWED = "estimate.viewed"
    ESTIMATE_PRESENTED = "estimate.presented"
    ESTIMATE_APPROVED = "estimate.approved"
    ESTIMATE_REJECTED = "estimate.rejected"
    ESTIMATE_EXPIRED = "estimate.expired"
    ESTIMATE_DECLINED = "estimate.declined"
    ESTIMATE_MIGRATED = "estimate.migrated"
    ESTIMATE_CONVERTED = "estimate.converted"
    COMMERCIAL_POLICY_CONFIGURED = "commercial.policy.configured"
    ESTIMATE_PRESENTATION_PREPARED = "estimate.presentation_prepared"
    ESTIMATE_PRESENTATION_VIEWED = "estimate.presentation_viewed"
    ESTIMATE_FOLLOW_UP_CHANGED = "estimate.follow_up_changed"

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
    JOB_MIGRATED = "job.migrated"

    # Financial
    INVOICE_CREATED = "invoice.created"
    INVOICE_ISSUED = "invoice.issued"
    INVOICE_VOIDED = "invoice.voided"
    INVOICE_CREDIT_MEMO_ISSUED = "invoice.credit_memo_issued"
    INVOICE_WRITE_OFF_RECORDED = "invoice.write_off_recorded"
    INVOICE_PAYMENT_APPLIED = "invoice.payment_applied"
    INVOICE_PAYMENT_APPLICATION_REVERSED = "invoice.payment_application_reversed"
    INVOICE_CORRECTION_REPLACEMENT_LINKED = "invoice.correction_replacement_linked"
    INVOICE_MIGRATED = "invoice.migrated"
    PAYMENT_RECEIVED = "payment.received"
    PAYMENT_REFUNDED = "payment.refunded"
    PAYMENT_MIGRATED = "payment.migrated"

    # Migration
    NOTE_MIGRATED = "note.migrated"
    ACTIVITY_MIGRATED = "activity.migrated"
    ARTIFACT_REGISTERED = "artifact.registered"
    ARTIFACT_MIGRATED = "artifact.migrated"
    MIGRATION_CUTOVER_READINESS_EVALUATED = "migration.cutover_readiness_evaluated"
    MIGRATION_COMPLETED = "migration.completed"
    MIGRATION_COMPLETED_WITH_EXCEPTIONS = "migration.completed_with_exceptions"
