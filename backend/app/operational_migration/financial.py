import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.financials.models import Invoice
from app.financials.service import (
    FinancialService,
    FinancialValidationError,
    MigratedLineItem,
    MigrateEstimate,
    MigrateInvoice,
    MigratePayment,
)
from app.operational_migration.hcp_rehearsal_authority import (
    SOURCE4_SYSTEM,
    require_sanctioned_context,
)
from app.operational_migration.models import (
    EstimateLineItemSourceIdentity,
    EstimateSourceIdentity,
    InvoiceLineItemSourceIdentity,
    InvoiceSourceIdentity,
    OperationalMigrationException,
    OperationalMigrationProgress,
    OperationalMigrationRun,
    PaymentSourceIdentity,
    utc_now,
)
from app.operational_migration.repository import (
    OperationalMigrationRepository,
    operational_migration_repository,
)
from app.operational_migration.service import (
    MigrationRecordError,
    MigrationReport,
    ParentResolutionError,
)
from app.platform.permissions.authorization import AuthorizationContext

FinancialEntityType = Literal["estimate", "invoice", "payment"]
Disposition = Literal["accepted", "rejected", "duplicate", "unresolved"]


@dataclass(frozen=True)
class FinancialLineItemRecord:
    source_id: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    total_amount: Decimal


@dataclass(frozen=True)
class EstimateMigrationRecord:
    source_id: str
    source_job_id: str
    status: str
    currency: str
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    line_items: tuple[FinancialLineItemRecord, ...]
    presented_at: datetime | None = None
    expires_on: date | None = None
    external_metadata: dict[str, object] | None = None


@dataclass(frozen=True)
class InvoiceMigrationRecord:
    source_id: str
    source_job_id: str
    status: str
    currency: str
    subtotal_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    line_items: tuple[FinancialLineItemRecord, ...]
    issued_at: datetime | None = None
    due_on: date | None = None
    external_metadata: dict[str, object] | None = None


@dataclass(frozen=True)
class PaymentMigrationRecord:
    source_id: str
    source_invoice_id: str
    status: str
    currency: str
    amount: Decimal
    paid_at: datetime | None = None
    method: str | None = None
    reference: str | None = None
    external_metadata: dict[str, object] | None = None


@dataclass(frozen=True)
class FinancialMigrationProgress:
    run_id: UUID
    entity_type: FinancialEntityType
    source: int
    processed: int
    accepted: int
    rejected: int
    duplicate: int
    unresolved: int


@dataclass
class _Counts:
    source: int
    processed: int = 0
    accepted: int = 0
    rejected: int = 0
    duplicate: int = 0
    unresolved: int = 0

    def advance(self, disposition: Disposition) -> None:
        self.processed += 1
        setattr(self, disposition, getattr(self, disposition) + 1)


ExceptionRecord = tuple[FinancialEntityType, int, str | None, Disposition, str, str]


