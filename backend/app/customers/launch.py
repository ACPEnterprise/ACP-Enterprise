from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.customers.detail import customer_detail_service
from app.customers.errors import CustomerNotFoundError
from app.customers.models import (
    Customer,
    CustomerContact,
    CustomerNote,
)
from app.customers.normalization import (
    build_normalized_address,
    build_normalized_name,
    normalize_email,
    normalize_phone,
    normalize_search_text,
)
from app.customers.repository import CustomerRepository
from app.customers.schemas import (
    CustomerConsentCreate,
    CustomerConsentResponse,
    CustomerIntakeCreate,
    CustomerIntakeResponse,
    CustomerNoteCreate,
    CustomerResponse,
    DuplicateCheckRequest,
    DuplicateCheckResponse,
    DuplicateMatchResponse,
)
from app.events.models import BusinessEvent
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.permissions.authorization import AuthorizationContext


class CustomerLaunchService:
    @staticmethod
    def _validate_scope(context: AuthorizationContext) -> None:
        branch = context.active_branch
        if branch is not None and branch.company_id != context.company.id:
            raise CustomerNotFoundError(branch.id)

    @staticmethod
    def _event(
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        event_type: EventType,
        entity_type: str,
        entity_id: UUID,
        payload: dict[str, object],
    ) -> BusinessEvent:
        return BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                company_id=context.company.id,
                branch_id=context.active_branch.id if context.active_branch else None,
                user_id=context.user.id,
                payload=payload,
            ),
        )

    async def duplicate_check(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: DuplicateCheckRequest,
    ) -> DuplicateCheckResponse:
        self._validate_scope(context)
        records = list(
            (
                await session.scalars(
                    select(Customer)
                    .where(
                        Customer.company_id == context.company.id,
                        Customer.archived_at.is_(None),
                    )
                    .options(
                        selectinload(Customer.contacts),
                        selectinload(Customer.locations),
                    )
                    .order_by(Customer.customer_number, Customer.id)
                )
            ).all()
        )
        requested_name = build_normalized_name(
            data.first_name, data.last_name, data.business_name
        )
        requested_phone = normalize_phone(data.phone) if data.phone else None
        requested_email = normalize_email(data.email) if data.email else None
        requested_address = (
            build_normalized_address(
                data.address_line_1,
                data.address_line_2,
                data.city,
                data.state,
                data.postal_code,
            )
            if data.address_line_1 and data.city and data.state and data.postal_code
            else None
        )
        matches: list[DuplicateMatchResponse] = []
        for customer in records:
            reasons: list[str] = []
            if requested_name and customer.normalized_name:
                ratio = SequenceMatcher(
                    None, requested_name, customer.normalized_name
                ).ratio()
                if ratio >= 0.8:
                    reasons.append("name")
            contact_phones = {
                value
                for contact in customer.contacts
                for value in (
                    contact.normalized_mobile_phone,
                    contact.normalized_office_phone,
                )
                if value
            }
            contact_emails = {
                contact.normalized_email
                for contact in customer.contacts
                if contact.normalized_email
            }
            if requested_phone and requested_phone in contact_phones:
                reasons.append("phone")
            if requested_email and requested_email in contact_emails:
                reasons.append("email")
            if requested_address and any(
                location.normalized_address == requested_address
                for location in customer.locations
            ):
                reasons.append("address")
            if reasons:
                customer_data = CustomerResponse.model_validate(customer).model_dump()
                matches.append(DuplicateMatchResponse(**customer_data, reasons=reasons))
        return DuplicateCheckResponse(matches=matches)

    async def intake(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: CustomerIntakeCreate,
    ) -> CustomerIntakeResponse:
        self._validate_scope(context)
        duplicates = await self.duplicate_check(
            session,
            context=context,
            data=DuplicateCheckRequest(
                first_name=data.first_name,
                last_name=data.last_name,
                business_name=data.business_name,
                phone=data.primary_phone,
                email=data.email,
            ),
        )
        await session.rollback()
        display_name = data.business_name or f"{data.first_name} {data.last_name}"
        customer_type = (
            "residential"
            if data.customer_type == "individual"
            else "commercial"
            if data.customer_type == "business"
            else data.customer_type
        )
        async with session.begin():
            number = await CustomerRepository.next_customer_number(
                session, context.company.id
            )
            customer = Customer(
                company_id=context.company.id,
                customer_number=number,
                status=data.status.value,
                customer_type=customer_type,
                display_name=display_name,
                preferred_contact_method=data.preferred_contact_method.value,
                marketing_source=data.source,
                notes=data.internal_notes,
                first_name=data.first_name,
                last_name=data.last_name,
                business_name=data.business_name,
                normalized_name=normalize_search_text(display_name),
                primary_phone=data.primary_phone,
                normalized_primary_phone=normalize_phone(data.primary_phone),
                secondary_phone=data.secondary_phone,
                normalized_secondary_phone=(
                    normalize_phone(data.secondary_phone)
                    if data.secondary_phone
                    else None
                ),
                email=data.email,
                normalized_email=normalize_email(data.email) if data.email else None,
                is_vip=data.is_vip,
            )
            session.add(customer)
            await session.flush()
            contact = CustomerContact(
                customer_id=customer.id,
                first_name=data.first_name or data.business_name or "Primary",
                last_name=data.last_name or "Contact",
                email=data.email,
                normalized_email=normalize_email(data.email) if data.email else None,
                mobile_phone=data.primary_phone,
                normalized_mobile_phone=normalize_phone(data.primary_phone),
                is_preferred=True,
                active=True,
            )
            session.add(contact)
            await session.flush()
            customer.primary_contact_id = contact.id
            self._event(
                session,
                context=context,
                event_type=EventType.CUSTOMER_CREATED,
                entity_type="customer",
                entity_id=customer.id,
                payload={
                    "customer_number": number,
                    "customer_type": customer_type,
                    "status": data.status.value,
                    "origin": "crm_intake",
                },
            )
            self._event(
                session,
                context=context,
                event_type=EventType.CONTACT_CREATED,
                entity_type="contact",
                entity_id=contact.id,
                payload={"customer_id": str(customer.id), "is_preferred": True},
            )
        detail = await customer_detail_service.get_detail(
            session, context=context, customer_id=customer.id
        )
        return CustomerIntakeResponse(
            customer=detail, duplicate_warnings=duplicates.matches
        )

    async def add_note(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer_id: UUID,
        data: CustomerNoteCreate,
    ) -> CustomerNote:
        self._validate_scope(context)
        async with session.begin():
            customer = await CustomerRepository.get(
                session,
                company_id=context.company.id,
                customer_id=customer_id,
                for_update=True,
            )
            if customer is None:
                raise CustomerNotFoundError(customer_id)
            note = CustomerNote(
                customer_id=customer.id,
                author_user_id=context.user.id,
                body=data.body,
            )
            session.add(note)
            await session.flush()
            self._event(
                session,
                context=context,
                event_type=EventType.CUSTOMER_NOTE_ADDED,
                entity_type="customer_note",
                entity_id=note.id,
                payload={"customer_id": str(customer.id)},
            )
        return note

    async def record_consent(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer_id: UUID,
        data: CustomerConsentCreate,
    ) -> CustomerConsentResponse:
        self._validate_scope(context)
        async with session.begin():
            customer = await CustomerRepository.get(
                session,
                company_id=context.company.id,
                customer_id=customer_id,
                for_update=True,
            )
            if customer is None:
                raise CustomerNotFoundError(customer_id)
            event = self._event(
                session,
                context=context,
                event_type=EventType.CUSTOMER_CONSENT_RECORDED,
                entity_type="customer",
                entity_id=customer.id,
                payload={
                    "customer_id": str(customer.id),
                    "channel": data.channel.value,
                    "decision": data.decision.value,
                    "source": data.source,
                    "reason": data.reason,
                },
            )
            await session.flush()
        return CustomerConsentResponse(
            id=event.id,
            customer_id=customer.id,
            channel=data.channel,
            decision=data.decision,
            source=data.source,
            reason=data.reason,
            recorded_at=event.occurred_at,
            recorded_by_user_id=event.user_id,
            branch_id=event.branch_id,
        )

    async def list_consents(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        customer_id: UUID,
    ) -> list[CustomerConsentResponse]:
        self._validate_scope(context)
        customer = await CustomerRepository.get(
            session, company_id=context.company.id, customer_id=customer_id
        )
        if customer is None:
            raise CustomerNotFoundError(customer_id)
        events = list(
            (
                await session.scalars(
                    select(BusinessEvent)
                    .where(
                        BusinessEvent.company_id == context.company.id,
                        BusinessEvent.entity_id == customer.id,
                        BusinessEvent.event_type
                        == EventType.CUSTOMER_CONSENT_RECORDED.value,
                    )
                    .order_by(BusinessEvent.occurred_at.desc(), BusinessEvent.id.desc())
                )
            ).all()
        )
        return [
            CustomerConsentResponse(
                id=event.id,
                customer_id=customer.id,
                channel=event.payload["channel"],
                decision=event.payload["decision"],
                source=event.payload["source"],
                reason=event.payload.get("reason"),
                recorded_at=event.occurred_at,
                recorded_by_user_id=event.user_id,
                branch_id=event.branch_id,
            )
            for event in events
        ]


customer_launch_service = CustomerLaunchService()
