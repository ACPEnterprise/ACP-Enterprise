import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.customer_migration.adapter_import_policy import (
    CustomerAdapterImportPolicy,
    customer_adapter_import_policy,
)
from app.customer_migration.adapter_import_repository import (
    CustomerAdapterImportRepository,
)
from app.customer_migration.models import (
    CustomerMigrationException,
    CustomerMigrationProgress,
    CustomerMigrationRun,
    CustomerSourceIdentity,
    utc_now,
)
from app.customers.schemas import (
    ContactCreate,
    CustomerCreate,
    ServiceLocationCreate,
)
from app.customers.service import CustomerService
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import AuthorizationContext

SHA256 = re.compile(r"^[0-9a-f]{64}$")
REVIEW_VERSION = "customer-adapter-review/v1"
BOUNDARY_VERSION = "customer-pilot-boundary/v1"


class AdapterRecord(Protocol):
    @property
    def row_number(self) -> int: ...

    @property
    def source_id(self) -> str: ...

    @property
    def schema_version(self) -> str: ...

    @property
    def source_row_sha256(self) -> str: ...

    @property
    def customer(self) -> CustomerCreate: ...

    @property
    def contact(self) -> ContactCreate | None: ...

    @property
    def service_locations(self) -> tuple[ServiceLocationCreate, ...]: ...

    @property
    def billing_address(self) -> ServiceLocationCreate | None: ...


class AdapterRejection(Protocol):
    @property
    def disposition(self) -> str: ...

    @property
    def source_id_sha256(self) -> str | None: ...


class AdapterChildException(Protocol):
    @property
    def source_id_sha256(self) -> str: ...


class AdapterOutput(Protocol):
    @property
    def source_sha256(self) -> str: ...

    @property
    def schema_version(self) -> str | None: ...

    @property
    def transformation_sha256(self) -> str: ...

    @property
    def source(self) -> int: ...

    @property
    def accepted(self) -> int: ...

    @property
    def rejected(self) -> int: ...

    @property
    def duplicate(self) -> int: ...

    @property
    def records(self) -> Sequence[AdapterRecord]: ...

    @property
    def rejections(self) -> Sequence[AdapterRejection]: ...

    @property
    def child_exceptions(self) -> Sequence[AdapterChildException]: ...


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _require_sha256(value: str, field: str) -> None:
    if SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _canonical_model(model: BaseModel | None) -> str | None:
    if model is None:
        return None
    return json.dumps(
        model.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )


@dataclass(frozen=True)
class ReviewedCustomerAggregate:
    row_number: int
    source_identity: str
    source_identity_sha256: str
    source_row_sha256: str
    customer_json: str
    contact_json: str | None
    service_location_json: tuple[str, ...]
    billing_address_json: str | None

    def __post_init__(self) -> None:
        if self.row_number < 2:
            raise ValueError("row_number must identify a source data row")
        if not self.source_identity or len(self.source_identity) > 191:
            raise ValueError("source_identity must be present and bounded")
        _require_sha256(self.source_identity_sha256, "source_identity_sha256")
        _require_sha256(self.source_row_sha256, "source_row_sha256")
        if _sha256(self.source_identity) != self.source_identity_sha256:
            raise ValueError("source identity digest does not match its value")

    @property
    def customer(self) -> CustomerCreate:
        return CustomerCreate.model_validate_json(self.customer_json)

    @property
    def contact(self) -> ContactCreate | None:
        return (
            ContactCreate.model_validate_json(self.contact_json)
            if self.contact_json is not None
            else None
        )

    @property
    def service_locations(self) -> tuple[ServiceLocationCreate, ...]:
        return tuple(
            ServiceLocationCreate.model_validate_json(payload)
            for payload in self.service_location_json
        )

    @property
    def billing_address(self) -> ServiceLocationCreate | None:
        return (
            ServiceLocationCreate.model_validate_json(self.billing_address_json)
            if self.billing_address_json is not None
            else None
        )


