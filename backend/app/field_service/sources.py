"""Minimum-necessary assignment-scoped projections for ACP Employee."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.models import CustomerContact
from app.dispatch.models import DispatchAssignment, DispatchCrewMember
from app.estimates.models import Estimate, EstimateJobConversion, EstimateRevision
from app.field_service.errors import FieldServiceNotFound
from app.field_service.schemas import (
    CompletedFieldHistory,
    CompletedFieldJob,
    FieldAsset,
    FieldAssetHistory,
    FieldCapabilityGate,
    FieldCommunicationState,
    FieldContact,
    FieldEstimate,
    FieldFleetAsset,
    FieldInvoice,
    FieldJobSources,
    FieldPaymentState,
    FieldPriceBookItem,
    FieldReadiness,
)
from app.invoicing.models import Invoice
from app.jobs.models import Job
from app.operational_assets.models import Asset, AssetEvidence, AssetRelationship
from app.payments.models import PaymentIntent, PaymentReceipt
from app.platform.notifications.models import NotificationOutbox
from app.platform.permissions.authorization import AuthorizationContext
from app.price_book.models import PriceBookPriceVersion, PriceBookServiceItem

from .service import FieldService


class FieldSourceService:
    def __init__(self, field: FieldService) -> None:
        self.field = field

    async def job_sources(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
    ) -> FieldJobSources:
        assignment = await self.field._assigned_job(session, context, job_id)
        job = await session.scalar(
            select(Job).where(
                Job.company_id == context.company.id,
                Job.branch_id == assignment.branch_id,
                Job.id == job_id,
            )
        )

        if job is None:
            raise FieldServiceNotFound("Assigned field Job was not found.")
        contact = await self._contact(session, job.customer_id)
        equipment = await self._equipment(
            session,
            context=context,
            branch_id=assignment.branch_id,
            job=job,
        )
        employee = await self.field._employee(session, context)
        fleet = await self._fleet(
            session,
            company_id=context.company.id,
            branch_id=assignment.branch_id,
            employee_id=employee.id,
        )
        estimates = await self._estimates(session, context.company.id, job_id)
        invoice_record = await session.scalar(
            select(Invoice)
            .where(
                Invoice.company_id == context.company.id,
                Invoice.branch_id == assignment.branch_id,
                Invoice.job_id == job_id,
            )
            .order_by(Invoice.created_at.desc())
            .limit(1)
        )
        invoice = self._invoice(invoice_record)
        payment = await self._payment(session, context.company.id, invoice_record)
        communications = await self._communications(
            session, context.company.id, job_id
        )
        completion = await self.field.state(session, context=context, job_id=job_id)
        return FieldJobSources(
            job_id=job.id,
            assignment_id=assignment.id,
            assignment_version=assignment.version,
            customer_id=job.customer_id,
            service_location_id=job.service_location_id,
            contact=contact,
            equipment=equipment,
            fleet=fleet,
            estimates=estimates,
            invoice=invoice,
            payment=payment,
            communications=communications,
            completion=completion,
            gates=self._gates(
                equipment=equipment,
                fleet=fleet,
                estimates=estimates,
                invoice=invoice,
            ),
        )

    @classmethod
    def readiness(cls) -> FieldReadiness:
        return FieldReadiness(
            capabilities=cls._gates(
                equipment=(), fleet=(), estimates=(), invoice=None
            ),
            authorization_root=(
                "authenticated_user→membership→employee→branch→assignment→permission"
            ),
            mutation_recovery="reconcile_authoritative_state_before_retry",
        )

    async def price_book(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
        limit: int,
    ) -> tuple[FieldPriceBookItem, ...]:
        assignment = await self.field._assigned_job(session, context, job_id)
        records = (
            await session.execute(
                select(PriceBookServiceItem, PriceBookPriceVersion)
                .join(
                    PriceBookPriceVersion,
                    (PriceBookPriceVersion.company_id == PriceBookServiceItem.company_id)
                    & (PriceBookPriceVersion.id == PriceBookServiceItem.current_version_id),
                )
                .where(
                    PriceBookServiceItem.company_id == context.company.id,
                    PriceBookServiceItem.status == "active",
                    or_(
                        PriceBookServiceItem.branch_id.is_(None),
                        PriceBookServiceItem.branch_id == assignment.branch_id,
                    ),
                    PriceBookPriceVersion.status == "active",
                    or_(
                        PriceBookPriceVersion.branch_id.is_(None),
                        PriceBookPriceVersion.branch_id == assignment.branch_id,
                    ),
                )
                .order_by(PriceBookServiceItem.name, PriceBookServiceItem.id)
                .limit(limit)
            )
        ).all()
        return tuple(
            FieldPriceBookItem(
                item_id=item.id,
                code=item.code,
                name=item.name,
                customer_description=item.customer_description,
                price_version_id=version.id,
                unit_price=version.unit_price,
                currency=version.currency,
            )
            for item, version in records
        )

    async def completed_history(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        limit: int,
    ) -> CompletedFieldHistory:
        employee = await self.field._employee(session, context)
        crew_assignment_ids = select(DispatchCrewMember.assignment_id).where(
            DispatchCrewMember.company_id == context.company.id,
            DispatchCrewMember.employee_id == employee.id,
        )
        rows = (
            await session.execute(
                select(Job, DispatchAssignment)
                .join(
                    DispatchAssignment,
                    (DispatchAssignment.company_id == Job.company_id)
                    & (DispatchAssignment.job_id == Job.id),
                )
                .where(
                    Job.company_id == context.company.id,
                    Job.branch_id.in_(context.authorized_branch_ids),
                    Job.status.in_(("completed", "closed")),
                    or_(
                        DispatchAssignment.primary_employee_id == employee.id,
                        DispatchAssignment.id.in_(crew_assignment_ids),
                    ),
                )
                .order_by(Job.updated_at.desc(), Job.id)
                .limit(limit)
            )
        ).all()
        return CompletedFieldHistory(
            items=tuple(
                CompletedFieldJob(
                    job_id=job.id,
                    job_number=job.job_number,
                    branch_id=job.branch_id,
                    status=job.status,
                    completed_at=job.updated_at,
                )
                for job, _assignment in rows
            )
        )

    @staticmethod
    async def _contact(session: AsyncSession, customer_id: UUID) -> FieldContact | None:
        contact = await session.scalar(
            select(CustomerContact)
            .where(
                CustomerContact.customer_id == customer_id,
                CustomerContact.active.is_(True),
                CustomerContact.archived_at.is_(None),
            )
            .order_by(CustomerContact.is_preferred.desc(), CustomerContact.created_at)
            .limit(1)
        )
        if contact is None:
            return None
        return FieldContact(
            contact_id=contact.id,
            display_name=f"{contact.first_name} {contact.last_name}".strip(),
            phone=contact.mobile_phone or contact.office_phone,
            email=contact.email,
            can_approve_work=contact.can_approve_work,
        )

    @staticmethod
    async def _equipment(
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        branch_id: UUID,
        job: Job,
    ) -> tuple[FieldAsset, ...]:
        customer_assets = select(AssetRelationship.asset_id).where(
            AssetRelationship.company_id == context.company.id,
            AssetRelationship.relationship_type == "customer",
            AssetRelationship.related_entity_id == job.customer_id,
            AssetRelationship.valid_to.is_(None),
        )
        location_assets = select(AssetRelationship.asset_id).where(
            AssetRelationship.company_id == context.company.id,
            AssetRelationship.relationship_type == "service_location",
            AssetRelationship.related_entity_id == job.service_location_id,
            AssetRelationship.valid_to.is_(None),
        )
        assets = tuple(
            (
                await session.scalars(
                    select(Asset)
                    .where(
                        Asset.company_id == context.company.id,
                        Asset.branch_id == branch_id,
                        Asset.asset_class == "customer_equipment",
                        Asset.id.in_(customer_assets),
                        Asset.id.in_(location_assets),
                    )
                    .order_by(Asset.display_name, Asset.id)
                    .limit(50)
                )
            ).all()
        )
        result: list[FieldAsset] = []
        for asset in assets:
            evidence = tuple(
                (
                    await session.scalars(
                        select(AssetEvidence)
                        .where(
                            AssetEvidence.company_id == context.company.id,
                            AssetEvidence.asset_id == asset.id,
                            AssetEvidence.evidence_type.in_(
                                ("manufacturer", "model", "warranty", "job_service")
                            ),
                        )
                        .order_by(AssetEvidence.occurred_at.desc(), AssetEvidence.id)
                        .limit(25)
                    )
                ).all()
            )
            manufacturer = next(
                (str(e.value.get("display") or e.value.get("value")) for e in evidence if e.evidence_type == "manufacturer"),
                None,
            )
            model = next(
                (str(e.value.get("display") or e.value.get("value")) for e in evidence if e.evidence_type == "model"),
                None,
            )
            warranty = next((e.state for e in evidence if e.evidence_type == "warranty"), "insufficient_evidence")
            history = tuple(
                FieldAssetHistory(
                    evidence_id=e.id,
                    evidence_type=e.evidence_type,
                    state=e.state,
                    occurred_at=e.occurred_at,
                )
                for e in evidence
                if e.evidence_type == "job_service"
            )
            result.append(
                FieldAsset(
                    asset_id=asset.id,
                    display_name=asset.display_name,
                    asset_class=asset.asset_class,
                    lifecycle=asset.lifecycle,
                    manufacturer=manufacturer,
                    model=model,
                    warranty_readiness=warranty,
                    service_history=history,
                )
            )
        return tuple(result)

    @staticmethod
    async def _fleet(
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID,
        employee_id: UUID,
    ) -> tuple[FieldFleetAsset, ...]:
        asset_ids = select(AssetRelationship.asset_id).where(
            AssetRelationship.company_id == company_id,
            AssetRelationship.branch_id == branch_id,
            AssetRelationship.relationship_type == "employee_custody",
            AssetRelationship.related_entity_id == employee_id,
            AssetRelationship.valid_to.is_(None),
        )
        assets = tuple(
            (
                await session.scalars(
                    select(Asset)
                    .where(
                        Asset.company_id == company_id,
                        Asset.branch_id == branch_id,
                        Asset.id.in_(asset_ids),
                        Asset.asset_class.in_(("vehicle", "tool", "equipment")),
                    )
                    .order_by(Asset.asset_class, Asset.display_name)
                    .limit(50)
                )
            ).all()
        )
        return tuple(
            FieldFleetAsset(
                asset_id=asset.id,
                display_name=asset.display_name,
                lifecycle=asset.lifecycle,
                readiness="ready" if asset.lifecycle == "active" else "attention_required",
            )
            for asset in assets
        )

    @staticmethod
    async def _estimates(
        session: AsyncSession, company_id: UUID, job_id: UUID
    ) -> tuple[FieldEstimate, ...]:
        rows = (
            await session.execute(
                select(Estimate, EstimateRevision)
                .join(
                    EstimateJobConversion,
                    (EstimateJobConversion.company_id == Estimate.company_id)
                    & (EstimateJobConversion.estimate_id == Estimate.id),
                )
                .join(
                    EstimateRevision,
                    (EstimateRevision.company_id == Estimate.company_id)
                    & (EstimateRevision.id == Estimate.current_revision_id),
                )
                .where(
                    Estimate.company_id == company_id,
                    EstimateJobConversion.job_id == job_id,
                )
                .order_by(Estimate.updated_at.desc())
                .limit(20)
            )
        ).all()
        return tuple(
            FieldEstimate(
                estimate_id=estimate.id,
                estimate_number=estimate.estimate_number,
                status=estimate.status,
                acceptance_status=estimate.acceptance_status,
                revision_id=revision.id,
                revision_number=revision.revision_number,
                title=revision.proposal_title,
                total_amount=revision.total_amount,
                currency=revision.currency,
            )
            for estimate, revision in rows
        )

    @staticmethod
    def _invoice(invoice: Invoice | None) -> FieldInvoice | None:
        if invoice is None:
            return None
        return FieldInvoice(
            invoice_id=invoice.id,
            invoice_number=invoice.invoice_number,
            status=invoice.status,
            version=invoice.version,
            open_amount=invoice.open_amount,
            currency=invoice.currency,
        )

    @staticmethod
    async def _payment(
        session: AsyncSession, company_id: UUID, invoice: Invoice | None
    ) -> FieldPaymentState:
        if invoice is None:
            return FieldPaymentState(
                state="invoice_not_available",
                invoice_id=None,
                open_amount=None,
                currency=None,
                receipt_status=None,
            )
        intent = await session.scalar(
            select(PaymentIntent)
            .where(
                PaymentIntent.company_id == company_id,
                PaymentIntent.invoice_id == invoice.id,
            )
            .order_by(PaymentIntent.created_at.desc())
            .limit(1)
        )
        receipt = (
            await session.scalar(
                select(PaymentReceipt)
                .where(
                    PaymentReceipt.company_id == company_id,
                    PaymentReceipt.intent_id == intent.id,
                )
                .limit(1)
            )
            if intent
            else None
        )
        return FieldPaymentState(
            state=intent.status if intent else "no_accepted_payment_evidence",
            invoice_id=invoice.id,
            open_amount=invoice.open_amount,
            currency=invoice.currency,
            receipt_status=receipt.status if receipt else None,
        )

    @staticmethod
    async def _communications(
        session: AsyncSession, company_id: UUID, job_id: UUID
    ) -> tuple[FieldCommunicationState, ...]:
        records = tuple(
            (
                await session.scalars(
                    select(NotificationOutbox)
                    .where(
                        NotificationOutbox.company_id == company_id,
                        NotificationOutbox.notification_type.like("communications.%"),
                        NotificationOutbox.payload["source_entity_id"].astext
                        == str(job_id),
                    )
                    .order_by(NotificationOutbox.created_at.desc())
                    .limit(25)
                )
            ).all()
        )
        return tuple(
            FieldCommunicationState(
                communication_id=record.id,
                message_class=str(record.payload.get("communication_type", "unknown")),
                channel=record.channel or "unknown",
                state=("delivered" if record.status == "sent" else "uncertain" if record.status == "ambiguous" else record.status),
                created_at=record.created_at,
            )
            for record in records
        )

    @staticmethod
    def _gates(
        *,
        equipment: tuple[FieldAsset, ...],
        fleet: tuple[FieldFleetAsset, ...],
        estimates: tuple[FieldEstimate, ...],
        invoice: FieldInvoice | None,
    ) -> tuple[FieldCapabilityGate, ...]:
        return (
            FieldCapabilityGate(capability="equipment", state="READY", reason="Assignment-scoped Asset authority is available."),
            FieldCapabilityGate(capability="attachments", state="PROVIDER_REQUIRED", reason="Artifact metadata custody is ready; an accepted protected-storage provider is required for bytes."),
            FieldCapabilityGate(capability="estimate_projection", state="READY", reason="Exact converted Estimate revisions are available."),
            FieldCapabilityGate(capability="estimate_creation", state="SOURCE_REQUIRED", reason="Technician commercial command permission is not accepted."),
            FieldCapabilityGate(capability="customer_authorization", state="POLICY_REQUIRED", reason="Current disposition evidence is not a legal signature policy."),
            FieldCapabilityGate(capability="invoice", state="READY", reason="Field-safe Invoice state is available."),
            FieldCapabilityGate(capability="payment", state="READY", reason="Read-only provider-neutral Payment state is available."),
            FieldCapabilityGate(capability="notifications", state="SOURCE_REQUIRED", reason="In-app Employee notification authority is not yet accepted."),
            FieldCapabilityGate(capability="communications", state="PROVIDER_REQUIRED", reason="Intent/status is available; real delivery requires provider admission."),
            FieldCapabilityGate(capability="fleet", state="READY", reason="Own-custody Assets are assignment scoped."),
            FieldCapabilityGate(capability="inspections", state="POLICY_REQUIRED", reason="Inspection definition and cadence must be configured."),
        )


field_source_service = FieldSourceService(FieldService())
