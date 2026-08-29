"""Controlled preview-only execution of reviewed Customer migration pilots."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.customer_migration.adapter_import import (
    BOUNDARY_VERSION,
    ApprovedCustomerImportBoundary,
    CustomerAdapterImportReport,
    ExpectedCustomerImportCounts,
    ReviewedCustomerAdapterOutput,
)
from app.customer_migration.customer_import import (
    CustomerImportFacade,
    customer_import_facade,
)
from app.customer_migration.models import CustomerSourceIdentity
from app.customers.models import (
    Customer,
    CustomerBillingAddress,
    CustomerContact,
    CustomerNote,
    ServiceLocation,
)
from app.events.models import BusinessEvent
from app.financials.models import Estimate, Invoice, Payment
from app.jobs.models import Job
from app.platform.permissions.authorization import (
    AuthorizationContext,
    AuthorizationService,
    authorization_service,
)
from app.platform.permissions.codes import CustomerPermission
from app.scheduling.models import Appointment

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
PILOT_APPROVAL_VERSION = "customer-pilot-execution/v1"
STAGE_APPROVAL_VERSION = "customer-migration-stage-execution/v1"


class PilotExecutionError(ValueError):
    """A controlled pilot failed a precondition and must not run."""


class PilotExpectedCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    customers: int = Field(ge=0)
    contacts: int = Field(ge=0)
    service_locations: int = Field(ge=0)
    billing_addresses: int = Field(ge=0)
    business_events: int = Field(ge=0)


class OperationalCounts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    customers: int = Field(ge=0)
    customer_contacts: int = Field(ge=0)
    service_locations: int = Field(ge=0)
    customer_billing_addresses: int = Field(ge=0)
    customer_notes: int = Field(ge=0)
    appointments: int = Field(ge=0)
    jobs: int = Field(ge=0)
    estimates: int = Field(ge=0)
    invoices: int = Field(ge=0)
    payments: int = Field(ge=0)
    business_events: int = Field(ge=0)


class CustomerPilotApproval(BaseModel):
    """Immutable owner-reviewed execution boundary; no source values are accepted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_version: str
    target_environment: Literal["preview"]
    mode: Literal["validate", "import"]
    source_sha256: str
    schema_version: str = Field(min_length=1, max_length=100)
    reviewed_output_sha256: str
    pilot_manifest_sha256: str
    pilot_boundary_sha256: str
    ordered_source_identity_allowlist: tuple[str, ...] = Field(min_length=1)
    expected: PilotExpectedCounts
    expected_blocking_dispositions: int = Field(ge=0)
    expected_deployed_git_sha: str
    expected_alembic_head: str = Field(min_length=1, max_length=64)
    expected_pre_import_counts: OperationalCounts

    @model_validator(mode="after")
    def validate_approval(self) -> CustomerPilotApproval:
        if self.approval_version not in (
            PILOT_APPROVAL_VERSION,
            STAGE_APPROVAL_VERSION,
        ):
            raise ValueError("unsupported pilot execution approval version")
        for field_name in (
            "source_sha256",
            "reviewed_output_sha256",
            "pilot_manifest_sha256",
            "pilot_boundary_sha256",
        ):
            if SHA256_PATTERN.fullmatch(getattr(self, field_name)) is None:
                raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
        if GIT_SHA_PATTERN.fullmatch(self.expected_deployed_git_sha) is None:
            raise ValueError("expected_deployed_git_sha must be a full Git SHA")
        for identity in self.ordered_source_identity_allowlist:
            if SHA256_PATTERN.fullmatch(identity) is None:
                raise ValueError(
                    "ordered_source_identity_allowlist contains an invalid digest"
                )
        if len(self.ordered_source_identity_allowlist) != len(
            set(self.ordered_source_identity_allowlist)
        ):
            raise ValueError("source identity allowlist must be unique")
        if self.expected.customers != len(self.ordered_source_identity_allowlist):
            raise ValueError("Customer count must equal the approved identity count")
        if self.expected_blocking_dispositions != 0:
            raise ValueError(
                "a live Customer pilot cannot include blocking dispositions"
            )
        return self

    def import_boundary(self) -> ApprovedCustomerImportBoundary:
        return ApprovedCustomerImportBoundary(
            boundary_version=BOUNDARY_VERSION,
            source_sha256=self.source_sha256,
            schema_version=self.schema_version,
            pilot_boundary_sha256=self.pilot_boundary_sha256,
            approved_source_identities=self.ordered_source_identity_allowlist,
            expected=ExpectedCustomerImportCounts(**self.expected.model_dump()),
        )

    def sha256(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode()).hexdigest()


