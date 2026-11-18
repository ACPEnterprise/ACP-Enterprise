"""Deterministic migration-factory contracts with no source-write capability."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Final
from uuid import UUID, uuid4


class MigrationFactoryError(ValueError):
    pass


class Domain(StrEnum):
    COMPANY = "company"
    CUSTOMERS = "customers"
    LOCATIONS = "locations"
    VENDORS = "vendors"
    EMPLOYEES = "employees"
    EMPLOYMENT_HISTORY = "employment_history"
    JOBS = "jobs"
    APPOINTMENTS = "appointments"
    DISPATCH = "dispatch"
    ESTIMATES = "estimates"
    INVOICES = "invoices"
    PAYMENTS = "payments"
    PRICE_BOOK = "price_book"
    ITEMS = "items"
    INVENTORY = "inventory"
    CHART_OF_ACCOUNTS = "chart_of_accounts"
    GL = "gl"
    AR = "ar"
    AP = "ap"
    BANKING = "banking"
    CREDIT_CARDS = "credit_cards"
    FIXED_ASSETS = "fixed_assets"
    TAX = "tax"
    TIMEKEEPING = "timekeeping"
    PAYROLL = "payroll"
    PAYROLL_TAX = "payroll_tax"
    DEDUCTIONS_BENEFITS = "deductions_benefits"
    YTD_PAYROLL_STATE = "ytd_payroll_state"


class CoverageState(StrEnum):
    NOT_DISCOVERED = "NOT_DISCOVERED"
    AVAILABLE_API = "AVAILABLE_API"
    AVAILABLE_REPORT = "AVAILABLE_REPORT"
    AVAILABLE_FILE = "AVAILABLE_FILE"
    ACQUIRING = "ACQUIRING"
    ACQUIRED = "ACQUIRED"
    NORMALIZED = "NORMALIZED"
    RECONCILED = "RECONCILED"
    CONFLICTED = "CONFLICTED"
    MISSING_SOURCE = "MISSING_SOURCE"
    CERTIFIED = "CERTIFIED"


class AccessMethod(StrEnum):
    AUTO_API = "AUTO_API"
    AUTO_REPORT = "AUTO_REPORT"
    AUTO_FILE_IMPORT = "AUTO_FILE_IMPORT"
    HUMAN_SOURCE_REQUIRED = "HUMAN_SOURCE_REQUIRED"
    UNAVAILABLE_FROM_PROVIDER = "UNAVAILABLE_FROM_PROVIDER"


class SourceSystem(StrEnum):
    QUICKBOOKS = "quickbooks"
    HOUSECALL_PRO = "housecall_pro"
    OWNER_FILE = "owner_file"


PAYROLL_FIELDS: Final = (
    "employee_identity",
    "employment_dates",
    "compensation",
    "compensation_effective_dates",
    "pay_frequency",
    "time",
    "earnings_pay_types",
    "commissions",
    "reimbursements",
    "w4_tax_elections",
    "fica_configuration",
    "jurisdictions",
    "deductions",
    "benefits",
    "employer_contributions",
    "historical_payroll_runs",
    "historical_paychecks",
    "ytd_wage_bases",
    "ytd_taxes",
    "futa_suta_configuration",
    "payroll_liabilities",
)


_ORDER = {
    CoverageState.NOT_DISCOVERED: 0,
    CoverageState.AVAILABLE_API: 1,
    CoverageState.AVAILABLE_REPORT: 1,
    CoverageState.AVAILABLE_FILE: 1,
    CoverageState.ACQUIRING: 2,
    CoverageState.ACQUIRED: 3,
    CoverageState.NORMALIZED: 4,
    CoverageState.RECONCILED: 5,
    CoverageState.CONFLICTED: 5,
    CoverageState.MISSING_SOURCE: 5,
    CoverageState.CERTIFIED: 6,
}


def canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class SourceDiscovery:
    source: SourceSystem
    connection_identity_digest: str
    company_identity_digest: str
    oauth_scopes: tuple[str, ...]
    api_families: tuple[str, ...]
    report_families: tuple[str, ...]
    limitations: tuple[str, ...]
    subscription_capabilities: tuple[str, ...]
    discovered_at: datetime

    def __post_init__(self) -> None:
        if (
            len(self.connection_identity_digest) != 64
            or len(self.company_identity_digest) != 64
        ):
            raise MigrationFactoryError("source identities must be digest-protected")
        if self.discovered_at.tzinfo is None:
            raise MigrationFactoryError("discovery timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Coverage:
    domain: Domain
    state: CoverageState
    methods: tuple[AccessMethod, ...] = ()
    source_systems: tuple[SourceSystem, ...] = ()
    source_count: int | None = None
    received_count: int = 0
    quarantined_count: int = 0
    rejected_count: int = 0
    explanation: str | None = None

    @property
    def accounted_count(self) -> int:
        return self.received_count + self.quarantined_count + self.rejected_count


@dataclass(frozen=True, slots=True)
class RawSourceEvidence:
    evidence_id: UUID
    company_id: UUID
    source: SourceSystem
    object_type: str
    object_id: str
    source_timestamp: datetime | None
    acquired_at: datetime
    payload_reference: str
    evidence_digest: str
    api_version: str
    authority: str
    batch_identity: str
    page_identity: str


@dataclass(frozen=True, slots=True)
class PageCheckpoint:
    source: SourceSystem
    family: str
    page_identity: str
    high_water_mark: str | None
    received_count: int
    quarantined_count: int
    terminal_page: bool
    response_digest: str


@dataclass(frozen=True, slots=True)
class AuthorityRule:
    rule_id: UUID
    version: int
    domain: Domain
    field_name: str
    source_precedence: tuple[SourceSystem, ...]
    effective_at: datetime
    rule_digest: str


@dataclass(frozen=True, slots=True)
class MigrationException:
    exception_id: UUID
    domain: Domain
    classification: str
    source_record_ids: tuple[UUID, ...]
    actionable_message: str
    resolved: bool = False


@dataclass(frozen=True, slots=True)
class MigrationCertificate:
    certificate_id: UUID
    company_id: UUID
    status: str
    coverage: tuple[Coverage, ...]
    source_hashes: tuple[str, ...]
    transformation_version: str
    conflicts: int
    unresolved_exceptions: int
    zero_silent_drops: bool
    certificate_digest: str
    certified_at: datetime


@dataclass(slots=True)
class MigrationFactory:
    company_id: UUID
    migration_id: UUID = field(default_factory=uuid4)
    discoveries: dict[SourceSystem, SourceDiscovery] = field(default_factory=dict)
    coverage: dict[Domain, Coverage] = field(
        default_factory=lambda: {
            domain: Coverage(domain, CoverageState.NOT_DISCOVERED) for domain in Domain
        }
    )
    vault: dict[tuple[SourceSystem, str, str, str], RawSourceEvidence] = field(
        default_factory=dict
    )
    checkpoints: dict[tuple[SourceSystem, str, str], PageCheckpoint] = field(
        default_factory=dict
    )
    authority_rules: dict[tuple[Domain, str], AuthorityRule] = field(
        default_factory=dict
    )
    crosswalks: dict[tuple[SourceSystem, str], UUID] = field(default_factory=dict)
    exceptions: list[MigrationException] = field(default_factory=list)
    high_water_marks: dict[SourceSystem, str] = field(default_factory=dict)
    normalized_records: dict[UUID, tuple[str, dict[str, object], str]] = field(
        default_factory=dict
    )
    provider_calls: dict[SourceSystem, int] = field(default_factory=dict)
    provider_cost_microunits: dict[SourceSystem, int] = field(default_factory=dict)

    def record_discovery(self, discovery: SourceDiscovery) -> None:
        self.discoveries[discovery.source] = discovery

    def transition(
        self,
        domain: Domain,
        state: CoverageState,
        *,
        methods: tuple[AccessMethod, ...] | None = None,
        sources: tuple[SourceSystem, ...] | None = None,
        source_count: int | None = None,
        received_count: int | None = None,
        quarantined_count: int | None = None,
        rejected_count: int | None = None,
        explanation: str | None = None,
    ) -> Coverage:
        previous = self.coverage[domain]
        if (
            state not in {CoverageState.CONFLICTED, CoverageState.MISSING_SOURCE}
            and _ORDER[state] < _ORDER[previous.state]
        ):
            raise MigrationFactoryError("coverage state cannot move backward")
        candidate = Coverage(
            domain,
            state,
            methods if methods is not None else previous.methods,
            sources if sources is not None else previous.source_systems,
            source_count if source_count is not None else previous.source_count,
            received_count if received_count is not None else previous.received_count,
            quarantined_count
            if quarantined_count is not None
            else previous.quarantined_count,
            rejected_count if rejected_count is not None else previous.rejected_count,
            explanation,
        )
        if (
            candidate.source_count is not None
            and candidate.accounted_count > candidate.source_count
        ):
            raise MigrationFactoryError("accounted records exceed provider count")
        if state in {
            CoverageState.ACQUIRED,
            CoverageState.NORMALIZED,
            CoverageState.RECONCILED,
            CoverageState.CERTIFIED,
        } and (
            candidate.source_count is None
            or candidate.accounted_count != candidate.source_count
        ):
            raise MigrationFactoryError("zero-silent-drop count proof is required")
        self.coverage[domain] = candidate
        return candidate

    def retain_raw(
        self,
        *,
        source: SourceSystem,
        object_type: str,
        object_id: str,
        payload: object,
        payload_reference: str,
        api_version: str,
        authority: str,
        batch_identity: str,
        page_identity: str,
        source_timestamp: datetime | None = None,
        acquired_at: datetime | None = None,
    ) -> RawSourceEvidence:
        digest = canonical_digest(payload)
        key = (source, object_type, object_id, digest)
        existing = self.vault.get(key)
        if existing:
            return existing
        record = RawSourceEvidence(
            uuid4(),
            self.company_id,
            source,
            object_type,
            object_id,
            source_timestamp,
            acquired_at or datetime.now(timezone.utc),
            payload_reference,
            digest,
            api_version,
            authority,
            batch_identity,
            page_identity,
        )
        self.vault[key] = record
        return record

    def checkpoint_page(self, checkpoint: PageCheckpoint) -> PageCheckpoint:
        key = (checkpoint.source, checkpoint.family, checkpoint.page_identity)
        existing = self.checkpoints.get(key)
        if existing and existing != checkpoint:
            raise MigrationFactoryError("page replay content changed")
        self.checkpoints[key] = checkpoint
        if checkpoint.high_water_mark:
            self.high_water_marks[checkpoint.source] = checkpoint.high_water_mark
        return checkpoint

    def prove_pagination(
        self, source: SourceSystem, family: str, expected_count: int
    ) -> bool:
        pages = [
            p
            for p in self.checkpoints.values()
            if p.source == source and p.family == family
        ]
        if (
            not pages
            or sum(p.received_count + p.quarantined_count for p in pages)
            != expected_count
        ):
            return False
        return sum(1 for p in pages if p.terminal_page) == 1

    def bind_crosswalk(
        self, source: SourceSystem, source_id: str, canonical_id: UUID
    ) -> None:
        key = (source, source_id)
        existing = self.crosswalks.get(key)
        if existing and existing != canonical_id:
            self.exceptions.append(
                MigrationException(
                    uuid4(),
                    Domain.EMPLOYEES,
                    "IDENTITY_CONFLICT",
                    (),
                    "Choose the correct employee",
                    False,
                )
            )
            self.coverage[Domain.EMPLOYEES] = Coverage(
                Domain.EMPLOYEES, CoverageState.CONFLICTED
            )
            return
        self.crosswalks[key] = canonical_id

    def normalize(
        self,
        evidence_id: UUID,
        transformation_version: str,
        value: dict[str, object],
    ) -> None:
        if evidence_id not in {record.evidence_id for record in self.vault.values()}:
            raise MigrationFactoryError("normalization requires retained raw evidence")
        candidate = (transformation_version, value, canonical_digest(value))
        existing = self.normalized_records.get(evidence_id)
        if existing and existing != candidate:
            raise MigrationFactoryError("normalized replay changed")
        self.normalized_records[evidence_id] = candidate

    def record_provider_call(
        self, source: SourceSystem, cost_microunits: int = 0
    ) -> None:
        if cost_microunits < 0:
            raise MigrationFactoryError("provider cost cannot be negative")
        self.provider_calls[source] = self.provider_calls.get(source, 0) + 1
        self.provider_cost_microunits[source] = (
            self.provider_cost_microunits.get(source, 0) + cost_microunits
        )

    def record_delta(
        self,
        source: SourceSystem,
        high_water_mark: str,
        *,
        webhook_sequence: int | None = None,
    ) -> None:
        previous = self.high_water_marks.get(source)
        if webhook_sequence is not None and previous and previous.startswith("seq:"):
            prior_sequence = int(previous.removeprefix("seq:"))
            if webhook_sequence != prior_sequence + 1:
                self.exceptions.append(
                    MigrationException(
                        uuid4(),
                        Domain.COMPANY,
                        "WEBHOOK_GAP",
                        (),
                        "Run source backfill reconciliation",
                        False,
                    )
                )
        self.high_water_marks[source] = (
            f"seq:{webhook_sequence}"
            if webhook_sequence is not None
            else high_water_mark
        )

    def add_authority_rule(
        self,
        domain: Domain,
        field_name: str,
        precedence: tuple[SourceSystem, ...],
        version: int,
    ) -> AuthorityRule:
        if not precedence or len(set(precedence)) != len(precedence):
            raise MigrationFactoryError("explicit unique source precedence is required")
        current = self.authority_rules.get((domain, field_name))
        if current and version != current.version + 1:
            raise MigrationFactoryError("authority rule version must be consecutive")
        now = datetime.now(timezone.utc)
        digest = canonical_digest([domain, field_name, precedence, version, now])
        rule = AuthorityRule(
            uuid4(), version, domain, field_name, precedence, now, digest
        )
        self.authority_rules[(domain, field_name)] = rule
        return rule

    def fallback(self, domain: Domain, field_name: str) -> AccessMethod:
        coverage = self.coverage[domain]
        for method in (
            AccessMethod.AUTO_API,
            AccessMethod.AUTO_REPORT,
            AccessMethod.AUTO_FILE_IMPORT,
        ):
            if method in coverage.methods:
                return method
        if coverage.state is CoverageState.MISSING_SOURCE:
            return AccessMethod.UNAVAILABLE_FROM_PROVIDER
        return AccessMethod.HUMAN_SOURCE_REQUIRED

    def dashboard(self) -> dict[str, object]:
        return {
            "migration_id": str(self.migration_id),
            "domains": {d.value: self.coverage[d].state.value for d in Domain},
            "actionable_exceptions": sum(not e.resolved for e in self.exceptions),
            "owner_steps": (
                "Connect QuickBooks",
                "Connect Housecall Pro",
                "Review exceptions",
                "Approve cutover",
            ),
        }

    def certify(self, transformation_version: str) -> MigrationCertificate:
        entries = tuple(self.coverage[d] for d in Domain)
        silent_drop_free = all(
            c.source_count is None or c.accounted_count == c.source_count
            for c in entries
        )
        unresolved = sum(not item.resolved for item in self.exceptions)
        ready = (
            silent_drop_free
            and unresolved == 0
            and all(c.state is CoverageState.CERTIFIED for c in entries)
        )
        now = datetime.now(timezone.utc)
        source_hashes = tuple(
            sorted(item.evidence_digest for item in self.vault.values())
        )
        body = {
            "company_id": str(self.company_id),
            "coverage": [
                (c.domain, c.state, c.source_count, c.accounted_count) for c in entries
            ],
            "source_hashes": source_hashes,
            "transformation_version": transformation_version,
            "unresolved": unresolved,
            "ready": ready,
        }
        return MigrationCertificate(
            uuid4(),
            self.company_id,
            "CERTIFIED" if ready else "BLOCKED",
            entries,
            source_hashes,
            transformation_version,
            sum(c.state is CoverageState.CONFLICTED for c in entries),
            unresolved,
            silent_drop_free,
            canonical_digest(body),
            now,
        )


def import_report_csv(
    content: bytes, required_columns: tuple[str, ...]
) -> tuple[tuple[dict[str, str], ...], tuple[dict[str, object], ...], str]:
    """Normalize a provider export without asking an owner to re-key rows."""
    digest = hashlib.sha256(content).hexdigest()
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    except UnicodeDecodeError as error:
        raise MigrationFactoryError("report must be a UTF-8 CSV export") from error
    headers = tuple(reader.fieldnames or ())
    missing = [column for column in required_columns if column not in headers]
    if missing:
        raise MigrationFactoryError("report is missing columns: " + ",".join(missing))
    accepted: list[dict[str, str]] = []
    quarantined: list[dict[str, object]] = []
    for line, row in enumerate(reader, start=2):
        if any(row.get(column) in {None, ""} for column in required_columns):
            quarantined.append(
                {
                    "line": line,
                    "reason": "required_value_missing",
                    "row_digest": canonical_digest(row),
                }
            )
        else:
            accepted.append(
                {
                    str(key): str(value)
                    for key, value in row.items()
                    if key is not None and value is not None
                }
            )
    return tuple(accepted), tuple(quarantined), digest


def all_county_current_assessment() -> dict[str, object]:
    """Repository-proven current access only; never probes QBO or opens Payroll."""
    accounting_families = (
        "company_info",
        "account",
        "customer",
        "vendor",
        "invoice",
        "payment",
        "bill",
        "bill_payment",
        "purchase",
        "deposit",
        "transfer",
        "journal_entry",
        "tax_payment",
        "tax_agency",
        "item",
        "employee",
        "time_activity",
    )
    return {
        "oauth_scopes": ("com.intuit.quickbooks.accounting",),
        "accounting": "AVAILABLE",
        "accounting_families": accounting_families,
        "payroll_compensation": "ADDITIONAL SCOPE REQUIRED",
        "employee_workforce": "PARTNER APPROVAL REQUIRED",
        "sensitive_payroll": "ADDITIONAL AGREEMENT REQUIRED",
        "time": "AVAILABLE",
        "time_qualification": "Accounting TimeActivity only; not QuickBooks Time/Workforce coverage",
        "answer_key_opened": False,
        "source_writes": False,
    }
