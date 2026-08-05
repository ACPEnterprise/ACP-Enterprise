"""Read-only, provider-neutral acquisition contracts for Economics."""

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol, TypeVar
from uuid import UUID, uuid5

ACQUISITION_NAMESPACE = UUID("8923e1e8-6f8d-54fb-923a-25ed4fc2dd92")


class AcquisitionDomain(StrEnum):
    JOBS = "jobs"
    DISPATCH = "dispatch"
    PRICE_BOOK = "price_book"
    CUSTOMERS = "customers"


class AcquisitionKind(StrEnum):
    JOB_CONTEXT = "job_context"
    DISPATCH_ACTIVITY = "dispatch_activity"
    PRICE_BOOK_LINEAGE = "price_book_lineage"
    CUSTOMER_CONTEXT = "customer_context"


class AcquisitionState(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


Scalar = str | int | bool


class AcquisitionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AcquisitionRequest:
    company_id: UUID
    authorized_branch_ids: frozenset[UUID]
    period_start: date
    period_end: date

    def __post_init__(self) -> None:
        if not self.authorized_branch_ids:
            raise ValueError("acquisition requires an authorized branch")
        if self.period_end < self.period_start:
            raise ValueError("acquisition period is invalid")


@dataclass(frozen=True, slots=True)
class SourceEvidenceContract:
    source_system: str
    record_type: str
    record_id: str
    source_version: str
    content_digest: str
    observed_at: datetime
    business_event_id: UUID | None = None

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (
                self.source_system,
                self.record_type,
                self.record_id,
                self.source_version,
            )
        ):
            raise ValueError("source evidence identity is required")
        if len(self.content_digest) != 64 or any(
            character not in "0123456789abcdefABCDEF"
            for character in self.content_digest
        ):
            raise ValueError("source evidence digest must be SHA-256")


@dataclass(frozen=True, slots=True)
class AcquiredAttribute:
    name: str
    value: Scalar

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("acquired attribute name is required")


@dataclass(frozen=True, slots=True)
class AcquiredOperationalFact:
    fact_id: UUID
    domain: AcquisitionDomain
    kind: AcquisitionKind
    company_id: UUID
    branch_id: UUID
    subject_id: UUID
    effective_at: datetime
    attributes: tuple[AcquiredAttribute, ...]
    missing_fields: tuple[str, ...]
    state: AcquisitionState
    evidence: SourceEvidenceContract

    def __post_init__(self) -> None:
        if (
            tuple(sorted(self.attributes, key=lambda item: item.name))
            != self.attributes
        ):
            raise ValueError("acquired attributes must be canonically ordered")
        if len({item.name for item in self.attributes}) != len(self.attributes):
            raise ValueError("acquired attribute names must be unique")
        if tuple(sorted(set(self.missing_fields))) != self.missing_fields:
            raise ValueError("missing fields must be unique and ordered")
        if self.state is AcquisitionState.COMPLETE and self.missing_fields:
            raise ValueError("complete acquisition cannot name missing fields")
        if self.state is AcquisitionState.INCOMPLETE and not self.missing_fields:
            raise ValueError("incomplete acquisition must name missing fields")


@dataclass(frozen=True, slots=True)
class AcquisitionBatch:
    batch_id: UUID
    domain: AcquisitionDomain
    facts: tuple[AcquiredOperationalFact, ...]
    evidence_digest: str

    def __post_init__(self) -> None:
        if tuple(sorted(self.facts, key=lambda item: str(item.fact_id))) != self.facts:
            raise ValueError("acquisition facts must be canonically ordered")
        if any(item.domain is not self.domain for item in self.facts):
            raise ValueError("acquisition batch cannot mix source domains")


@dataclass(frozen=True, slots=True)
class JobSourceSnapshot:
    id: UUID
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID
    job_number: str
    status: str
    job_type_code: str | None
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime
    concurrency_version: int
    evidence: SourceEvidenceContract


@dataclass(frozen=True, slots=True)
class DispatchSourceSnapshot:
    id: UUID
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    job_id: UUID | None
    technician_id: UUID | None
    status: str
    scheduled_start_at: datetime | None
    scheduled_end_at: datetime | None
    actual_start_at: datetime | None
    actual_end_at: datetime | None
    updated_at: datetime
    concurrency_version: int
    evidence: SourceEvidenceContract