@dataclass(frozen=True)
class ReviewedCustomerAdapterOutput:
    review_version: str
    source_system: str
    source_sha256: str
    schema_version: str
    transformation_sha256: str
    source_count: int
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    aggregates: tuple[ReviewedCustomerAggregate, ...]
    rejected_source_identities: tuple[str, ...]
    duplicate_source_identities: tuple[str, ...]
    child_exception_source_identities: tuple[str, ...]
    review_sha256: str

    def integrity_payload(self) -> dict[str, object]:
        return {
            "review_version": self.review_version,
            "source_system": self.source_system,
            "source_sha256": self.source_sha256,
            "schema_version": self.schema_version,
            "transformation_sha256": self.transformation_sha256,
            "source_count": self.source_count,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "duplicate_count": self.duplicate_count,
            "aggregates": [aggregate.__dict__ for aggregate in self.aggregates],
            "rejected_source_identities": self.rejected_source_identities,
            "duplicate_source_identities": self.duplicate_source_identities,
            "child_exception_source_identities": (
                self.child_exception_source_identities
            ),
        }

    def validate_integrity(self) -> None:
        if self.review_version != REVIEW_VERSION:
            raise ValueError("unsupported reviewed-output version")
        if not self.source_system or len(self.source_system) > 50:
            raise ValueError("source_system must be explicit and bounded")
        _require_sha256(self.source_sha256, "source_sha256")
        _require_sha256(self.transformation_sha256, "transformation_sha256")
        _require_sha256(self.review_sha256, "review_sha256")
        if self.source_count != (
            self.accepted_count + self.rejected_count + self.duplicate_count
        ):
            raise ValueError("reviewed output counts do not reconcile")
        if self.accepted_count != len(self.aggregates):
            raise ValueError("accepted count does not match reviewed aggregates")
        identities = [item.source_identity_sha256 for item in self.aggregates]
        if len(identities) != len(set(identities)):
            raise ValueError("reviewed aggregates contain duplicate identities")
        expected = _sha256(
            json.dumps(self.integrity_payload(), sort_keys=True, separators=(",", ":"))
        )
        if expected != self.review_sha256:
            raise ValueError("reviewed output digest mismatch")


