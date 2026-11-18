"""Provider-independent staging contracts consumed by reconciliation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from .domain import ProviderKey


class NormalizedKind(StrEnum):
    COMPANY = "company"
    CUSTOMER = "customer"
    LOCATION = "location"
    EMPLOYEE = "employee"
    EMPLOYMENT_HISTORY = "employment_history"
    TECHNICIAN = "technician"
    JOB = "job"
    APPOINTMENT = "appointment"
    ASSIGNMENT = "assignment"
    DISPATCH_EVENT = "dispatch_event"
    ESTIMATE = "estimate"
    PRICE_BOOK_SERVICE = "price_book_service"
    INVOICE = "invoice"
    PAYMENT = "payment"
    VENDOR = "vendor"
    PURCHASE = "purchase"
    INVENTORY_ITEM = "inventory_item"
    ACCOUNT = "account"
    JOURNAL = "journal"
    TIME_ENTRY = "time_entry"
    PAYROLL_EMPLOYEE = "payroll_employee"
    COMPENSATION = "compensation"
    PAYROLL_CONFIGURATION = "payroll_configuration"
    PAYROLL_RUN = "payroll_run"
    PAYROLL_RESULT = "payroll_result"
    DEDUCTION = "deduction"
    BENEFIT = "benefit"
    TAX_CONFIGURATION = "tax_configuration"
    PAYROLL_YTD_STATE = "payroll_ytd_state"


@dataclass(frozen=True, slots=True)
class SourceLineage:
    provider: ProviderKey
    evidence_id: UUID
    source_object_id: str
    transformation_version: str
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class NormalizedRecord:
    kind: NormalizedKind
    source_identity: str
    effective_at: datetime | None
    fields: Mapping[str, object]
    lineage: SourceLineage


NORMALIZED_CONTRACTS = frozenset(NormalizedKind)