@dataclass(frozen=True, slots=True)
class PriceBookSourceSnapshot:
    id: UUID
    company_id: UUID
    branch_id: UUID
    job_id: UUID | None
    estimate_id: UUID | None
    selected_option_id: UUID | None
    item_code: str
    item_version: int
    expected_revenue_minor: int | None
    expected_labor_minor: int | None
    expected_materials_minor: int | None
    currency: str
    effective_at: datetime
    evidence: SourceEvidenceContract


@dataclass(frozen=True, slots=True)
class CustomerSourceSnapshot:
    id: UUID
    company_id: UUID
    branch_id: UUID
    customer_number: str
    customer_type: str
    status: str
    marketing_source: str | None
    service_location_id: UUID | None
    updated_at: datetime
    evidence: SourceEvidenceContract


SourceSnapshot = (
    JobSourceSnapshot
    | DispatchSourceSnapshot
    | PriceBookSourceSnapshot
    | CustomerSourceSnapshot
)
SnapshotT_contra = TypeVar("SnapshotT_contra", bound=SourceSnapshot, contravariant=True)


class AcquisitionAdapter(Protocol[SnapshotT_contra]):
    def acquire(
        self, request: AcquisitionRequest, sources: tuple[SnapshotT_contra, ...]
    ) -> AcquisitionBatch: ...


