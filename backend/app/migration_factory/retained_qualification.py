"""Repository-verifiable retained All County qualification; performs no source I/O."""

from __future__ import annotations

from dataclasses import dataclass

from .certification import CertificationStatus


@dataclass(frozen=True, slots=True)
class RetainedDomainQualification:
    domain: str
    record_count: int | None
    acquisition: str
    pagination: str
    reconciliation: str
    status: CertificationStatus


HCP_ALL_COUNTY_RETAINED = (
    RetainedDomainQualification(
        "customers",
        5253,
        "COMPLETE",
        "CHECKSUM_PROVEN",
        "43 native-ID omissions recovered",
        CertificationStatus.QUALIFIED_LIVE,
    ),
    RetainedDomainQualification(
        "employees",
        7,
        "COMPLETE",
        "CHECKSUM_PROVEN",
        "owner crosswalk remains",
        CertificationStatus.QUALIFIED_LIVE,
    ),
    RetainedDomainQualification(
        "jobs",
        5801,
        "COMPLETE",
        "CHECKSUM_PROVEN",
        "4816 controls matched; 985 classified API-only",
        CertificationStatus.QUALIFIED_LIVE,
    ),
    RetainedDomainQualification(
        "estimates",
        1307,
        "COMPLETE",
        "CHECKSUM_PROVEN",
        "1304 corroborated; 2 partial; 1 control-export missing",
        CertificationStatus.QUALIFIED_LIVE,
    ),
    RetainedDomainQualification(
        "invoices",
        5756,
        "COMPLETE",
        "CHECKSUM_PROVEN",
        "source acquisition complete",
        CertificationStatus.QUALIFIED_LIVE,
    ),
    RetainedDomainQualification(
        "payments",
        4308,
        "COMPLETE_EVIDENCE",
        "PARENT_PAGE_PROVEN",
        "application tie-out partial",
        CertificationStatus.PARTIAL,
    ),
    RetainedDomainQualification(
        "refunds",
        28,
        "COMPLETE_EVIDENCE",
        "PARENT_PAGE_PROVEN",
        "12 native refund IDs",
        CertificationStatus.PARTIAL,
    ),
    RetainedDomainQualification(
        "appointments",
        3219,
        "PARTIAL",
        "3950 relationship requests accounted",
        "920 provider HTTP 400 responses",
        CertificationStatus.PARTIAL,
    ),
    RetainedDomainQualification(
        "attachments",
        None,
        "DEFERRED",
        "NOT_AVAILABLE",
        "provider availability unresolved",
        CertificationStatus.BLOCKED_PROVIDER,
    ),
)


QBO_ACCOUNTING_FAMILIES = (
    "company",
    "accounts",
    "customers",
    "vendors",
    "items",
    "invoices",
    "payments",
    "bills",
    "bill_payments",
    "purchases",
    "deposits",
    "transfers",
    "journals",
    "tax_resources",
    "generic_employee",
    "time_activity",
)

QBO_ALL_COUNTY_RETAINED = tuple(
    RetainedDomainQualification(
        domain,
        None,
        "AUTHORIZATION_ONLY_NO_RETAINED_COMPLETE_ACQUISITION",
        "NOT_PROVEN",
        "live acquisition required",
        CertificationStatus.IMPLEMENTED_UNQUALIFIED,
    )
    for domain in QBO_ACCOUNTING_FAMILIES
)

QBO_PAYROLL_RETAINED = tuple(
    RetainedDomainQualification(
        domain,
        None,
        "SCOPE_NOT_GRANTED",
        "NOT_APPLICABLE",
        "provider approval/access required",
        CertificationStatus.BLOCKED_PROVIDER,
    )
    for domain in (
        "payroll_compensation",
        "workforce_employee",
        "benefits_deductions",
        "payroll_runs_payslips",
        "tax_withholding",
        "ytd_payroll_state",
    )
)
