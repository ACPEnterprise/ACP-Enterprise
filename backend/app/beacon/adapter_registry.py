"""Truthful cross-domain Beacon adapter admission registry.

This module records consumption seams only.  A registered contract is not an
active signal evaluator until ``status`` is ``ACTIVE``.
"""

from dataclasses import dataclass
from enum import StrEnum


class AdapterStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ADAPTER_GATED = "ADAPTER_GATED"
    SOURCE_GATED = "SOURCE_GATED"
    POLICY_GATED = "POLICY_GATED"


class AttentionResponsibility(StrEnum):
    OWNER = "OWNER"
    OFFICE = "OFFICE"
    TECHNICIAN = "TECHNICIAN"
    EMPLOYEE = "EMPLOYEE"
    ACCOUNTANT = "ACCOUNTANT"
    PROVIDER = "PROVIDER"
    ENGINEERING = "ENGINEERING"
    SYSTEM = "SYSTEM"
    SOURCE = "SOURCE"


@dataclass(frozen=True)
class CrossDomainAdapterRegistration:
    family: str
    source_authority: str
    contract: str
    status: AdapterStatus
    responsibility: AttentionResponsibility
    clearing_condition: str
    limitation: str | None = None


CROSS_DOMAIN_ADAPTER_REGISTRY = (
    CrossDomainAdapterRegistration(
        "scheduling_dispatch",
        "Scheduling and Dispatch",
        "BeaconSnapshot.overdue_appointments/v1",
        AdapterStatus.ACTIVE,
        AttentionResponsibility.OFFICE,
        "Record the authoritative appointment or dispatch outcome.",
    ),
    CrossDomainAdapterRegistration(
        "customer_jobs",
        "Jobs",
        "BeaconSnapshot.paused_jobs/v1",
        AdapterStatus.ACTIVE,
        AttentionResponsibility.OFFICE,
        "Record the authoritative next Job lifecycle action.",
    ),
    CrossDomainAdapterRegistration(
        "invoice_collections",
        "Invoices and Accounts Receivable",
        "BeaconSnapshot.past_due_invoices/v1",
        AdapterStatus.ACTIVE,
        AttentionResponsibility.OFFICE,
        "Resolve the authoritative Invoice or payment-application condition.",
    ),
    CrossDomainAdapterRegistration(
        "migration_source_completeness",
        "Operational Migration",
        "migration-readiness-review + SOURCE.4 immutable evidence",
        AdapterStatus.ADAPTER_GATED,
        AttentionResponsibility.SOURCE,
        "Admit or explicitly disposition the source evidence in Migration.",
        "Beacon must consume exact Migration classifications; it may not infer bindings.",
    ),
    CrossDomainAdapterRegistration(
        "workforce",
        "Workforce",
        "RealRosterReadiness + FieldReadinessResponse",
        AdapterStatus.ADAPTER_GATED,
        AttentionResponsibility.OFFICE,
        "Complete the identified Workforce readiness requirement.",
        "No employee ranking or inferred identity is permitted.",
    ),
    CrossDomainAdapterRegistration(
        "timekeeping",
        "Timekeeping",
        "authoritative worked intervals and correction history",
        AdapterStatus.ADAPTER_GATED,
        AttentionResponsibility.EMPLOYEE,
        "Resolve the authoritative open punch or Timecard exception.",
        "A schedule alone does not establish that an Employee should be clocked.",
    ),
    CrossDomainAdapterRegistration(
        "payroll_readiness",
        "Payroll",
        "Payroll run-member blocker codes and cutover readiness",
        AdapterStatus.ADAPTER_GATED,
        AttentionResponsibility.ACCOUNTANT,
        "Satisfy the named Payroll readiness blocker through Payroll authority.",
        "Protected compensation and tax values are outside Beacon evidence.",
    ),
    CrossDomainAdapterRegistration(
        "accounting_controls",
        "Accounting and accepted QBO evidence",
        "Accounting reports + financial reconciliation readiness/v1",
        AdapterStatus.ADAPTER_GATED,
        AttentionResponsibility.ACCOUNTANT,
        "Complete the named reconciliation, certification, or posting prerequisite.",
        "Source-backed QBO evidence is not ACP Accounting truth.",
    ),
    CrossDomainAdapterRegistration(
        "economics_luminary",
        "Business Economics and Luminary",
        "immutable economics result + Luminary finding reference",
        AdapterStatus.ADAPTER_GATED,
        AttentionResponsibility.OWNER,
        "Resolve the evidence or policy gap identified by Economics.",
        "Beacon does not recalculate Economics or create recommendations.",
    ),
    CrossDomainAdapterRegistration(
        "price_book",
        "Price Book",
        "canonical item/version and activation-readiness authority",
        AdapterStatus.POLICY_GATED,
        AttentionResponsibility.OWNER,
        "Complete the configured review requirement and authorize it in Price Book.",
        "No accepted stale-review or below-cost threshold is configured.",
    ),
    CrossDomainAdapterRegistration(
        "estimates",
        "Estimates",
        "immutable Estimate revision and lifecycle authority",
        AdapterStatus.ADAPTER_GATED,
        AttentionResponsibility.OFFICE,
        "Record the authoritative Estimate lifecycle outcome.",
        "Follow-up cadence requires accepted policy and never implies Customer contact.",
    ),
    CrossDomainAdapterRegistration(
        "inventory_purchasing",
        "Inventory and Purchasing",
        "inventory availability, valuation, demand, PO, and receipt evidence",
        AdapterStatus.POLICY_GATED,
        AttentionResponsibility.OFFICE,
        "Resolve the authoritative availability, valuation, or purchasing condition.",
        "Certified reorder and overdue thresholds are not universally configured.",
    ),
    CrossDomainAdapterRegistration(
        "capacity",
        "Scheduling, Dispatch, and Workforce",
        "accepted assignment, availability, and schedule-conflict evidence",
        AdapterStatus.ADAPTER_GATED,
        AttentionResponsibility.OFFICE,
        "Assign eligible capacity or resolve the authoritative scheduling conflict.",
        "No employee ranking, hiring recommendation, or autonomous reassignment.",
    ),
)


if len({item.family for item in CROSS_DOMAIN_ADAPTER_REGISTRY}) != len(
    CROSS_DOMAIN_ADAPTER_REGISTRY
):
    raise RuntimeError("Beacon adapter families must be unique.")
