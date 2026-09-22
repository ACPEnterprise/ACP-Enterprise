"""Fail-closed QBO source evidence planning for Employee Payroll setup.

This module creates no Payroll authority.  It classifies sealed source facts and
produces draft-import/review instructions for an authorized importer to apply through
the existing Payroll setup services.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from .contracts import canonical_digest


class SourceClassification(StrEnum):
    AUTHORITATIVE_SOURCE_AVAILABLE = "AUTHORITATIVE_SOURCE_AVAILABLE"
    PARTIAL_SOURCE_EVIDENCE = "PARTIAL_SOURCE_EVIDENCE"
    ABSENT = "ABSENT"
    CONFLICTING = "CONFLICTING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ReconciliationDisposition(StrEnum):
    RESOLVED_FROM_QBO = "RESOLVED_FROM_QBO"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    OWNER_INPUT_REQUIRED = "OWNER_INPUT_REQUIRED"
    ACCOUNTANT_INPUT_REQUIRED = "ACCOUNTANT_INPUT_REQUIRED"
    SOURCE_MISSING = "SOURCE_MISSING"
    CONFLICTING = "CONFLICTING"
    HOLD_FOR_OWNER_REVIEW = "HOLD_FOR_OWNER_REVIEW"


class ExistingAuthorityState(StrEnum):
    MISSING = "MISSING"
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"


NEVER_INFER_FIELDS: Final = frozenset(
    {
        "w4_filing_status",
        "w4_step_2",
        "w4_step_3",
        "w4_step_4a",
        "w4_step_4b",
        "w4_step_4c",
    }
)

PAYROLL_INPUT_FIELDS: Final = (
    "employee_identity_crosswalk",
    "compensation_basis",
    "compensation_rate",
    "pay_frequency",
    "compensation_effective_history",
    "federal_withholding_ytd",
    "social_security_wages_ytd",
    "social_security_tax_ytd",
    "medicare_wages_ytd",
    "medicare_tax_ytd",
    "additional_medicare_evidence",
    "deduction_history",
    "deduction_applicability",
    "prior_payroll_coverage",
    "payroll_period_history",
    "work_jurisdiction",
    "residence_jurisdiction",
    "state_local_withholding_applicability",
    "w4_filing_status",
    "w4_step_2",
    "w4_step_3",
    "w4_step_4a",
    "w4_step_4b",
    "w4_step_4c",
)

_ACCOUNTING_CATALOG_REVIEW_FIELDS: Final = frozenset(
    {
        "compensation_basis",
        "compensation_rate",
        "compensation_effective_history",
        "additional_medicare_evidence",
        "deduction_history",
        "deduction_applicability",
        "prior_payroll_coverage",
        "payroll_period_history",
        "work_jurisdiction",
        "residence_jurisdiction",
        "state_local_withholding_applicability",
    }
)


@dataclass(frozen=True, slots=True)
class SourceEvidence:
    field: str
    classification: SourceClassification
    source_record_ids: tuple[str, ...]
    evidence_digest: str | None
    effective_period: str | None
    value_digest: str | None = None
    explicit_zero: bool = False
    provider_authoritative: bool = False


@dataclass(frozen=True, slots=True)
class EmployeeCrosswalk:
    company_id: str
    realm_company_identity: str
    qbo_employee_id: str
    acp_employee_id: str
    evidence_digest: str
    approved: bool


@dataclass(frozen=True, slots=True)
class ExistingPayrollAuthority:
    field: str
    state: ExistingAuthorityState
    evidence_digest: str | None
    value_digest: str | None


@dataclass(frozen=True, slots=True)
class FieldReconciliation:
    field: str
    source_classification: SourceClassification
    disposition: ReconciliationDisposition
    importable_as_draft: bool
    preserve_existing: bool
    source_record_ids: tuple[str, ...]
    source_evidence_digest: str | None


@dataclass(frozen=True, slots=True)
class EmployeeReconciliationPacket:
    contract_version: str
    company_id: str
    realm_company_identity: str
    qbo_employee_id: str | None
    acp_employee_id: str | None
    crosswalk_disposition: ReconciliationDisposition
    fields: tuple[FieldReconciliation, ...]
    packet_digest: str


def classify_accounting_catalog(
    *, entity_counts: dict[str, int]
) -> tuple[SourceEvidence, ...]:
    """Classify capability only; catalog presence never proves a Payroll value."""
    has_employee = entity_counts.get("employee", 0) > 0
    has_time = entity_counts.get("time_activity", 0) > 0
    has_transactions = any(
        entity_counts.get(key, 0) > 0
        for key in ("journal_entry", "tax_payment", "account")
    )
    result: list[SourceEvidence] = []
    for field in PAYROLL_INPUT_FIELDS:
        partial = (
            field == "employee_identity_crosswalk"
            and has_employee
            or field in _ACCOUNTING_CATALOG_REVIEW_FIELDS
            and (has_employee or has_time or has_transactions)
        )
        result.append(
            SourceEvidence(
                field,
                SourceClassification.PARTIAL_SOURCE_EVIDENCE
                if partial
                else SourceClassification.ABSENT,
                (),
                None,
                None,
            )
        )
    return tuple(result)


def reconcile_employee(
    *,
    company_id: str,
    realm_company_identity: str,
    qbo_employee_id: str | None,
    crosswalks: tuple[EmployeeCrosswalk, ...],
    source: tuple[SourceEvidence, ...],
    existing: tuple[ExistingPayrollAuthority, ...],
) -> EmployeeReconciliationPacket:
    matching = tuple(
        item
        for item in crosswalks
        if item.approved
        and item.company_id == company_id
        and item.realm_company_identity == realm_company_identity
        and item.qbo_employee_id == qbo_employee_id
    )
    targets = {item.acp_employee_id for item in matching}
    if qbo_employee_id is None or not matching:
        crosswalk_disposition = ReconciliationDisposition.SOURCE_MISSING
        acp_employee_id = None
    elif len(targets) != 1:
        crosswalk_disposition = ReconciliationDisposition.HOLD_FOR_OWNER_REVIEW
        acp_employee_id = None
    else:
        crosswalk_disposition = ReconciliationDisposition.RESOLVED_FROM_QBO
        acp_employee_id = next(iter(targets))

    source_by_field = {item.field: item for item in source}
    existing_by_field = {item.field: item for item in existing}
    fields = tuple(
        _reconcile_field(
            field=field,
            source=source_by_field.get(field),
            existing=existing_by_field.get(field),
            crosswalk_ready=crosswalk_disposition
            is ReconciliationDisposition.RESOLVED_FROM_QBO,
        )
        for field in PAYROLL_INPUT_FIELDS
    )
    body = {
        "contract_version": "payroll.qbo-employee-input-reconciliation.v1",
        "company_id": company_id,
        "realm_company_identity": realm_company_identity,
        "qbo_employee_id": qbo_employee_id,
        "acp_employee_id": acp_employee_id,
        "crosswalk_disposition": crosswalk_disposition.value,
        "fields": tuple(
            (
                item.field,
                item.source_classification.value,
                item.disposition.value,
                item.importable_as_draft,
                item.preserve_existing,
                item.source_evidence_digest,
            )
            for item in fields
        ),
    }
    return EmployeeReconciliationPacket(
        str(body["contract_version"]),
        company_id,
        realm_company_identity,
        qbo_employee_id,
        acp_employee_id,
        crosswalk_disposition,
        fields,
        canonical_digest(body),
    )


def _reconcile_field(
    *,
    field: str,
    source: SourceEvidence | None,
    existing: ExistingPayrollAuthority | None,
    crosswalk_ready: bool,
) -> FieldReconciliation:
    source = source or SourceEvidence(
        field, SourceClassification.ABSENT, (), None, None
    )
    approved = (
        existing is not None and existing.state is ExistingAuthorityState.APPROVED
    )
    same_value = bool(
        approved
        and existing
        and existing.value_digest
        and source.value_digest
        and existing.value_digest == source.value_digest
    )
    authoritative = bool(
        crosswalk_ready
        and field not in NEVER_INFER_FIELDS
        and source.classification is SourceClassification.AUTHORITATIVE_SOURCE_AVAILABLE
        and source.provider_authoritative
        and source.evidence_digest
        and source.value_digest
        and (not source.explicit_zero or source.provider_authoritative)
    )
    if approved:
        disposition = (
            ReconciliationDisposition.RESOLVED_FROM_QBO
            if authoritative and same_value
            else ReconciliationDisposition.CONFLICTING
            if authoritative and not same_value
            else ReconciliationDisposition.OWNER_INPUT_REQUIRED
        )
        return FieldReconciliation(
            field,
            source.classification,
            disposition,
            False,
            True,
            source.source_record_ids,
            source.evidence_digest,
        )
    if field in NEVER_INFER_FIELDS:
        disposition = ReconciliationDisposition.OWNER_INPUT_REQUIRED
    elif authoritative:
        disposition = ReconciliationDisposition.RESOLVED_FROM_QBO
    elif source.classification in {
        SourceClassification.PARTIAL_SOURCE_EVIDENCE,
        SourceClassification.CONFLICTING,
    }:
        disposition = ReconciliationDisposition.REVIEW_REQUIRED
    elif source.classification is SourceClassification.ABSENT:
        disposition = ReconciliationDisposition.SOURCE_MISSING
    else:
        disposition = ReconciliationDisposition.ACCOUNTANT_INPUT_REQUIRED
    return FieldReconciliation(
        field,
        source.classification,
        disposition,
        authoritative,
        False,
        source.source_record_ids,
        source.evidence_digest,
    )