def review_adapter_output(
    output: AdapterOutput,
    *,
    source_system: str,
) -> ReviewedCustomerAdapterOutput:
    if output.schema_version is None:
        raise ValueError("adapter output must have a supported schema")
    aggregates = tuple(
        ReviewedCustomerAggregate(
            row_number=record.row_number,
            source_identity=record.source_id,
            source_identity_sha256=_sha256(record.source_id),
            source_row_sha256=record.source_row_sha256,
            customer_json=_canonical_model(record.customer) or "",
            contact_json=_canonical_model(record.contact),
            service_location_json=tuple(
                _canonical_model(location) or ""
                for location in record.service_locations
            ),
            billing_address_json=_canonical_model(record.billing_address),
        )
        for record in output.records
    )
    rejected = tuple(
        sorted(
            {
                item.source_id_sha256
                for item in output.rejections
                if item.disposition == "rejected" and item.source_id_sha256
            }
        )
    )
    duplicates = tuple(
        sorted(
            {
                item.source_id_sha256
                for item in output.rejections
                if item.disposition == "duplicate" and item.source_id_sha256
            }
        )
    )
    children = tuple(
        sorted({item.source_id_sha256 for item in output.child_exceptions})
    )
    values: dict[str, object] = {
        "review_version": REVIEW_VERSION,
        "source_system": source_system,
        "source_sha256": output.source_sha256,
        "schema_version": output.schema_version,
        "transformation_sha256": output.transformation_sha256,
        "source_count": output.source,
        "accepted_count": output.accepted,
        "rejected_count": output.rejected,
        "duplicate_count": output.duplicate,
        "aggregates": aggregates,
        "rejected_source_identities": rejected,
        "duplicate_source_identities": duplicates,
        "child_exception_source_identities": children,
    }
    review_sha256 = _sha256(
        json.dumps(
            {
                **values,
                "aggregates": [aggregate.__dict__ for aggregate in aggregates],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    reviewed = ReviewedCustomerAdapterOutput(
        review_version=REVIEW_VERSION,
        source_system=source_system,
        source_sha256=output.source_sha256,
        schema_version=output.schema_version,
        transformation_sha256=output.transformation_sha256,
        source_count=output.source,
        accepted_count=output.accepted,
        rejected_count=output.rejected,
        duplicate_count=output.duplicate,
        aggregates=aggregates,
        rejected_source_identities=rejected,
        duplicate_source_identities=duplicates,
        child_exception_source_identities=children,
        review_sha256=review_sha256,
    )
    reviewed.validate_integrity()
    return reviewed


@dataclass(frozen=True)
class ExpectedCustomerImportCounts:
    customers: int
    contacts: int
    service_locations: int
    billing_addresses: int
    business_events: int


@dataclass(frozen=True)
class ApprovedCustomerImportBoundary:
    boundary_version: str
    source_sha256: str
    schema_version: str
    pilot_boundary_sha256: str
    approved_source_identities: tuple[str, ...]
    expected: ExpectedCustomerImportCounts

    def validate(self) -> None:
        if self.boundary_version != BOUNDARY_VERSION:
            raise ValueError("unsupported pilot-boundary version")
        _require_sha256(self.source_sha256, "source_sha256")
        _require_sha256(self.pilot_boundary_sha256, "pilot_boundary_sha256")
        for identity in self.approved_source_identities:
            _require_sha256(identity, "approved_source_identity")
        if len(self.approved_source_identities) != len(
            set(self.approved_source_identities)
        ):
            raise ValueError("approved source identities must be unique")
        digest = _sha256(
            json.dumps(self.approved_source_identities, separators=(",", ":"))
        )
        if digest != self.pilot_boundary_sha256:
            raise ValueError("pilot boundary digest mismatch")


@dataclass(frozen=True)
class CustomerAdapterImportReport:
    run_id: str
    attempted: int
    accepted: int
    duplicate: int
    rejected: int


class CustomerAdapterImportError(ValueError):
    pass


class CustomerAdapterImportService:
    def __init__(
        self,
        *,
        repository: CustomerAdapterImportRepository | None = None,
        policy: CustomerAdapterImportPolicy = customer_adapter_import_policy,
        customer_service: CustomerService | None = None,
        audit: AuditService = audit_service,
    ) -> None:
        self.repository = repository or CustomerAdapterImportRepository()
        self.policy = policy
        self.customer_service = customer_service or CustomerService()
        self.audit = audit

    @staticmethod
    def _selected(
        reviewed: ReviewedCustomerAdapterOutput,
        boundary: ApprovedCustomerImportBoundary,
    ) -> tuple[ReviewedCustomerAggregate, ...]:
        by_identity = {
            item.source_identity_sha256: item for item in reviewed.aggregates
        }
        try:
            return tuple(
                by_identity[identity]
                for identity in boundary.approved_source_identities
            )
        except KeyError as error:
            raise CustomerAdapterImportError(
                "allowlist contains an identity absent from reviewed output"
            ) from error

    def _validate_exclusions(
        self,
        reviewed: ReviewedCustomerAdapterOutput,
        selected: tuple[ReviewedCustomerAggregate, ...],
    ) -> None:
        selected_ids = {item.source_identity_sha256 for item in selected}
        blocked = selected_ids.intersection(
            reviewed.rejected_source_identities
            + reviewed.duplicate_source_identities
            + reviewed.child_exception_source_identities
        )
        if blocked:
            raise CustomerAdapterImportError(
                "approved boundary contains a rejected, duplicate, or exceptional identity"
            )
        if any(len(item.service_locations) > 1 for item in selected):
            raise CustomerAdapterImportError(
                "approved boundary contains a multi-location aggregate"
            )
        duplicate_members = self.policy.duplicate_members(reviewed.aggregates)
        if selected_ids.intersection(duplicate_members):
            raise CustomerAdapterImportError(
                "approved boundary contains a recomputed duplicate signal"
            )

    async def _verify_staged_review(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        reviewed: ReviewedCustomerAdapterOutput,
        selected: tuple[ReviewedCustomerAggregate, ...],
    ) -> None:
        artifact = await self.repository.find_staged_artifact(
            session,
            context=context,
            source_system=reviewed.source_system,
            source_sha256=reviewed.source_sha256,
        )
        if artifact is None:
            raise ValueError("reviewed staging artifact is required before import")
        if (
            artifact.schema_version != reviewed.schema_version
            or artifact.transformation_sha256 != reviewed.transformation_sha256
            or artifact.row_count != reviewed.source_count
        ):
            raise ValueError("staged artifact does not match reviewed output")
        for aggregate in selected:
            source_row = await self.repository.find_staged_row(
                session,
                artifact_id=artifact.id,
                source_identity_sha256=aggregate.source_identity_sha256,
                source_row_sha256=aggregate.source_row_sha256,
            )
            if source_row is None:
                raise ValueError("approved aggregate is absent from reviewed staging")
            candidates = await self.repository.list_staged_candidates(
                session, source_row_id=source_row.id
            )
            actual = {
                (item.entity_type, item.ordinal): item.payload_sha256
                for item in candidates
            }
            if actual != self.policy.candidate_hashes(aggregate):
                raise ValueError("staged candidates do not match reviewed aggregate")

    async def _create_run(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        reviewed: ReviewedCustomerAdapterOutput,
        selected_count: int,
    ) -> UUID:
        assert context.active_branch is not None
        async with factory() as session, session.begin():
            run = CustomerMigrationRun(
                company_id=context.company.id,
                branch_id=context.active_branch.id,
                initiated_by_user_id=context.user.id,
                source_system=reviewed.source_system,
                source_sha256=reviewed.source_sha256,
                mode="import",
                status="running",
            )
            session.add(run)
            await session.flush()
            session.add(
                CustomerMigrationProgress(
                    run_id=run.id,
                    entity_type="customer",
                    source_count=selected_count,
                    processed_count=0,
                    accepted_count=0,
                    rejected_count=0,
                    duplicate_count=0,
                    unresolved_count=0,
                )
            )
            return run.id

    async def _advance(
        self,
        session: AsyncSession,
        *,
        run_id: UUID,
        disposition: str,
    ) -> None:
        run, progress = await self.repository.lock_run_progress(session, run_id=run_id)
        progress.processed_count += 1
        run.source_count += 1
        if disposition == "accepted":
            progress.accepted_count += 1
            run.accepted_count += 1
        elif disposition == "duplicate":
            progress.duplicate_count += 1
            run.duplicate_count += 1
        else:
            progress.rejected_count += 1
            run.rejected_count += 1
        progress.updated_at = utc_now()

    def _audit(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        run_id: UUID,
        aggregate: ReviewedCustomerAggregate,
        boundary: ApprovedCustomerImportBoundary,
        outcome: str,
        reason_code: str,
    ) -> None:
        assert context.active_branch is not None
        self.audit.stage(
            session,
            AuditEntry(
                action="customer_migration.aggregate_imported",
                resource_type="customer_migration_run",
                resource_id=run_id,
                outcome=outcome,
                actor_user_id=context.user.id,
                company_id=context.company.id,
                branch_id=context.active_branch.id,
                reason_code=reason_code,
                details={
                    "source_identity_sha256": aggregate.source_identity_sha256,
                    "source_row_sha256": aggregate.source_row_sha256,
                    "pilot_boundary_sha256": boundary.pilot_boundary_sha256,
                },
            ),
        )

    async def _record_failure(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        run_id: UUID,
        aggregate: ReviewedCustomerAggregate,
        boundary: ApprovedCustomerImportBoundary,
        reason_code: str,
    ) -> None:
        async with factory() as session, session.begin():
            session.add(
                CustomerMigrationException(
                    run_id=run_id,
                    row_number=aggregate.row_number,
                    entity_type="customer",
                    source_id_sha256=aggregate.source_identity_sha256,
                    disposition="rejected",
                    reason_code=reason_code,
                    detail="Reviewed Customer aggregate failed closed import validation.",
                )
            )
            await self._advance(session, run_id=run_id, disposition="rejected")
            run = await session.get(CustomerMigrationRun, run_id, with_for_update=True)
            assert run is not None
            run.status = "failed"
            run.completed_at = utc_now()
            self._audit(
                session,
                context=context,
                run_id=run_id,
                aggregate=aggregate,
                boundary=boundary,
                outcome="failure",
                reason_code=reason_code,
            )

    async def run(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        reviewed: ReviewedCustomerAdapterOutput,
        boundary: ApprovedCustomerImportBoundary,
    ) -> CustomerAdapterImportReport:
        try:
            reviewed.validate_integrity()
            boundary.validate()
        except ValueError as error:
            raise CustomerAdapterImportError(str(error)) from error
        if context.active_branch is None or not context.can_access_branch(
            context.active_branch.id
        ):
            raise CustomerAdapterImportError("an authorized active Branch is required")
        if reviewed.source_sha256 != boundary.source_sha256:
            raise CustomerAdapterImportError("source checksum mismatch")
        if reviewed.schema_version != boundary.schema_version:
            raise CustomerAdapterImportError("schema-version mismatch")
        selected = self._selected(reviewed, boundary)
        self._validate_exclusions(reviewed, selected)
        policy_counts = self.policy.expected_counts(selected)
        if (
            policy_counts.customers,
            policy_counts.contacts,
            policy_counts.service_locations,
            policy_counts.billing_addresses,
            policy_counts.business_events,
        ) != (
            boundary.expected.customers,
            boundary.expected.contacts,
            boundary.expected.service_locations,
            boundary.expected.billing_addresses,
            boundary.expected.business_events,
        ):
            raise CustomerAdapterImportError("approved count boundary mismatch")
        try:
            async with factory() as session:
                await self._verify_staged_review(
                    session,
                    context=context,
                    reviewed=reviewed,
                    selected=selected,
                )
        except ValueError as error:
            raise CustomerAdapterImportError(str(error)) from error
        run_id = await self._create_run(
            factory,
            context=context,
            reviewed=reviewed,
            selected_count=len(selected),
        )
        for aggregate in selected:
            try:
                reviewed.validate_integrity()
                async with factory() as session, session.begin():
                    existing = await self.repository.find_source_identity(
                        session,
                        context=context,
                        source_system=reviewed.source_system,
                        source_identity=aggregate.source_identity,
                    )
                    if existing is not None:
                        if existing.branch_id != context.active_branch.id:
                            raise CustomerAdapterImportError(
                                "source identity belongs to another Branch"
                            )
                        await self._advance(
                            session, run_id=run_id, disposition="duplicate"
                        )
                        self._audit(
                            session,
                            context=context,
                            run_id=run_id,
                            aggregate=aggregate,
                            boundary=boundary,
                            outcome="success",
                            reason_code="idempotent_replay",
                        )
                        continue
                    lookup = self.policy.duplicate_lookup(aggregate)
                    if await self.repository.count_supplied_identity_matches(
                        session,
                        company_id=context.company.id,
                        normalized_name=lookup.normalized_name,
                        normalized_emails=lookup.normalized_emails,
                        normalized_phones=lookup.normalized_phones,
                        normalized_address=lookup.normalized_address,
                    ):
                        raise CustomerAdapterImportError(
                            "operational_duplicate_detected"
                        )
                    locations = aggregate.service_locations
                    customer = await self.customer_service.stage_migrated_customer(
                        session,
                        context=context,
                        customer_data=aggregate.customer,
                        contact_data=aggregate.contact,
                        service_location_data=locations[0] if locations else None,
                        billing_address_data=aggregate.billing_address,
                    )
                    assert context.active_branch is not None
                    session.add(
                        CustomerSourceIdentity(
                            company_id=context.company.id,
                            branch_id=context.active_branch.id,
                            customer_id=customer.id,
                            source_system=reviewed.source_system,
                            source_customer_id=aggregate.source_identity,
                            first_run_id=run_id,
                        )
                    )
                    await self._advance(session, run_id=run_id, disposition="accepted")
                    self._audit(
                        session,
                        context=context,
                        run_id=run_id,
                        aggregate=aggregate,
                        boundary=boundary,
                        outcome="success",
                        reason_code="reviewed_adapter_import",
                    )
            except Exception as error:
                reason = (
                    str(error)
                    if isinstance(error, CustomerAdapterImportError)
                    else "aggregate_transaction_failed"
                )
                await self._record_failure(
                    factory,
                    context=context,
                    run_id=run_id,
                    aggregate=aggregate,
                    boundary=boundary,
                    reason_code=reason,
                )
                raise CustomerAdapterImportError(reason) from error
        async with factory() as session, session.begin():
            run = await session.get(CustomerMigrationRun, run_id, with_for_update=True)
            if run is None:
                raise RuntimeError("Customer adapter import run disappeared")
            run.status = "completed"
            run.completed_at = utc_now()
            return CustomerAdapterImportReport(
                run_id=str(run.id),
                attempted=run.source_count,
                accepted=run.accepted_count,
                duplicate=run.duplicate_count,
                rejected=run.rejected_count,
            )