class _ReadOnlyAdapter:
    domain: AcquisitionDomain
    kind: AcquisitionKind

    @staticmethod
    def _validate_scope(
        request: AcquisitionRequest, company_id: UUID, branch_id: UUID
    ) -> None:
        if company_id != request.company_id or branch_id not in (
            request.authorized_branch_ids
        ):
            raise AcquisitionError("source is outside the authorized acquisition scope")

    @staticmethod
    def _validate_period(request: AcquisitionRequest, effective_at: datetime) -> None:
        if not request.period_start <= effective_at.date() <= request.period_end:
            raise AcquisitionError("source is outside the acquisition period")

    def _batch(self, facts: tuple[AcquiredOperationalFact, ...]) -> AcquisitionBatch:
        ordered = tuple(sorted(facts, key=lambda item: str(item.fact_id)))
        manifest = [
            [
                str(item.fact_id),
                item.evidence.source_system,
                item.evidence.record_type,
                item.evidence.record_id,
                item.evidence.source_version,
                item.evidence.content_digest,
                [[attribute.name, attribute.value] for attribute in item.attributes],
                list(item.missing_fields),
            ]
            for item in ordered
        ]
        digest = hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return AcquisitionBatch(
            batch_id=uuid5(ACQUISITION_NAMESPACE, f"{self.domain.value}:{digest}"),
            domain=self.domain,
            facts=ordered,
            evidence_digest=digest,
        )

    def _fact(
        self,
        *,
        source_id: UUID,
        company_id: UUID,
        branch_id: UUID,
        effective_at: datetime,
        attributes: dict[str, Scalar],
        missing: tuple[str, ...],
        evidence: SourceEvidenceContract,
    ) -> AcquiredOperationalFact:
        missing_fields = tuple(sorted(set(missing)))
        values = tuple(
            AcquiredAttribute(name=name, value=value)
            for name, value in sorted(attributes.items())
        )
        identity = hashlib.sha256(
            json.dumps(
                {
                    "domain": self.domain.value,
                    "source_id": str(source_id),
                    "version": evidence.source_version,
                    "digest": evidence.content_digest,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        return AcquiredOperationalFact(
            fact_id=uuid5(ACQUISITION_NAMESPACE, identity),
            domain=self.domain,
            kind=self.kind,
            company_id=company_id,
            branch_id=branch_id,
            subject_id=source_id,
            effective_at=effective_at,
            attributes=values,
            missing_fields=missing_fields,
            state=(
                AcquisitionState.INCOMPLETE
                if missing_fields
                else AcquisitionState.COMPLETE
            ),
            evidence=evidence,
        )


class JobsAcquisitionAdapter(_ReadOnlyAdapter):
    domain = AcquisitionDomain.JOBS
    kind = AcquisitionKind.JOB_CONTEXT

    def acquire(
        self, request: AcquisitionRequest, sources: tuple[JobSourceSnapshot, ...]
    ) -> AcquisitionBatch:
        facts = []
        for source in sources:
            self._validate_scope(request, source.company_id, source.branch_id)
            self._validate_period(request, source.updated_at)
            missing = ("job_type_code",) if source.job_type_code is None else ()
            attributes: dict[str, Scalar] = {
                "customer_id": str(source.customer_id),
                "job_number": source.job_number,
                "service_location_id": str(source.service_location_id),
                "status": source.status,
                "version": source.concurrency_version,
            }
            if source.job_type_code is not None:
                attributes["job_type_code"] = source.job_type_code
            facts.append(
                self._fact(
                    source_id=source.id,
                    company_id=source.company_id,
                    branch_id=source.branch_id,
                    effective_at=source.updated_at,
                    attributes=attributes,
                    missing=missing,
                    evidence=source.evidence,
                )
            )
        return self._batch(tuple(facts))


class DispatchAcquisitionAdapter(_ReadOnlyAdapter):
    domain = AcquisitionDomain.DISPATCH
    kind = AcquisitionKind.DISPATCH_ACTIVITY

    def acquire(
        self, request: AcquisitionRequest, sources: tuple[DispatchSourceSnapshot, ...]
    ) -> AcquisitionBatch:
        facts = []
        for source in sources:
            self._validate_scope(request, source.company_id, source.branch_id)
            self._validate_period(request, source.updated_at)
            optional = {
                "job_id": source.job_id,
                "technician_id": source.technician_id,
                "actual_start_at": source.actual_start_at,
                "actual_end_at": source.actual_end_at,
            }
            missing = tuple(name for name, value in optional.items() if value is None)
            attributes: dict[str, Scalar] = {
                "customer_id": str(source.customer_id),
                "status": source.status,
                "version": source.concurrency_version,
            }
            attributes.update(
                {
                    name: value.isoformat()
                    if isinstance(value, datetime)
                    else str(value)
                    for name, value in optional.items()
                    if value is not None
                }
            )
            facts.append(
                self._fact(
                    source_id=source.id,
                    company_id=source.company_id,
                    branch_id=source.branch_id,
                    effective_at=source.updated_at,
                    attributes=attributes,
                    missing=missing,
                    evidence=source.evidence,
                )
            )
        return self._batch(tuple(facts))


class PriceBookAcquisitionAdapter(_ReadOnlyAdapter):
    domain = AcquisitionDomain.PRICE_BOOK
    kind = AcquisitionKind.PRICE_BOOK_LINEAGE

    def acquire(
        self, request: AcquisitionRequest, sources: tuple[PriceBookSourceSnapshot, ...]
    ) -> AcquisitionBatch:
        facts = []
        for source in sources:
            self._validate_scope(request, source.company_id, source.branch_id)
            self._validate_period(request, source.effective_at)
            optional = {
                "job_id": source.job_id,
                "estimate_id": source.estimate_id,
                "selected_option_id": source.selected_option_id,
                "expected_revenue_minor": source.expected_revenue_minor,
                "expected_labor_minor": source.expected_labor_minor,
                "expected_materials_minor": source.expected_materials_minor,
            }
            missing = tuple(name for name, value in optional.items() if value is None)
            attributes: dict[str, Scalar] = {
                "currency": source.currency.upper(),
                "item_code": source.item_code,
                "item_version": source.item_version,
            }
            attributes.update(
                {
                    name: str(value) if isinstance(value, UUID) else value
                    for name, value in optional.items()
                    if value is not None
                }
            )
            facts.append(
                self._fact(
                    source_id=source.id,
                    company_id=source.company_id,
                    branch_id=source.branch_id,
                    effective_at=source.effective_at,
                    attributes=attributes,
                    missing=missing,
                    evidence=source.evidence,
                )
            )
        return self._batch(tuple(facts))


class CustomersAcquisitionAdapter(_ReadOnlyAdapter):
    domain = AcquisitionDomain.CUSTOMERS
    kind = AcquisitionKind.CUSTOMER_CONTEXT

    def acquire(
        self, request: AcquisitionRequest, sources: tuple[CustomerSourceSnapshot, ...]
    ) -> AcquisitionBatch:
        facts = []
        for source in sources:
            self._validate_scope(request, source.company_id, source.branch_id)
            self._validate_period(request, source.updated_at)
            optional = {
                "marketing_source": source.marketing_source,
                "service_location_id": source.service_location_id,
            }
            missing = tuple(name for name, value in optional.items() if value is None)
            attributes: dict[str, Scalar] = {
                "customer_number": source.customer_number,
                "customer_type": source.customer_type,
                "status": source.status,
            }
            attributes.update(
                {
                    name: str(value)
                    for name, value in optional.items()
                    if value is not None
                }
            )
            facts.append(
                self._fact(
                    source_id=source.id,
                    company_id=source.company_id,
                    branch_id=source.branch_id,
                    effective_at=source.updated_at,
                    attributes=attributes,
                    missing=missing,
                    evidence=source.evidence,
                )
            )
        return self._batch(tuple(facts))