class CustomerMigrationStageApproval(CustomerPilotApproval):
    """Cumulative execution boundary with an explicit imported prefix."""

    expected_already_imported: PilotExpectedCounts

    @model_validator(mode="after")
    def validate_stage_approval(self) -> CustomerMigrationStageApproval:
        if self.approval_version != STAGE_APPROVAL_VERSION:
            raise ValueError("unsupported Customer migration stage approval version")
        if any(
            getattr(self.expected_already_imported, field)
            > getattr(self.expected, field)
            for field in PilotExpectedCounts.model_fields
        ):
            raise ValueError("already-imported counts exceed cumulative stage counts")
        return self


class PreviewBackupEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path_sha256: str
    backup_sha256: str
    byte_size: int = Field(gt=0)
    custom_format_verified: bool

    @model_validator(mode="after")
    def validate_digests(self) -> PreviewBackupEvidence:
        if (
            SHA256_PATTERN.fullmatch(self.path_sha256) is None
            or SHA256_PATTERN.fullmatch(self.backup_sha256) is None
        ):
            raise ValueError("backup evidence digests must be lowercase SHA-256")
        return self


@dataclass(frozen=True)
class PreviewExecutionRuntime:
    environment: str
    deployed_git_sha: str
    alembic_head: str
    backup: PreviewBackupEvidence | None = None


