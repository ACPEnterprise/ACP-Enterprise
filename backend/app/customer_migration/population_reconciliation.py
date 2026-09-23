"""Exact-provider Customer population reconciliation.

This module inventories accepted staged HCP Customers and composes exact
admission through the existing reviewed Customer importer.  It never matches
on a name, address, email, or phone number.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.customer_migration.adapter_import import (
    BOUNDARY_VERSION,
    REVIEW_VERSION,
    ApprovedCustomerImportBoundary,
    ExpectedCustomerImportCounts,
    ReviewedCustomerAdapterOutput,
    ReviewedCustomerAggregate,
)
from app.customer_migration.adapter_import_policy import customer_adapter_import_policy
from app.customer_migration.customer_import import (
    CustomerImportFacade,
    customer_import_facade,
)
from app.customer_migration.models import (
    CustomerMigrationCandidate,
    CustomerMigrationSourceArtifact,
    CustomerMigrationSourceRow,
    CustomerPopulationReconciliationCommand,
    CustomerPopulationReconciliationDisposition,
    CustomerPopulationRefreshRun,
    CustomerSourceIdentity,
)
from app.customers.models import Customer, CustomerContact, ServiceLocation
from app.customers.schemas import ContactCreate, CustomerCreate, ServiceLocationCreate
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.idempotency.contracts import (
    IdempotencyIdentity,
    canonical_request_digest,
)
from app.platform.idempotency.reliability import (
    AuthoritativeOutcome,
    MutationDisposition,
    RetentionClass,
    mutation_reliability_service,
)
from app.platform.permissions.authorization import (
    AuthorizationContext,
    AuthorizationService,
    authorization_service,
)
from app.platform.permissions.codes import CustomerPermission

HCP_SOURCE_SYSTEM = "housecall_pro"
POPULATION_CONTRACT_VERSION = "customer-population-reconciliation/v1"


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _lock_key(*values: object) -> int:
    raw = hashlib.sha256("\x1f".join(map(str, values)).encode()).digest()
    return int.from_bytes(raw[:8], byteorder="big", signed=True)


class CustomerPopulationReconciliationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CustomerPopulationCounts:
    total: int
    bound: int
    held: int
    ambiguous: int
    unexplained: int

    def __post_init__(self) -> None:
        if self.total != self.bound + self.held + self.ambiguous + self.unexplained:
            raise ValueError("Customer population dispositions do not reconcile")


@dataclass(frozen=True, slots=True)
class CustomerPopulationReport:
    source_system: str
    counts: CustomerPopulationCounts
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class ExactCustomerAdmissionCommand:
    source_system: str
    source_customer_id: str
    source_artifact_id: UUID
    expected_source_sha256: str
    expected_source_row_sha256: str
    expected_customers: int
    expected_contacts: int
    expected_service_locations: int
    expected_billing_addresses: int
    idempotency_key: str
    reason_code: str

    def __post_init__(self) -> None:
        if not self.source_system or not self.source_customer_id:
            raise ValueError("exact provider source identity is required")
        if len(self.source_customer_id) > 191:
            raise ValueError("provider Customer identity is too long")
        if len(self.idempotency_key) < 8 or len(self.idempotency_key) > 160:
            raise ValueError("bounded idempotency key is required")
        if not self.reason_code or len(self.reason_code) > 80:
            raise ValueError("bounded reconciliation reason is required")
        if any(
            value < 0
            for value in (
                self.expected_customers,
                self.expected_contacts,
                self.expected_service_locations,
                self.expected_billing_addresses,
            )
        ):
            raise ValueError("expected admission counts cannot be negative")
        if self.expected_customers != 1:
            raise ValueError("exact admission must target one Customer")
        for value in (self.expected_source_sha256, self.expected_source_row_sha256):
            if len(value) != 64 or any(
                character not in "0123456789abcdef" for character in value
            ):
                raise ValueError("source digests must be lowercase SHA-256 values")

    @property
    def request_digest(self) -> str:
        return _digest(
            {
                "contract": POPULATION_CONTRACT_VERSION,
                "source_system": self.source_system,
                "source_customer_id": self.source_customer_id,
                "source_artifact_id": self.source_artifact_id,
                "expected_source_sha256": self.expected_source_sha256,
                "expected_source_row_sha256": self.expected_source_row_sha256,
                "expected_customers": self.expected_customers,
                "expected_contacts": self.expected_contacts,
                "expected_service_locations": self.expected_service_locations,
                "expected_billing_addresses": self.expected_billing_addresses,
                "reason_code": self.reason_code,
            }
        )


@dataclass(frozen=True, slots=True)
class ExactCustomerAdmissionResult:
    customer_id: UUID
    customer_source_identity_id: UUID
    disposition_id: UUID
    customers: int
    contacts: int
    service_locations: int
    billing_addresses: int
    replayed: bool


@dataclass(frozen=True, slots=True)
class CleanMajorityAdmissionResult:
    source_system: str
    selected: int
    admitted: int
    replayed: int
    quarantined: int
    remaining_unexplained: int
    before_digest: str
    after_digest: str

    def __post_init__(self) -> None:
        if self.selected != self.admitted + self.replayed + self.quarantined:
            raise ValueError("clean-majority Customer outcomes do not reconcile")


class CustomerPopulationReconciliationService:
    def __init__(
        self,
        *,
        importer: CustomerImportFacade = customer_import_facade,
        authorization: AuthorizationService = authorization_service,
        audit: AuditService = audit_service,
    ) -> None:
        self.importer = importer
        self.authorization = authorization
        self.audit = audit

    def _authorize(self, context: AuthorizationContext) -> None:
        if context.active_branch is None or not context.can_access_branch(
            context.active_branch.id
        ):
            raise CustomerPopulationReconciliationError(
                "an authorized active Branch is required"
            )
        self.authorization.require_permission(context, CustomerPermission.MANAGE)

    @staticmethod
    async def _lock(
        session: AsyncSession, *, company_id: UUID, source_system: str, identity: str
    ) -> None:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _lock_key(company_id, source_system, identity)},
        )

    @staticmethod
    async def _latest_disposition(
        session: AsyncSession,
        *,
        company_id: UUID,
        source_system: str,
        source_customer_id: str,
        for_update: bool = False,
    ) -> CustomerPopulationReconciliationDisposition | None:
        statement = (
            select(CustomerPopulationReconciliationDisposition)
            .where(
                CustomerPopulationReconciliationDisposition.company_id == company_id,
                CustomerPopulationReconciliationDisposition.source_system
                == source_system,
                CustomerPopulationReconciliationDisposition.source_customer_id
                == source_customer_id,
            )
            .order_by(CustomerPopulationReconciliationDisposition.version.desc())
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    async def _record_disposition(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        artifact: CustomerMigrationSourceArtifact,
        source_row: CustomerMigrationSourceRow,
        disposition: str,
        reason_code: str,
        binding: CustomerSourceIdentity | None,
    ) -> CustomerPopulationReconciliationDisposition:
        assert context.active_branch is not None
        if source_row.source_identity is None or source_row.source_id_sha256 is None:
            raise CustomerPopulationReconciliationError(
                "accepted source row has no exact provider identity"
            )
        await self._lock(
            session,
            company_id=context.company.id,
            source_system=artifact.source_system,
            identity=source_row.source_identity,
        )
        latest = await self._latest_disposition(
            session,
            company_id=context.company.id,
            source_system=artifact.source_system,
            source_customer_id=source_row.source_identity,
            for_update=True,
        )
        evidence_digest = _digest(
            {
                "contract": POPULATION_CONTRACT_VERSION,
                "artifact_id": artifact.id,
                "source_sha256": artifact.source_sha256,
                "source_row_id": source_row.id,
                "source_row_sha256": source_row.source_row_sha256,
                "disposition": disposition,
                "reason_code": reason_code,
                "binding_id": binding.id if binding else None,
                "customer_id": binding.customer_id if binding else None,
            }
        )
        if latest is not None and latest.evidence_digest == evidence_digest:
            return latest
        row = CustomerPopulationReconciliationDisposition(
            company_id=context.company.id,
            branch_id=context.active_branch.id,
            source_artifact_id=artifact.id,
            source_row_id=source_row.id,
            customer_source_identity_id=binding.id if binding else None,
            customer_id=binding.customer_id if binding else None,
            source_system=artifact.source_system,
            source_customer_id=source_row.source_identity,
            source_identity_sha256=source_row.source_id_sha256,
            source_row_sha256=source_row.source_row_sha256,
            disposition=disposition,
            reason_code=reason_code,
            version=(latest.version + 1) if latest else 1,
            evidence_digest=evidence_digest,
            decided_by_user_id=context.user.id,
        )
        session.add(row)
        await session.flush()
        return row

    async def refresh_population(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        source_system: str = HCP_SOURCE_SYSTEM,
    ) -> CustomerPopulationReport:
        async with factory() as session, session.begin():
            return await self._refresh_population_in_session(
                session, context=context, source_system=source_system
            )

    async def _refresh_population_in_session(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        source_system: str,
    ) -> CustomerPopulationReport:
        self._authorize(context)
        assert context.active_branch is not None
        evidence: list[str] = []
        observations = list(
            (
                await session.execute(
                    select(CustomerMigrationSourceRow, CustomerMigrationSourceArtifact)
                    .join(
                        CustomerMigrationSourceArtifact,
                        CustomerMigrationSourceArtifact.id
                        == CustomerMigrationSourceRow.artifact_id,
                    )
                    .where(
                        CustomerMigrationSourceArtifact.company_id
                        == context.company.id,
                        CustomerMigrationSourceArtifact.branch_id
                        == context.active_branch.id,
                        CustomerMigrationSourceArtifact.source_system == source_system,
                        CustomerMigrationSourceRow.disposition == "accepted",
                        CustomerMigrationSourceRow.source_identity.is_not(None),
                    )
                    .order_by(
                        CustomerMigrationSourceRow.source_identity,
                        CustomerMigrationSourceArtifact.created_at.desc(),
                        CustomerMigrationSourceRow.created_at.desc(),
                    )
                )
            ).all()
        )
        grouped: dict[
            str,
            list[tuple[CustomerMigrationSourceRow, CustomerMigrationSourceArtifact]],
        ] = defaultdict(list)
        for source_row, artifact in observations:
            assert source_row.source_identity is not None
            grouped[source_row.source_identity].append((source_row, artifact))
        for source_customer_id, values in sorted(grouped.items()):
            source_row, artifact = values[0]
            binding = await session.scalar(
                select(CustomerSourceIdentity).where(
                    CustomerSourceIdentity.company_id == context.company.id,
                    CustomerSourceIdentity.source_system == source_system,
                    CustomerSourceIdentity.source_customer_id == source_customer_id,
                )
            )
            prior = await self._latest_disposition(
                session,
                company_id=context.company.id,
                source_system=source_system,
                source_customer_id=source_customer_id,
            )
            if binding is not None and binding.branch_id == context.active_branch.id:
                disposition, reason = "BOUND", "exact_provider_identity_bound"
            elif binding is not None:
                binding = None
                disposition, reason = "AMBIGUOUS", "binding_branch_conflict"
            elif prior is not None and prior.disposition == "HELD":
                disposition, reason = "HELD", prior.reason_code
            elif len({item[0].source_row_sha256 for item in values}) > 1:
                disposition, reason = "AMBIGUOUS", "conflicting_source_observations"
            else:
                disposition, reason = "UNEXPLAINED", "accepted_source_not_bound"
            recorded = await self._record_disposition(
                session,
                context=context,
                artifact=artifact,
                source_row=source_row,
                disposition=disposition,
                reason_code=reason,
                binding=binding,
            )
            evidence.append(recorded.evidence_digest)
        counts = await self._current_counts_in_session(
            session, context=context, source_system=source_system
        )
        return CustomerPopulationReport(
            source_system=source_system,
            counts=counts,
            evidence_digest=_digest(sorted(evidence)),
        )

    async def current_counts(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        source_system: str = HCP_SOURCE_SYSTEM,
    ) -> CustomerPopulationCounts:
        self._authorize(context)
        assert context.active_branch is not None
        async with factory() as session:
            return await self._current_counts_in_session(
                session, context=context, source_system=source_system
            )

    async def admit_clean_majority(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        source_system: str = HCP_SOURCE_SYSTEM,
        limit: int = 5000,
    ) -> CleanMajorityAdmissionResult:
        """Admit exact safe rows independently and quarantine only failed rows."""
        self._authorize(context)
        if limit < 1 or limit > 5000:
            raise CustomerPopulationReconciliationError(
                "clean-majority admission limit must be between 1 and 5000"
            )
        before = await self.refresh_population(
            factory, context=context, source_system=source_system
        )
        assert context.active_branch is not None
        latest = (
            select(
                CustomerPopulationReconciliationDisposition.source_customer_id,
                func.max(CustomerPopulationReconciliationDisposition.version).label(
                    "version"
                ),
            )
            .where(
                CustomerPopulationReconciliationDisposition.company_id
                == context.company.id,
                CustomerPopulationReconciliationDisposition.branch_id
                == context.active_branch.id,
                CustomerPopulationReconciliationDisposition.source_system
                == source_system,
            )
            .group_by(CustomerPopulationReconciliationDisposition.source_customer_id)
            .subquery()
        )
        async with factory() as session:
            candidates = tuple(
                (
                    await session.scalars(
                        select(CustomerPopulationReconciliationDisposition)
                        .join(
                            latest,
                            (
                                latest.c.source_customer_id
                                == CustomerPopulationReconciliationDisposition.source_customer_id
                            )
                            & (
                                latest.c.version
                                == CustomerPopulationReconciliationDisposition.version
                            ),
                        )
                        .where(
                            CustomerPopulationReconciliationDisposition.company_id
                            == context.company.id,
                            CustomerPopulationReconciliationDisposition.branch_id
                            == context.active_branch.id,
                            CustomerPopulationReconciliationDisposition.source_system
                            == source_system,
                            CustomerPopulationReconciliationDisposition.disposition
                            == "UNEXPLAINED",
                        )
                        .order_by(
                            CustomerPopulationReconciliationDisposition.source_customer_id
                        )
                        .limit(limit)
                    )
                ).all()
            )

        admitted = replayed = quarantined = 0
        reviewed_artifacts: dict[UUID, ReviewedCustomerAdapterOutput] = {}
        for candidate in candidates:
            async with factory() as session:
                artifact = await session.get(
                    CustomerMigrationSourceArtifact, candidate.source_artifact_id
                )
                source_row = await session.get(
                    CustomerMigrationSourceRow, candidate.source_row_id
                )
                if artifact is None or source_row is None:
                    raise CustomerPopulationReconciliationError(
                        "population disposition source evidence is unavailable"
                    )
                try:
                    aggregate = self._aggregate(
                        source_row,
                        tuple(
                            (
                                await session.scalars(
                                    select(CustomerMigrationCandidate).where(
                                        CustomerMigrationCandidate.source_row_id
                                        == source_row.id
                                    )
                                )
                            ).all()
                        ),
                    )
                    expected = customer_adapter_import_policy.expected_counts(
                        (aggregate,)
                    )
                    command = ExactCustomerAdmissionCommand(
                        source_system=source_system,
                        source_customer_id=candidate.source_customer_id,
                        source_artifact_id=artifact.id,
                        expected_source_sha256=artifact.source_sha256,
                        expected_source_row_sha256=source_row.source_row_sha256,
                        expected_customers=expected.customers,
                        expected_contacts=expected.contacts,
                        expected_service_locations=expected.service_locations,
                        expected_billing_addresses=expected.billing_addresses,
                        idempotency_key=(
                            f"clean-majority:{source_system}:"
                            f"{candidate.source_identity_sha256[:32]}:"
                            f"{candidate.source_row_sha256[:16]}"
                        ),
                        reason_code="deterministic_exact_provider_admission",
                    )
                    reviewed = reviewed_artifacts.get(artifact.id)
                    if reviewed is None:
                        reviewed = await self._reviewed_artifact(
                            session, artifact=artifact
                        )
                        reviewed_artifacts[artifact.id] = reviewed
                except (CustomerPopulationReconciliationError, ValueError):
                    await self.hold_exact(
                        factory,
                        context=context,
                        source_system=source_system,
                        source_customer_id=candidate.source_customer_id,
                        reason_code="source_aggregate_validation_required",
                    )
                    quarantined += 1
                    continue
            try:
                result = await self.admit_exact(
                    factory,
                    context=context,
                    command=command,
                    _reviewed=reviewed,
                )
            except CustomerPopulationReconciliationError:
                await self.hold_exact(
                    factory,
                    context=context,
                    source_system=source_system,
                    source_customer_id=candidate.source_customer_id,
                    reason_code="deterministic_admission_review_required",
                )
                quarantined += 1
                continue
            if result.replayed:
                replayed += 1
            else:
                admitted += 1

        after = await self.refresh_population(
            factory, context=context, source_system=source_system
        )
        return CleanMajorityAdmissionResult(
            source_system=source_system,
            selected=len(candidates),
            admitted=admitted,
            replayed=replayed,
            quarantined=quarantined,
            remaining_unexplained=after.counts.unexplained,
            before_digest=before.evidence_digest,
            after_digest=after.evidence_digest,
        )

    async def _current_counts_in_session(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        source_system: str,
    ) -> CustomerPopulationCounts:
        self._authorize(context)
        assert context.active_branch is not None
        latest = (
            select(
                CustomerPopulationReconciliationDisposition.source_customer_id,
                func.max(CustomerPopulationReconciliationDisposition.version).label(
                    "version"
                ),
            )
            .where(
                CustomerPopulationReconciliationDisposition.company_id
                == context.company.id,
                CustomerPopulationReconciliationDisposition.branch_id
                == context.active_branch.id,
                CustomerPopulationReconciliationDisposition.source_system
                == source_system,
            )
            .group_by(CustomerPopulationReconciliationDisposition.source_customer_id)
            .subquery()
        )
        rows = (
            await session.execute(
                select(
                    CustomerPopulationReconciliationDisposition.disposition,
                    func.count(),
                )
                .join(
                    latest,
                    (
                        latest.c.source_customer_id
                        == CustomerPopulationReconciliationDisposition.source_customer_id
                    )
                    & (
                        latest.c.version
                        == CustomerPopulationReconciliationDisposition.version
                    ),
                )
                .where(
                    CustomerPopulationReconciliationDisposition.company_id
                    == context.company.id,
                    CustomerPopulationReconciliationDisposition.branch_id
                    == context.active_branch.id,
                    CustomerPopulationReconciliationDisposition.source_system
                    == source_system,
                )
                .group_by(CustomerPopulationReconciliationDisposition.disposition)
            )
        ).all()
        values = {str(disposition): int(count) for disposition, count in rows}
        total = sum(values.values())
        return CustomerPopulationCounts(
            total=total,
            bound=values.get("BOUND", 0),
            held=values.get("HELD", 0),
            ambiguous=values.get("AMBIGUOUS", 0),
            unexplained=values.get("UNEXPLAINED", 0),
        )

    async def refresh_population_idempotent(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        source_system: str,
        idempotency_key: str,
    ) -> tuple[CustomerPopulationRefreshRun, MutationDisposition, UUID]:
        """Refresh dispositions without admitting or creating any Customer."""

        self._authorize(context)
        branch = context.active_branch
        assert branch is not None
        request_digest = canonical_request_digest(
            {
                "contract": POPULATION_CONTRACT_VERSION,
                "source_system": source_system,
                "branch_id": branch.id,
            }
        )

        async def mutate() -> AuthoritativeOutcome[CustomerPopulationRefreshRun]:
            report = await self._refresh_population_in_session(
                session, context=context, source_system=source_system
            )
            run = CustomerPopulationRefreshRun(
                company_id=context.company.id,
                branch_id=branch.id,
                source_system=source_system,
                total_count=report.counts.total,
                bound_count=report.counts.bound,
                held_count=report.counts.held,
                ambiguous_count=report.counts.ambiguous,
                unexplained_count=report.counts.unexplained,
                evidence_digest=report.evidence_digest,
                initiated_by_user_id=context.user.id,
            )
            session.add(run)
            await session.flush()
            self.audit.stage(
                session,
                AuditEntry(
                    action="customer_population_reconciliation.refreshed",
                    resource_type="customer_population_refresh_run",
                    resource_id=run.id,
                    actor_user_id=context.user.id,
                    company_id=context.company.id,
                    branch_id=branch.id,
                    reason_code="operator_population_refresh",
                    details={
                        "source_system": source_system,
                        "total_count": report.counts.total,
                        "bound_count": report.counts.bound,
                        "held_count": report.counts.held,
                        "ambiguous_count": report.counts.ambiguous,
                        "unexplained_count": report.counts.unexplained,
                        "evidence_digest": report.evidence_digest,
                    },
                ),
            )
            return AuthoritativeOutcome(
                run,
                "customer_population_refresh_run",
                run.id,
                200,
            )

        async def recover(result_id: UUID) -> CustomerPopulationRefreshRun | None:
            result = await session.execute(
                select(CustomerPopulationRefreshRun).where(
                    CustomerPopulationRefreshRun.id == result_id,
                    CustomerPopulationRefreshRun.company_id == context.company.id,
                    CustomerPopulationRefreshRun.branch_id == branch.id,
                )
            )
            return result.scalar_one_or_none()

        result = await mutation_reliability_service.execute(
            session,
            identity=IdempotencyIdentity(
                company_id=context.company.id,
                branch_id=branch.id,
                operation="customer_population_reconciliation.refresh",
                idempotency_key=idempotency_key,
            ),
            actor_user_id=context.user.id,
            request_digest=request_digest,
            retention_class=RetentionClass.OPERATIONAL,
            mutate=mutate,
            recover=recover,
        )
        return result.value, result.disposition, result.receipt_id

    async def hold_exact(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        source_system: str,
        source_customer_id: str,
        reason_code: str,
    ) -> CustomerPopulationReconciliationDisposition:
        self._authorize(context)
        assert context.active_branch is not None
        if not reason_code or len(reason_code) > 80:
            raise CustomerPopulationReconciliationError(
                "bounded hold reason is required"
            )
        async with factory() as session, session.begin():
            result = await session.execute(
                select(CustomerMigrationSourceRow, CustomerMigrationSourceArtifact)
                .join(
                    CustomerMigrationSourceArtifact,
                    CustomerMigrationSourceArtifact.id
                    == CustomerMigrationSourceRow.artifact_id,
                )
                .where(
                    CustomerMigrationSourceArtifact.company_id == context.company.id,
                    CustomerMigrationSourceArtifact.branch_id
                    == context.active_branch.id,
                    CustomerMigrationSourceArtifact.source_system == source_system,
                    CustomerMigrationSourceRow.source_identity == source_customer_id,
                    CustomerMigrationSourceRow.disposition == "accepted",
                )
                .order_by(CustomerMigrationSourceArtifact.created_at.desc())
                .limit(1)
            )
            value = result.one_or_none()
            if value is None:
                raise CustomerPopulationReconciliationError(
                    "accepted provider Customer was not found in this Company and Branch"
                )
            source_row, artifact = value
            binding = await session.scalar(
                select(CustomerSourceIdentity).where(
                    CustomerSourceIdentity.company_id == context.company.id,
                    CustomerSourceIdentity.source_system == source_system,
                    CustomerSourceIdentity.source_customer_id == source_customer_id,
                )
            )
            if binding is not None:
                raise CustomerPopulationReconciliationError(
                    "a bound provider Customer cannot be held"
                )
            return await self._record_disposition(
                session,
                context=context,
                artifact=artifact,
                source_row=source_row,
                disposition="HELD",
                reason_code=reason_code,
                binding=None,
            )

    @staticmethod
    def _aggregate(
        source_row: CustomerMigrationSourceRow,
        candidates: tuple[CustomerMigrationCandidate, ...],
    ) -> ReviewedCustomerAggregate:
        by_type = {(item.entity_type, item.ordinal): item for item in candidates}
        customer_candidate = by_type.get(("customer", 0))
        if (
            customer_candidate is None
            or source_row.source_identity is None
            or source_row.source_id_sha256 is None
        ):
            raise CustomerPopulationReconciliationError(
                "accepted source Customer aggregate is incomplete"
            )
        contact = by_type.get(("contact", 0))
        locations = tuple(
            item
            for item in sorted(candidates, key=lambda value: value.ordinal)
            if item.entity_type == "service_location"
        )
        billing = by_type.get(("billing_address", 0))
        return ReviewedCustomerAggregate(
            row_number=source_row.row_number,
            source_identity=source_row.source_identity,
            source_identity_sha256=source_row.source_id_sha256,
            source_row_sha256=source_row.source_row_sha256,
            customer_json=CustomerCreate.model_validate(
                customer_candidate.payload
            ).model_dump_json(),
            contact_json=(
                ContactCreate.model_validate(contact.payload).model_dump_json()
                if contact
                else None
            ),
            service_location_json=tuple(
                ServiceLocationCreate.model_validate(item.payload).model_dump_json()
                for item in locations
            ),
            billing_address_json=(
                ServiceLocationCreate.model_validate(billing.payload).model_dump_json()
                if billing
                else None
            ),
        )

    async def _reviewed_artifact(
        self,
        session: AsyncSession,
        *,
        artifact: CustomerMigrationSourceArtifact,
    ) -> ReviewedCustomerAdapterOutput:
        rows = tuple(
            (
                await session.scalars(
                    select(CustomerMigrationSourceRow)
                    .where(CustomerMigrationSourceRow.artifact_id == artifact.id)
                    .order_by(CustomerMigrationSourceRow.row_number)
                )
            ).all()
        )
        # The models intentionally do not expose a bidirectional staging relationship.
        aggregates: list[ReviewedCustomerAggregate] = []
        for row in rows:
            if row.disposition != "accepted":
                continue
            candidates = tuple(
                (
                    await session.scalars(
                        select(CustomerMigrationCandidate).where(
                            CustomerMigrationCandidate.source_row_id == row.id
                        )
                    )
                ).all()
            )
            aggregates.append(self._aggregate(row, candidates))
        rejected = tuple(
            sorted(
                row.source_id_sha256
                for row in rows
                if row.disposition == "rejected" and row.source_id_sha256
            )
        )
        duplicates = tuple(
            sorted(
                row.source_id_sha256
                for row in rows
                if row.disposition == "duplicate" and row.source_id_sha256
            )
        )
        values: dict[str, object] = {
            "review_version": REVIEW_VERSION,
            "source_system": artifact.source_system,
            "source_sha256": artifact.source_sha256,
            "schema_version": artifact.schema_version,
            "transformation_sha256": artifact.transformation_sha256,
            "source_count": artifact.row_count,
            "accepted_count": len(aggregates),
            "rejected_count": len(rejected),
            "duplicate_count": len(duplicates),
            "aggregates": tuple(aggregates),
            "rejected_source_identities": rejected,
            "duplicate_source_identities": duplicates,
            "child_exception_source_identities": (),
        }
        review_sha256 = _digest(
            {
                **values,
                "aggregates": [aggregate.__dict__ for aggregate in aggregates],
            }
        )
        reviewed = ReviewedCustomerAdapterOutput(
            review_version=REVIEW_VERSION,
            source_system=artifact.source_system,
            source_sha256=artifact.source_sha256,
            schema_version=artifact.schema_version,
            transformation_sha256=artifact.transformation_sha256,
            source_count=artifact.row_count,
            accepted_count=len(aggregates),
            rejected_count=len(rejected),
            duplicate_count=len(duplicates),
            aggregates=tuple(aggregates),
            rejected_source_identities=rejected,
            duplicate_source_identities=duplicates,
            child_exception_source_identities=(),
            review_sha256=review_sha256,
        )
        reviewed.validate_integrity()
        return reviewed

    async def _start_command(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        command: ExactCustomerAdmissionCommand,
    ) -> tuple[UUID, ExactCustomerAdmissionResult | None]:
        assert context.active_branch is not None
        async with factory() as session, session.begin():
            await self._lock(
                session,
                company_id=context.company.id,
                source_system="reconciliation_command",
                identity=command.idempotency_key,
            )
            existing = await session.scalar(
                select(CustomerPopulationReconciliationCommand)
                .where(
                    CustomerPopulationReconciliationCommand.company_id
                    == context.company.id,
                    CustomerPopulationReconciliationCommand.idempotency_key
                    == command.idempotency_key,
                )
                .with_for_update()
            )
            if existing is not None:
                if existing.request_digest != command.request_digest:
                    raise CustomerPopulationReconciliationError(
                        "idempotency key conflicts with prior exact-provider command"
                    )
                if existing.status == "completed":
                    disposition = await session.get(
                        CustomerPopulationReconciliationDisposition,
                        existing.result_disposition_id,
                    )
                    if disposition is None or existing.result_counts is None:
                        raise CustomerPopulationReconciliationError(
                            "completed reconciliation result is unavailable"
                        )
                    return existing.id, ExactCustomerAdmissionResult(
                        customer_id=existing.customer_id,  # type: ignore[arg-type]
                        customer_source_identity_id=(
                            disposition.customer_source_identity_id  # type: ignore[arg-type]
                        ),
                        disposition_id=disposition.id,
                        customers=existing.result_counts["customers"],
                        contacts=existing.result_counts["contacts"],
                        service_locations=existing.result_counts["service_locations"],
                        billing_addresses=existing.result_counts["billing_addresses"],
                        replayed=True,
                    )
                if existing.status == "pending":
                    raise CustomerPopulationReconciliationError(
                        "exact-provider reconciliation command is already in progress"
                    )
                existing.status = "pending"
                existing.error_code = None
                return existing.id, None
            receipt = CustomerPopulationReconciliationCommand(
                company_id=context.company.id,
                branch_id=context.active_branch.id,
                source_system=command.source_system,
                source_customer_id=command.source_customer_id,
                idempotency_key=command.idempotency_key,
                request_digest=command.request_digest,
                status="pending",
                initiated_by_user_id=context.user.id,
            )
            session.add(receipt)
            await session.flush()
            return receipt.id, None

    async def admit_exact(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        command: ExactCustomerAdmissionCommand,
        _reviewed: ReviewedCustomerAdapterOutput | None = None,
    ) -> ExactCustomerAdmissionResult:
        self._authorize(context)
        assert context.active_branch is not None
        receipt_id, replay = await self._start_command(
            factory, context=context, command=command
        )
        if replay is not None:
            return replay
        try:
            async with factory() as session:
                artifact = await session.scalar(
                    select(CustomerMigrationSourceArtifact).where(
                        CustomerMigrationSourceArtifact.id
                        == command.source_artifact_id,
                        CustomerMigrationSourceArtifact.company_id
                        == context.company.id,
                        CustomerMigrationSourceArtifact.branch_id
                        == context.active_branch.id,
                        CustomerMigrationSourceArtifact.source_system
                        == command.source_system,
                        CustomerMigrationSourceArtifact.source_sha256
                        == command.expected_source_sha256,
                    )
                )
                if artifact is None:
                    raise CustomerPopulationReconciliationError(
                        "exact staged source artifact was not found in this scope"
                    )
                source_row = await session.scalar(
                    select(CustomerMigrationSourceRow).where(
                        CustomerMigrationSourceRow.artifact_id == artifact.id,
                        CustomerMigrationSourceRow.source_identity
                        == command.source_customer_id,
                        CustomerMigrationSourceRow.source_row_sha256
                        == command.expected_source_row_sha256,
                        CustomerMigrationSourceRow.disposition == "accepted",
                    )
                )
                if source_row is None:
                    raise CustomerPopulationReconciliationError(
                        "exact accepted provider Customer row was not found"
                    )
                current = await self._latest_disposition(
                    session,
                    company_id=context.company.id,
                    source_system=command.source_system,
                    source_customer_id=command.source_customer_id,
                )
                if current is not None and current.disposition == "HELD":
                    raise CustomerPopulationReconciliationError(
                        "provider Customer is held for human review"
                    )
                reviewed = _reviewed or await self._reviewed_artifact(
                    session, artifact=artifact
                )
                if (
                    reviewed.source_system != artifact.source_system
                    or reviewed.source_sha256 != artifact.source_sha256
                ):
                    raise CustomerPopulationReconciliationError(
                        "reviewed source evidence does not match the exact artifact"
                    )
            aggregate = next(
                (
                    item
                    for item in reviewed.aggregates
                    if item.source_identity == command.source_customer_id
                    and item.source_row_sha256 == command.expected_source_row_sha256
                ),
                None,
            )
            if aggregate is None:
                raise CustomerPopulationReconciliationError(
                    "exact staged aggregate could not be reconstructed"
                )
            policy_counts = customer_adapter_import_policy.expected_counts((aggregate,))
            actual_expected = (
                policy_counts.customers,
                policy_counts.contacts,
                policy_counts.service_locations,
                policy_counts.billing_addresses,
            )
            commanded_expected = (
                command.expected_customers,
                command.expected_contacts,
                command.expected_service_locations,
                command.expected_billing_addresses,
            )
            if actual_expected != commanded_expected:
                raise CustomerPopulationReconciliationError(
                    "exact staged aggregate counts contradict the approved command"
                )
            identity_sha256 = hashlib.sha256(
                command.source_customer_id.encode()
            ).hexdigest()
            boundary = ApprovedCustomerImportBoundary(
                boundary_version=BOUNDARY_VERSION,
                source_sha256=reviewed.source_sha256,
                schema_version=reviewed.schema_version,
                pilot_boundary_sha256=_digest((identity_sha256,)),
                approved_source_identities=(identity_sha256,),
                expected=ExpectedCustomerImportCounts(
                    customers=policy_counts.customers,
                    contacts=policy_counts.contacts,
                    service_locations=policy_counts.service_locations,
                    billing_addresses=policy_counts.billing_addresses,
                    business_events=policy_counts.business_events,
                ),
            )
            await self.importer.import_reviewed(
                factory, context=context, reviewed=reviewed, boundary=boundary
            )
            async with factory() as session, session.begin():
                binding = await session.scalar(
                    select(CustomerSourceIdentity).where(
                        CustomerSourceIdentity.company_id == context.company.id,
                        CustomerSourceIdentity.branch_id == context.active_branch.id,
                        CustomerSourceIdentity.source_system == command.source_system,
                        CustomerSourceIdentity.source_customer_id
                        == command.source_customer_id,
                    )
                )
                if binding is None:
                    raise CustomerPopulationReconciliationError(
                        "exact provider binding was not created"
                    )
                customer = await session.scalar(
                    select(Customer).where(
                        Customer.id == binding.customer_id,
                        Customer.company_id == context.company.id,
                    )
                )
                if customer is None:
                    raise CustomerPopulationReconciliationError(
                        "bound native Customer was not found"
                    )
                contact_count = int(
                    await session.scalar(
                        select(func.count())
                        .select_from(CustomerContact)
                        .where(CustomerContact.customer_id == customer.id)
                    )
                    or 0
                )
                location_count = int(
                    await session.scalar(
                        select(func.count())
                        .select_from(ServiceLocation)
                        .where(ServiceLocation.customer_id == customer.id)
                    )
                    or 0
                )
                if (
                    contact_count != command.expected_contacts
                    or location_count != command.expected_service_locations
                ):
                    raise CustomerPopulationReconciliationError(
                        "native Customer child linkage does not match approved counts"
                    )
                artifact = await session.get(
                    CustomerMigrationSourceArtifact, command.source_artifact_id
                )
                source_row = await session.scalar(
                    select(CustomerMigrationSourceRow).where(
                        CustomerMigrationSourceRow.artifact_id
                        == command.source_artifact_id,
                        CustomerMigrationSourceRow.source_identity
                        == command.source_customer_id,
                        CustomerMigrationSourceRow.source_row_sha256
                        == command.expected_source_row_sha256,
                    )
                )
                assert artifact is not None and source_row is not None
                disposition = await self._record_disposition(
                    session,
                    context=context,
                    artifact=artifact,
                    source_row=source_row,
                    disposition="BOUND",
                    reason_code=command.reason_code,
                    binding=binding,
                )
                counts = {
                    "customers": 1,
                    "contacts": contact_count,
                    "service_locations": location_count,
                    "billing_addresses": command.expected_billing_addresses,
                }
                receipt = await session.get(
                    CustomerPopulationReconciliationCommand,
                    receipt_id,
                    with_for_update=True,
                )
                if receipt is None or receipt.request_digest != command.request_digest:
                    raise CustomerPopulationReconciliationError(
                        "reconciliation command receipt was lost or contradicted"
                    )
                receipt.status = "completed"
                receipt.result_disposition_id = disposition.id
                receipt.customer_id = customer.id
                receipt.result_counts = counts
                receipt.completed_at = datetime.now(timezone.utc)
                self.audit.stage(
                    session,
                    AuditEntry(
                        action="customer_population_reconciliation.bound",
                        resource_type="customer",
                        resource_id=customer.id,
                        outcome="success",
                        actor_user_id=context.user.id,
                        company_id=context.company.id,
                        branch_id=context.active_branch.id,
                        reason_code=command.reason_code,
                        details={
                            "source_identity_sha256": identity_sha256,
                            "source_row_sha256": command.expected_source_row_sha256,
                            "disposition_evidence_digest": disposition.evidence_digest,
                        },
                    ),
                )
                return ExactCustomerAdmissionResult(
                    customer_id=customer.id,
                    customer_source_identity_id=binding.id,
                    disposition_id=disposition.id,
                    customers=1,
                    contacts=contact_count,
                    service_locations=location_count,
                    billing_addresses=command.expected_billing_addresses,
                    replayed=False,
                )
        except Exception as error:
            async with factory() as session, session.begin():
                receipt = await session.get(
                    CustomerPopulationReconciliationCommand,
                    receipt_id,
                    with_for_update=True,
                )
                if receipt is not None and receipt.status != "completed":
                    receipt.status = "failed"
                    receipt.error_code = type(error).__name__[:80]
            raise


customer_population_reconciliation_service = CustomerPopulationReconciliationService()