class FinancialMigrationService:
    """Provider-neutral Estimate, Invoice, and Payment migration orchestration."""

    def __init__(
        self,
        *,
        financial_service: FinancialService | None = None,
        repository: OperationalMigrationRepository = operational_migration_repository,
    ) -> None:
        self._financials = financial_service or FinancialService()
        self._repository = repository

    @staticmethod
    def _source_system(value: str) -> str:
        normalized = value.strip().lower()
        if not normalized or len(normalized) > 80:
            raise ValueError("source_system must contain 1 to 80 characters")
        return normalized

    @staticmethod
    def _validate_record(
        record: EstimateMigrationRecord
        | InvoiceMigrationRecord
        | PaymentMigrationRecord,
    ) -> None:
        if not record.source_id.strip() or len(record.source_id) > 191:
            raise MigrationRecordError(
                "Source identifier must contain 1 to 191 characters."
            )
        try:
            json.dumps(record.external_metadata or {}, sort_keys=True)
        except (TypeError, ValueError) as error:
            raise MigrationRecordError(
                "External metadata must be JSON serializable."
            ) from error

    @staticmethod
    def _digest(
        source_system: str,
        estimates: Sequence[EstimateMigrationRecord],
        invoices: Sequence[InvoiceMigrationRecord],
        payments: Sequence[PaymentMigrationRecord],
    ) -> str:
        payload = json.dumps(
            {
                "source_system": source_system,
                "estimates": [asdict(record) for record in estimates],
                "invoices": [asdict(record) for record in invoices],
                "payments": [asdict(record) for record in payments],
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    async def run(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        context: AuthorizationContext,
        source_system: str,
        estimates: Sequence[EstimateMigrationRecord],
        invoices: Sequence[InvoiceMigrationRecord],
        payments: Sequence[PaymentMigrationRecord],
        dry_run: bool,
        master_run_id: UUID | None = None,
        repair_of_run_id: UUID | None = None,
        repair_generation: int = 0,
        progress_callback: Callable[[FinancialMigrationProgress], None] | None = None,
    ) -> MigrationReport:
        source_system = self._source_system(source_system)
        if source_system == SOURCE4_SYSTEM and master_run_id is None:
            raise ValueError("SOURCE.4 financial import requires a master run")
        if source_system == SOURCE4_SYSTEM:
            require_sanctioned_context(context)
        if context.active_branch is None or not context.can_access_branch(
            context.active_branch.id
        ):
            raise ValueError("An authorized active Branch is required.")
        digest = self._digest(source_system, estimates, invoices, payments)
        async with factory() as session, session.begin():
            run = OperationalMigrationRun(
                company_id=context.company.id,
                branch_id=context.active_branch.id,
                initiated_by_user_id=context.user.id,
                master_run_id=master_run_id,
                master_domain="financial" if master_run_id is not None else None,
                repair_of_run_id=repair_of_run_id,
                repair_generation=repair_generation,
                source_system=source_system,
                source_digest=digest,
                mode="dry_run" if dry_run else "import",
                status="running",
            )
            await self._repository.create_run(session, run)
            run_id = run.id
        counts = {
            "estimate": _Counts(len(estimates)),
            "invoice": _Counts(len(invoices)),
            "payment": _Counts(len(payments)),
        }
        exceptions: list[ExceptionRecord] = []
        seen: dict[FinancialEntityType, set[str]] = {
            "estimate": set(),
            "invoice": set(),
            "payment": set(),
        }
        planned_invoices: dict[str, Invoice] = {}
        try:
            if dry_run:
                async with factory() as session:
                    transaction = await session.begin()
                    for index, estimate_record in enumerate(estimates, start=1):
                        async with session.begin_nested():
                            await self._estimate(
                                session,
                                context=context,
                                run_id=run_id,
                                source_system=source_system,
                                record=estimate_record,
                                index=index,
                                counts=counts["estimate"],
                                exceptions=exceptions,
                                seen=seen["estimate"],
                                persist=False,
                                callback=progress_callback,
                            )
                    for index, invoice_record in enumerate(invoices, start=1):
                        async with session.begin_nested():
                            await self._invoice(
                                session,
                                context=context,
                                run_id=run_id,
                                source_system=source_system,
                                record=invoice_record,
                                index=index,
                                counts=counts["invoice"],
                                exceptions=exceptions,
                                seen=seen["invoice"],
                                planned=planned_invoices,
                                persist=False,
                                callback=progress_callback,
                            )
                    for index, payment_record in enumerate(payments, start=1):
                        async with session.begin_nested():
                            await self._payment(
                                session,
                                context=context,
                                run_id=run_id,
                                source_system=source_system,
                                record=payment_record,
                                index=index,
                                counts=counts["payment"],
                                exceptions=exceptions,
                                seen=seen["payment"],
                                planned=planned_invoices,
                                persist=False,
                                callback=progress_callback,
                            )
                    await transaction.rollback()
            else:
                for index, estimate_record in enumerate(estimates, start=1):
                    async with factory() as session, session.begin():
                        await self._estimate(
                            session,
                            context=context,
                            run_id=run_id,
                            source_system=source_system,
                            record=estimate_record,
                            index=index,
                            counts=counts["estimate"],
                            exceptions=exceptions,
                            seen=seen["estimate"],
                            persist=True,
                            callback=progress_callback,
                        )
                for index, invoice_record in enumerate(invoices, start=1):
                    async with factory() as session, session.begin():
                        await self._invoice(
                            session,
                            context=context,
                            run_id=run_id,
                            source_system=source_system,
                            record=invoice_record,
                            index=index,
                            counts=counts["invoice"],
                            exceptions=exceptions,
                            seen=seen["invoice"],
                            planned=planned_invoices,
                            persist=True,
                            callback=progress_callback,
                        )
                for index, payment_record in enumerate(payments, start=1):
                    async with factory() as session, session.begin():
                        await self._payment(
                            session,
                            context=context,
                            run_id=run_id,
                            source_system=source_system,
                            record=payment_record,
                            index=index,
                            counts=counts["payment"],
                            exceptions=exceptions,
                            seen=seen["payment"],
                            planned=planned_invoices,
                            persist=True,
                            callback=progress_callback,
                        )
        except Exception:
            await self._finalize(
                factory,
                run_id=run_id,
                counts=counts,
                exceptions=exceptions,
                status="failed",
            )
            raise
        return await self._finalize(
            factory,
            run_id=run_id,
            counts=counts,
            exceptions=exceptions,
            status="completed",
        )

    async def _job_parent(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        source_system: str,
        source_job_id: str,
    ):
        assert context.active_branch is not None
        identity = await self._repository.get_job_identity(
            session,
            company_id=context.company.id,
            source_system=source_system,
            source_job_id=source_job_id,
        )
        if identity is None or identity.branch_id != context.active_branch.id:
            raise ParentResolutionError("Migrated Job parent was not found.")
        return identity

    async def _estimate(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        run_id: UUID,
        source_system: str,
        record: EstimateMigrationRecord,
        index: int,
        counts: _Counts,
        exceptions: list[ExceptionRecord],
        seen: set[str],
        persist: bool,
        callback: Callable[[FinancialMigrationProgress], None] | None,
    ) -> None:
        disposition: Disposition = "accepted"
        reason = detail = ""
        try:
            self._validate_record(record)
            if record.source_id in seen:
                disposition, reason, detail = (
                    "duplicate",
                    "duplicate_source_id_in_input",
                    "Estimate source identifier occurs more than once.",
                )
            else:
                seen.add(record.source_id)
                existing = await self._repository.get_estimate_identity(
                    session,
                    company_id=context.company.id,
                    source_system=source_system,
                    source_id=record.source_id,
                )
                if existing:
                    disposition, reason, detail = (
                        "duplicate",
                        "source_identity_exists",
                        "Estimate source identity already exists.",
                    )
                else:
                    parent = await self._job_parent(
                        session,
                        context=context,
                        source_system=source_system,
                        source_job_id=record.source_job_id,
                    )
                    estimate, items = await self._financials.stage_migrated_estimate(
                        session,
                        context=context,
                        command=MigrateEstimate(
                            branch_id=parent.branch_id,
                            job_id=parent.job_id,
                            status=record.status,
                            currency=record.currency,
                            subtotal_amount=record.subtotal_amount,
                            tax_amount=record.tax_amount,
                            total_amount=record.total_amount,
                            line_items=self._items(record.line_items),
                            presented_at=record.presented_at,
                            expires_on=record.expires_on,
                        ),
                    )
                    if persist:
                        identity = EstimateSourceIdentity(
                            id=uuid4(),
                            company_id=context.company.id,
                            branch_id=parent.branch_id,
                            estimate_id=estimate.id,
                            job_source_identity_id=parent.id,
                            job_id=parent.job_id,
                            customer_id=parent.customer_id,
                            service_location_id=parent.service_location_id,
                            source_system=source_system,
                            source_estimate_id=record.source_id,
                            source_status=record.status,
                            external_metadata=dict(record.external_metadata or {}),
                            first_run_id=run_id,
                        )
                        await self._repository.add_estimate_identity(
                            session,
                            identity,
                            [
                                EstimateLineItemSourceIdentity(
                                    company_id=context.company.id,
                                    estimate_source_identity_id=identity.id,
                                    estimate_id=estimate.id,
                                    estimate_line_item_id=item.id,
                                    source_system=source_system,
                                    source_line_item_id=source.source_id,
                                    first_run_id=run_id,
                                )
                                for source, item in zip(
                                    record.line_items, items, strict=True
                                )
                            ],
                        )
        except ParentResolutionError as error:
            disposition, reason, detail = "unresolved", "missing_parent", str(error)
        except (FinancialValidationError, MigrationRecordError) as error:
            disposition, reason, detail = "rejected", "validation_failed", str(error)
        self._result(
            run_id,
            "estimate",
            index,
            record.source_id,
            disposition,
            reason,
            detail,
            counts,
            exceptions,
            callback,
        )

    async def _invoice(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        run_id: UUID,
        source_system: str,
        record: InvoiceMigrationRecord,
        index: int,
        counts: _Counts,
        exceptions: list[ExceptionRecord],
        seen: set[str],
        planned: dict[str, Invoice],
        persist: bool,
        callback: Callable[[FinancialMigrationProgress], None] | None,
    ) -> None:
        disposition: Disposition = "accepted"
        reason = detail = ""
        try:
            self._validate_record(record)
            if record.source_id in seen:
                disposition, reason, detail = (
                    "duplicate",
                    "duplicate_source_id_in_input",
                    "Invoice source identifier occurs more than once.",
                )
            else:
                seen.add(record.source_id)
                existing = await self._repository.get_invoice_identity(
                    session,
                    company_id=context.company.id,
                    source_system=source_system,
                    source_id=record.source_id,
                )
                if existing:
                    disposition, reason, detail = (
                        "duplicate",
                        "source_identity_exists",
                        "Invoice source identity already exists.",
                    )
                else:
                    parent = await self._job_parent(
                        session,
                        context=context,
                        source_system=source_system,
                        source_job_id=record.source_job_id,
                    )
                    invoice, items = await self._financials.stage_migrated_invoice(
                        session,
                        context=context,
                        command=MigrateInvoice(
                            branch_id=parent.branch_id,
                            job_id=parent.job_id,
                            status=record.status,
                            currency=record.currency,
                            subtotal_amount=record.subtotal_amount,
                            tax_amount=record.tax_amount,
                            total_amount=record.total_amount,
                            line_items=self._items(record.line_items),
                            issued_at=record.issued_at,
                            due_on=record.due_on,
                        ),
                    )
                    planned[record.source_id] = invoice
                    if persist:
                        identity = InvoiceSourceIdentity(
                            id=uuid4(),
                            company_id=context.company.id,
                            branch_id=parent.branch_id,
                            invoice_id=invoice.id,
                            job_source_identity_id=parent.id,
                            job_id=parent.job_id,
                            customer_id=parent.customer_id,
                            service_location_id=parent.service_location_id,
                            source_system=source_system,
                            source_invoice_id=record.source_id,
                            source_status=record.status,
                            external_metadata=dict(record.external_metadata or {}),
                            first_run_id=run_id,
                        )
                        await self._repository.add_invoice_identity(
                            session,
                            identity,
                            [
                                InvoiceLineItemSourceIdentity(
                                    company_id=context.company.id,
                                    invoice_source_identity_id=identity.id,
                                    invoice_id=invoice.id,
                                    invoice_line_item_id=item.id,
                                    source_system=source_system,
                                    source_line_item_id=source.source_id,
                                    first_run_id=run_id,
                                )
                                for source, item in zip(
                                    record.line_items, items, strict=True
                                )
                            ],
                        )
        except ParentResolutionError as error:
            disposition, reason, detail = "unresolved", "missing_parent", str(error)
        except (FinancialValidationError, MigrationRecordError) as error:
            disposition, reason, detail = "rejected", "validation_failed", str(error)
        self._result(
            run_id,
            "invoice",
            index,
            record.source_id,
            disposition,
            reason,
            detail,
            counts,
            exceptions,
            callback,
        )

    async def _payment(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        run_id: UUID,
        source_system: str,
        record: PaymentMigrationRecord,
        index: int,
        counts: _Counts,
        exceptions: list[ExceptionRecord],
        seen: set[str],
        planned: dict[str, Invoice],
        persist: bool,
        callback: Callable[[FinancialMigrationProgress], None] | None,
    ) -> None:
        disposition: Disposition = "accepted"
        reason = detail = ""
        try:
            self._validate_record(record)
            if record.source_id in seen:
                disposition, reason, detail = (
                    "duplicate",
                    "duplicate_source_id_in_input",
                    "Payment source identifier occurs more than once.",
                )
            else:
                seen.add(record.source_id)
                existing = await self._repository.get_payment_identity(
                    session,
                    company_id=context.company.id,
                    source_system=source_system,
                    source_id=record.source_id,
                )
                if existing:
                    disposition, reason, detail = (
                        "duplicate",
                        "source_identity_exists",
                        "Payment source identity already exists.",
                    )
                else:
                    invoice_identity = await self._repository.get_invoice_identity(
                        session,
                        company_id=context.company.id,
                        source_system=source_system,
                        source_id=record.source_invoice_id,
                    )
                    invoice = planned.get(record.source_invoice_id)
                    if invoice_identity is None and invoice is None:
                        raise ParentResolutionError(
                            "Migrated Invoice parent was not found."
                        )
                    if invoice_identity is not None:
                        invoice_id = invoice_identity.invoice_id
                        branch_id = invoice_identity.branch_id
                    else:
                        assert invoice is not None
                        invoice_id = invoice.id
                        branch_id = invoice.branch_id
                    payment = await self._financials.stage_migrated_payment(
                        session,
                        context=context,
                        command=MigratePayment(
                            branch_id=branch_id,
                            invoice_id=invoice_id,
                            status=record.status,
                            currency=record.currency,
                            amount=record.amount,
                            paid_at=record.paid_at,
                            method=record.method,
                            reference=record.reference,
                        ),
                    )
                    if persist:
                        assert invoice_identity is not None
                        self._repository.add_payment_identity(
                            session,
                            PaymentSourceIdentity(
                                company_id=context.company.id,
                                branch_id=branch_id,
                                payment_id=payment.id,
                                invoice_source_identity_id=invoice_identity.id,
                                invoice_id=invoice_identity.invoice_id,
                                customer_id=invoice_identity.customer_id,
                                source_system=source_system,
                                source_payment_id=record.source_id,
                                source_status=record.status,
                                external_metadata=dict(record.external_metadata or {}),
                                first_run_id=run_id,
                            ),
                        )
        except ParentResolutionError as error:
            disposition, reason, detail = "unresolved", "missing_parent", str(error)
        except (FinancialValidationError, MigrationRecordError) as error:
            disposition, reason, detail = "rejected", "validation_failed", str(error)
        self._result(
            run_id,
            "payment",
            index,
            record.source_id,
            disposition,
            reason,
            detail,
            counts,
            exceptions,
            callback,
        )

    @staticmethod
    def _items(
        records: tuple[FinancialLineItemRecord, ...],
    ) -> tuple[MigratedLineItem, ...]:
        return tuple(
            MigratedLineItem(
                source_id=item.source_id,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_amount=item.total_amount,
            )
            for item in records
        )

    @staticmethod
    def _result(
        run_id: UUID,
        entity_type: FinancialEntityType,
        index: int,
        source_id: str,
        disposition: Disposition,
        reason: str,
        detail: str,
        counts: _Counts,
        exceptions: list[ExceptionRecord],
        callback: Callable[[FinancialMigrationProgress], None] | None,
    ) -> None:
        counts.advance(disposition)
        if disposition != "accepted":
            exceptions.append(
                (entity_type, index, source_id, disposition, reason, detail)
            )
        if callback:
            callback(
                FinancialMigrationProgress(
                    run_id=run_id,
                    entity_type=entity_type,
                    source=counts.source,
                    processed=counts.processed,
                    accepted=counts.accepted,
                    rejected=counts.rejected,
                    duplicate=counts.duplicate,
                    unresolved=counts.unresolved,
                )
            )

    async def _finalize(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        run_id: UUID,
        counts: dict[str, _Counts],
        exceptions: list[ExceptionRecord],
        status: str,
    ) -> MigrationReport:
        total = _Counts(sum(value.source for value in counts.values()))
        for value in counts.values():
            total.processed += value.processed
            total.accepted += value.accepted
            total.rejected += value.rejected
            total.duplicate += value.duplicate
            total.unresolved += value.unresolved
        async with factory() as session, session.begin():
            run = await self._repository.get_run_for_update(session, run_id)
            if run is None:
                raise RuntimeError("Operational migration run disappeared.")
            run.source_count = total.processed
            run.accepted_count = total.accepted
            run.rejected_count = total.rejected
            run.duplicate_count = total.duplicate
            run.unresolved_count = total.unresolved
            run.status = status
            run.completed_at = utc_now()
            for entity_type, value in counts.items():
                self._repository.add_progress(
                    session,
                    OperationalMigrationProgress(
                        run_id=run_id,
                        entity_type=entity_type,
                        source_count=value.source,
                        processed_count=value.processed,
                        accepted_count=value.accepted,
                        rejected_count=value.rejected,
                        duplicate_count=value.duplicate,
                        unresolved_count=value.unresolved,
                    ),
                )
            for (
                entity_type,
                index,
                source_id,
                disposition,
                reason,
                detail,
            ) in exceptions:
                self._repository.add_exception(
                    session,
                    OperationalMigrationException(
                        run_id=run_id,
                        entity_type=entity_type,
                        record_index=index,
                        source_id_sha256=(
                            hashlib.sha256(source_id.encode()).hexdigest()
                            if source_id
                            else None
                        ),
                        disposition=disposition,
                        reason_code=reason,
                        detail=detail,
                    ),
                )
        return MigrationReport(
            run_id=run_id,
            mode=run.mode,
            source=total.processed,
            accepted=total.accepted,
            rejected=total.rejected,
            duplicate=total.duplicate,
            unresolved=total.unresolved,
        )