class CustomerPilotExecutionReport(BaseModel):
    """PII-safe command result suitable for restricted execution logs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["validated", "completed", "completed_with_discrepancy"]
    target_environment: Literal["preview"]
    mode: Literal["validate", "import"]
    source_sha256: str
    schema_version: str
    approval_sha256: str
    pilot_manifest_sha256: str
    reviewed_output_sha256: str
    pilot_boundary_sha256: str
    deployed_git_sha: str
    alembic_revision: str
    started_at: datetime
    completed_at: datetime
    expected_counts: PilotExpectedCounts
    actual_count_delta: PilotExpectedCounts
    approved_aggregate_count: int
    run_id: str | None
    attempted: int
    accepted: int
    duplicate: int
    rejected: int
    pre_import_counts: OperationalCounts
    post_import_counts: OperationalCounts
    backup_sha256: str | None
    post_import_counts_match: bool
    idempotent_replay: bool


class OperationalCountReader(Protocol):
    async def read(
        self, factory: async_sessionmaker[AsyncSession]
    ) -> OperationalCounts: ...

    async def alembic_head(self, factory: async_sessionmaker[AsyncSession]) -> str: ...

    async def imported_source_identities(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        source_system: str,
        source_identities: tuple[str, ...],
    ) -> frozenset[str]: ...


class CustomerPilotExecutionRepository:
    CUSTOMER_MIGRATION_EVENT_TYPES = (
        "customer.created",
        "contact.created",
        "service_location.created",
        "customer.billing_address_created",
    )

    async def read(
        self, factory: async_sessionmaker[AsyncSession]
    ) -> OperationalCounts:
        models = {
            "customers": Customer,
            "customer_contacts": CustomerContact,
            "service_locations": ServiceLocation,
            "customer_billing_addresses": CustomerBillingAddress,
            "customer_notes": CustomerNote,
            "appointments": Appointment,
            "jobs": Job,
            "estimates": Estimate,
            "invoices": Invoice,
            "payments": Payment,
        }
        async with factory() as session:
            values = {
                name: int(
                    await session.scalar(select(func.count()).select_from(model)) or 0
                )
                for name, model in models.items()
            }
            values["business_events"] = int(
                await session.scalar(
                    select(func.count())
                    .select_from(BusinessEvent)
                    .where(
                        BusinessEvent.event_type.in_(
                            self.CUSTOMER_MIGRATION_EVENT_TYPES
                        )
                    )
                )
                or 0
            )
        return OperationalCounts.model_validate(values)

    async def alembic_head(self, factory: async_sessionmaker[AsyncSession]) -> str:
        async with factory() as session:
            revision = await session.scalar(
                text("SELECT version_num FROM alembic_version")
            )
        if not isinstance(revision, str) or not revision:
            raise PilotExecutionError("database Alembic revision is unavailable")
        return revision

    async def imported_source_identities(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        source_system: str,
        source_identities: tuple[str, ...],
    ) -> frozenset[str]:
        async with factory() as session:
            values = await session.scalars(
                select(CustomerSourceIdentity.source_customer_id).where(
                    CustomerSourceIdentity.company_id == context.company.id,
                    CustomerSourceIdentity.source_system == source_system,
                    CustomerSourceIdentity.source_customer_id.in_(source_identities),
                )
            )
        return frozenset(values.all())


class CustomerPilotExecutionService:
    """The sole supervised execution boundary above the authoritative facade."""

    def __init__(
        self,
        *,
        facade: CustomerImportFacade = customer_import_facade,
        repository: OperationalCountReader | None = None,
        authorization: AuthorizationService = authorization_service,
    ) -> None:
        self.facade = facade
        self.repository = repository or CustomerPilotExecutionRepository()
        self.authorization = authorization

    def _validate(
        self,
        *,
        context: AuthorizationContext,
        reviewed: ReviewedCustomerAdapterOutput,
        approval: CustomerPilotApproval,
        runtime: PreviewExecutionRuntime,
        current_alembic_head: str,
        pre_counts: OperationalCounts,
    ) -> ApprovedCustomerImportBoundary:
        if runtime.environment != "preview" or approval.target_environment != "preview":
            raise PilotExecutionError("Customer pilot execution is preview-only")
        if runtime.deployed_git_sha != approval.expected_deployed_git_sha:
            raise PilotExecutionError("deployed Git SHA mismatch")
        if (
            runtime.alembic_head != approval.expected_alembic_head
            or current_alembic_head != approval.expected_alembic_head
        ):
            raise PilotExecutionError("Alembic head mismatch")
        if context.active_branch is None:
            raise PilotExecutionError("an active Branch is required")
        self.authorization.require_permission(context, CustomerPermission.MANAGE)
        if reviewed.review_sha256 != approval.reviewed_output_sha256:
            raise PilotExecutionError("reviewed-output digest mismatch")
        if reviewed.source_sha256 != approval.source_sha256:
            raise PilotExecutionError("source digest mismatch")
        if reviewed.schema_version != approval.schema_version:
            raise PilotExecutionError("schema version mismatch")
        expected_post_counts = self._expected_post_counts(approval)
        initial = approval.expected_pre_import_counts
        unchanged = (
            "customer_notes",
            "appointments",
            "jobs",
            "estimates",
            "invoices",
            "payments",
        )
        bounded = (
            "customers",
            "customer_contacts",
            "service_locations",
            "customer_billing_addresses",
        )
        if any(
            getattr(pre_counts, field) != getattr(initial, field) for field in unchanged
        ):
            raise PilotExecutionError("pre-import operational counts changed")
        if pre_counts.business_events < initial.business_events:
            raise PilotExecutionError("pre-import operational counts changed")
        if any(
            not (
                getattr(initial, field)
                <= getattr(pre_counts, field)
                <= getattr(expected_post_counts, field)
            )
            for field in bounded
        ):
            raise PilotExecutionError("pre-import operational counts changed")
        boundary = approval.import_boundary()
        try:
            reviewed.validate_integrity()
            boundary.validate()
        except ValueError as error:
            raise PilotExecutionError(str(error)) from error
        if approval.mode == "import" and (
            runtime.backup is None or not runtime.backup.custom_format_verified
        ):
            raise PilotExecutionError(
                "verified preview PostgreSQL backup is required before execution"
            )
        return boundary

    @staticmethod
    def _expected_post_counts(
        approval: CustomerPilotApproval,
    ) -> OperationalCounts:
        initial = approval.expected_pre_import_counts
        expected = CustomerPilotExecutionService._incremental_expected(approval)
        return initial.model_copy(
            update={
                "customers": initial.customers + expected.customers,
                "customer_contacts": initial.customer_contacts + expected.contacts,
                "service_locations": (
                    initial.service_locations + expected.service_locations
                ),
                "customer_billing_addresses": (
                    initial.customer_billing_addresses + expected.billing_addresses
                ),
                "business_events": (initial.business_events + expected.business_events),
            }
        )

    @staticmethod
    def _incremental_expected(approval: CustomerPilotApproval) -> PilotExpectedCounts:
        existing = getattr(
            approval, "expected_already_imported", None
        ) or PilotExpectedCounts(
            customers=0,
            contacts=0,
            service_locations=0,
            billing_addresses=0,
            business_events=0,
        )
        return PilotExpectedCounts(
            **{
                field: getattr(approval.expected, field) - getattr(existing, field)
                for field in PilotExpectedCounts.model_fields
            }
        )

    async def run(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        reviewed: ReviewedCustomerAdapterOutput,
        approval: CustomerPilotApproval,
        runtime: PreviewExecutionRuntime,
    ) -> CustomerPilotExecutionReport:
        started_at = datetime.now(timezone.utc)
        pre_counts = await self.repository.read(factory)
        current_alembic_head = await self.repository.alembic_head(factory)
        boundary = self._validate(
            context=context,
            reviewed=reviewed,
            approval=approval,
            runtime=runtime,
            current_alembic_head=current_alembic_head,
            pre_counts=pre_counts,
        )
        expected_post_counts = self._expected_post_counts(approval)
        structural_fields = (
            "customers",
            "customer_contacts",
            "service_locations",
            "customer_billing_addresses",
        )
        at_initial_boundary = all(
            getattr(pre_counts, field)
            == getattr(approval.expected_pre_import_counts, field)
            for field in structural_fields
        )
        at_final_boundary = all(
            getattr(pre_counts, field) == getattr(expected_post_counts, field)
            for field in structural_fields
        )
        partial_resume = not at_initial_boundary and not at_final_boundary
        if partial_resume:
            existing = getattr(approval, "expected_already_imported", None)
            if existing is None:
                raise PilotExecutionError("pilot state is not a complete boundary")
            selected_by_hash = {
                aggregate.source_identity_sha256: aggregate
                for aggregate in reviewed.aggregates
            }
            ordered = tuple(
                selected_by_hash[identity].source_identity
                for identity in approval.ordered_source_identity_allowlist
            )
            imported_count = existing.customers + (
                pre_counts.customers - approval.expected_pre_import_counts.customers
            )
            actual_identities = await self.repository.imported_source_identities(
                factory,
                context=context,
                source_system=reviewed.source_system,
                source_identities=ordered,
            )
            if actual_identities != frozenset(ordered[:imported_count]):
                raise PilotExecutionError(
                    "partial stage is not the deterministic imported prefix"
                )
        imported: CustomerAdapterImportReport | None = None
        replay_expected = at_final_boundary
        if approval.mode == "import":
            imported = await self.facade.import_reviewed(
                factory,
                context=context,
                reviewed=reviewed,
                boundary=boundary,
            )
        post_counts = await self.repository.read(factory)
        if approval.mode == "validate" and post_counts != pre_counts:
            raise PilotExecutionError("validation mode changed operational records")
        post_import_counts_match = True
        actual_delta = PilotExpectedCounts(
            customers=post_counts.customers - pre_counts.customers,
            contacts=post_counts.customer_contacts - pre_counts.customer_contacts,
            service_locations=(
                post_counts.service_locations - pre_counts.service_locations
            ),
            billing_addresses=(
                post_counts.customer_billing_addresses
                - pre_counts.customer_billing_addresses
            ),
            business_events=post_counts.business_events - pre_counts.business_events,
        )
        if imported is not None:
            existing = getattr(approval, "expected_already_imported", None)
            imported_count = (existing.customers if existing is not None else 0) + (
                pre_counts.customers - approval.expected_pre_import_counts.customers
            )
            selected_by_hash = {
                aggregate.source_identity_sha256: aggregate
                for aggregate in reviewed.aggregates
            }
            missing = tuple(
                selected_by_hash[identity]
                for identity in approval.ordered_source_identity_allowlist[
                    imported_count:
                ]
            )
            incremental = PilotExpectedCounts(
                customers=len(missing),
                contacts=sum(item.contact is not None for item in missing),
                service_locations=sum(len(item.service_locations) for item in missing),
                billing_addresses=sum(
                    item.billing_address is not None for item in missing
                ),
                business_events=sum(
                    1
                    + (item.contact is not None)
                    + len(item.service_locations)
                    + (item.billing_address is not None)
                    for item in missing
                ),
            )
            recognized = approval.expected.customers - incremental.customers
            expected_delta = (
                incremental
                if imported.accepted == incremental.customers
                and imported.duplicate == recognized
                else PilotExpectedCounts(
                    customers=0,
                    contacts=0,
                    service_locations=0,
                    billing_addresses=0,
                    business_events=0,
                )
                if imported.accepted == 0
                and imported.duplicate == approval.expected.customers
                else None
            )
            post_import_counts_match = (
                expected_delta is not None and actual_delta == expected_delta
            )
        return CustomerPilotExecutionReport(
            status=(
                "validated"
                if imported is None
                else "completed"
                if post_import_counts_match
                else "completed_with_discrepancy"
            ),
            target_environment="preview",
            mode=approval.mode,
            source_sha256=approval.source_sha256,
            schema_version=approval.schema_version,
            approval_sha256=approval.sha256(),
            pilot_manifest_sha256=approval.pilot_manifest_sha256,
            reviewed_output_sha256=approval.reviewed_output_sha256,
            pilot_boundary_sha256=approval.pilot_boundary_sha256,
            deployed_git_sha=runtime.deployed_git_sha,
            alembic_revision=current_alembic_head,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            expected_counts=approval.expected,
            actual_count_delta=actual_delta,
            approved_aggregate_count=len(approval.ordered_source_identity_allowlist),
            run_id=imported.run_id if imported is not None else None,
            attempted=imported.attempted if imported is not None else 0,
            accepted=imported.accepted if imported is not None else 0,
            duplicate=imported.duplicate if imported is not None else 0,
            rejected=imported.rejected if imported is not None else 0,
            pre_import_counts=pre_counts,
            post_import_counts=post_counts,
            backup_sha256=(
                runtime.backup.backup_sha256 if runtime.backup is not None else None
            ),
            post_import_counts_match=post_import_counts_match,
            idempotent_replay=(
                replay_expected
                and imported is not None
                and imported.accepted == 0
                and imported.duplicate == approval.expected.customers
            ),
        )


customer_pilot_execution_service = CustomerPilotExecutionService()
