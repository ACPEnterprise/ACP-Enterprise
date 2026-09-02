import json
from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True)
class QualityRule:
    rule_id: str
    version: int
    domain: str
    state: str
    severity: str
    launch_impact: str
    explanation: str
    evidence_required: tuple[str, ...]
    repair_owner: str
    automated_correction_prohibited: bool = True

    @property
    def digest(self) -> str:
        payload = {
            "automated_correction_prohibited": self.automated_correction_prohibited,
            "domain": self.domain,
            "evidence_required": self.evidence_required,
            "explanation": self.explanation,
            "launch_impact": self.launch_impact,
            "repair_owner": self.repair_owner,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "state": self.state,
            "version": self.version,
        }
        return sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _rule(rule_id: str, domain: str, state: str, severity: str, impact: str,
          explanation: str, evidence: tuple[str, ...], owner: str) -> QualityRule:
    return QualityRule(rule_id, 1, domain, state, severity, impact, explanation,
                       evidence, owner)


QUALITY_CATALOG = (
    _rule("DQ-CUSTOMER-001", "CUSTOMERS", "INCOMPLETE", "HIGH", "BLOCKS_SPECIFIC_RECORD", "Customer has no usable display identity for office workflows.", ("customer.display_name",), "CUSTOMERS"),
    _rule("DQ-CUSTOMER-002", "CUSTOMERS", "DUPLICATE_CANDIDATE", "MEDIUM", "OWNER_REVIEW", "Normalized Customer identity is shared by multiple records; this is evidence for review, not a merge decision.", ("customer.normalized_name",), "CUSTOMER_SURVIVORSHIP"),
    _rule("DQ-CONTACT-001", "CONTACTS", "INCOMPLETE", "LOW", "BLOCKS_SPECIFIC_RECORD", "Active Contact has neither an admitted email nor phone destination.", ("contact.email", "contact.mobile_phone", "contact.office_phone"), "CUSTOMERS"),
    _rule("DQ-LOCATION-001", "LOCATIONS", "INCOMPLETE", "HIGH", "BLOCKS_SPECIFIC_RECORD", "Service Location lacks complete operational address evidence.", ("location.address", "location.city", "location.state", "location.postal_code"), "CUSTOMERS"),
    _rule("DQ-LOCATION-002", "LOCATIONS", "CONFLICTING", "CRITICAL", "BLOCKS_SPECIFIC_RECORD", "Service Location and Customer tenant scopes conflict.", ("location.customer_id", "customer.company_id"), "CUSTOMERS"),
    _rule("DQ-JOB-001", "JOBS", "CONFLICTING", "CRITICAL", "BLOCKS_SPECIFIC_RECORD", "Job, Customer, Location, or Branch scope is inconsistent.", ("job.company_id", "job.branch_id", "job.customer_id", "job.service_location_id"), "JOBS"),
    _rule("DQ-APPOINTMENT-001", "APPOINTMENTS", "CONFLICTING", "CRITICAL", "BLOCKS_SPECIFIC_RECORD", "Appointment scope conflicts with its linked Job or service context.", ("appointment.company_id", "appointment.branch_id", "job.id"), "SCHEDULING"),
    _rule("DQ-EMPLOYEE-001", "EMPLOYEES", "INCOMPLETE", "HIGH", "BLOCKS_SPECIFIC_RECORD", "Employee lacks required Company, Membership, access, or Branch evidence.", ("employee.company_id", "employee.membership_id", "employee.branch_id"), "WORKFORCE"),
    _rule("DQ-ESTIMATE-001", "ESTIMATES", "STALE", "HIGH", "BLOCKS_SPECIFIC_RECORD", "Estimate presentation or delivery references a stale/superseded revision.", ("estimate.current_revision", "presentation.revision"), "COMMERCIAL_SALES"),
    _rule("DQ-INVOICE-001", "INVOICES", "CONFLICTING", "CRITICAL", "BLOCKS_SPECIFIC_RECORD", "Invoice source, Customer, Job, or tenant scope is inconsistent.", ("invoice.company_id", "invoice.customer_id", "invoice.job_id"), "REVENUE_COLLECTION"),
    _rule("DQ-PAYMENT-001", "PAYMENTS", "CONFLICTING", "CRITICAL", "BLOCKS_SPECIFIC_RECORD", "Payment application is unlinked, over-applied, duplicated, or settlement evidence is ambiguous.", ("payment.source_identity", "application.invoice_id", "settlement.state"), "PAYMENTS"),
    _rule("DQ-INVENTORY-001", "INVENTORY", "ORPHANED", "CRITICAL", "BLOCKS_SPECIFIC_RECORD", "Inventory movement has invalid item/location or admitted source evidence.", ("movement.item_id", "movement.location_id", "movement.source"), "INVENTORY"),
    _rule("DQ-AGREEMENT-001", "SERVICE_AGREEMENTS", "CONFLICTING", "HIGH", "BLOCKS_SPECIFIC_RECORD", "Agreement enrollment, plan version, coverage, entitlement, or billing readiness conflicts.", ("agreement.customer_id", "agreement.plan_version", "coverage.location_id"), "SERVICE_AGREEMENTS"),
    _rule("DQ-ASSET-001", "ASSETS", "CONFLICTING", "HIGH", "BLOCKS_SPECIFIC_RECORD", "Asset relationship, identifier, replacement, or service evidence conflicts.", ("asset.company_id", "asset.relationships", "asset.evidence"), "ASSETS"),
    _rule("DQ-FLEET-001", "FLEET", "CONFLICTING", "HIGH", "BLOCKS_SPECIFIC_RECORD", "Vehicle has conflicting assignment/readiness evidence.", ("vehicle.assignments", "vehicle.readiness"), "ASSETS"),
    _rule("DQ-CUSTODY-001", "CUSTODY", "CONFLICTING", "HIGH", "BLOCKS_SPECIFIC_RECORD", "Tracked Asset has multiple incompatible current custodians.", ("asset.custody_history",), "ASSETS"),
    _rule("DQ-COMMS-001", "COMMUNICATION_DESTINATIONS", "INCOMPLETE", "MEDIUM", "BLOCKS_SPECIFIC_RECORD", "Destination is missing, invalid, suppressed, or conflicts with preference evidence.", ("contact.destination", "preference.state"), "COMMUNICATIONS"),
    _rule("DQ-TIME-001", "TIMEKEEPING", "CONFLICTING", "CRITICAL", "BLOCKS_SPECIFIC_RECORD", "Time interval, Employee, pay-period, or revision chain is structurally inconsistent.", ("timekeeping.employee_id", "timekeeping.period_id", "timekeeping.revision"), "TIMEKEEPING"),
    _rule("DQ-MIGRATION-001", "MIGRATION_IDENTITIES", "UNRESOLVED_IDENTITY", "HIGH", "HISTORICAL_ONLY", "Migration crosswalk or HOLD remains unresolved by its owning workflow.", ("migration.safe_identity", "migration.hold_state"), "MIGRATION"),
)


CATALOG_DIGEST = sha256("|".join(rule.digest for rule in QUALITY_CATALOG).encode()).hexdigest()
