import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.normalization import normalize_email, normalize_phone
from app.events.models import BusinessEvent
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.notifications.models import NotificationOutbox
from app.platform.notifications.repository import NotificationOutboxRepository
from app.platform.permissions.authorization import AuthorizationContext

from .catalog import OPERATIONAL_MESSAGE_CATALOG
from .contracts import (
    CommunicationEvidence,
    CommunicationPolicy,
    CommunicationRequest,
)
from .errors import (
    CommunicationAuthorizationError,
    CommunicationConflictError,
    CommunicationNotFoundError,
    CommunicationValidationError,
)
from .repository import CommunicationRepository, communication_repository
from .suppression import destination_digest
from .types import CommunicationChannel, CommunicationDeliveryState, CommunicationType

LEGACY_POLICIES = {
    CommunicationType.APPOINTMENT_CONFIRMATION: CommunicationPolicy(
        CommunicationType.APPOINTMENT_CONFIRMATION,
        frozenset({"appointment.booked"}),
        "appointment-confirmation-v1",
    ),
    CommunicationType.APPOINTMENT_REMINDER: CommunicationPolicy(
        CommunicationType.APPOINTMENT_REMINDER,
        frozenset({"appointment.booked", "appointment.rescheduled"}),
        "appointment-reminder-v1",
    ),
    CommunicationType.APPOINTMENT_RESCHEDULED: CommunicationPolicy(
        CommunicationType.APPOINTMENT_RESCHEDULED,
        frozenset({"appointment.rescheduled"}),
        "appointment-rescheduled-v1",
    ),
    CommunicationType.APPOINTMENT_CANCELLED: CommunicationPolicy(
        CommunicationType.APPOINTMENT_CANCELLED,
        frozenset({"appointment.cancelled"}),
        "appointment-cancelled-v1",
    ),
    CommunicationType.TECHNICIAN_EN_ROUTE: CommunicationPolicy(
        CommunicationType.TECHNICIAN_EN_ROUTE,
        frozenset({"technician.en_route"}),
        "technician-en-route-v1",
    ),
    CommunicationType.TECHNICIAN_ARRIVED: CommunicationPolicy(
        CommunicationType.TECHNICIAN_ARRIVED,
        frozenset({"technician.arrived"}),
        "technician-arrived-v1",
    ),
    CommunicationType.ESTIMATE_ACTION_REQUESTED: CommunicationPolicy(
        CommunicationType.ESTIMATE_ACTION_REQUESTED,
        frozenset({"estimate.sent"}),
        "estimate-action-requested-v1",
    ),
    CommunicationType.ESTIMATE_STATUS_NOTICE: CommunicationPolicy(
        CommunicationType.ESTIMATE_STATUS_NOTICE,
        frozenset({"estimate.approved", "estimate.rejected", "estimate.expired"}),
        "estimate-status-notice-v1",
    ),
}
POLICIES = LEGACY_POLICIES
REQUEST_POLICIES = OPERATIONAL_MESSAGE_CATALOG


def _canonical_digest(value: dict[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class CommunicationService:
    def __init__(self, repository: CommunicationRepository) -> None:
        self.repository = repository

    @staticmethod
    def _validate_branch(context: AuthorizationContext, branch_id: UUID) -> None:
        if not context.can_access_branch(branch_id):
            raise CommunicationAuthorizationError("Branch access denied.")

    @staticmethod
    def _recipient(contact: object, channel: CommunicationChannel) -> str:
        if channel is CommunicationChannel.EMAIL:
            raw = getattr(contact, "normalized_email", None) or getattr(
                contact, "email", None
            )
            try:
                recipient = normalize_email(raw) if raw else None
            except ValueError as error:
                raise CommunicationValidationError(
                    "The selected contact has no valid email recipient."
                ) from error
        else:
            raw = getattr(contact, "normalized_mobile_phone", None) or getattr(
                contact, "mobile_phone", None
            )
            try:
                recipient = normalize_phone(raw) if raw else None
            except ValueError as error:
                raise CommunicationValidationError(
                    "The selected contact has no valid SMS recipient."
                ) from error
        if not recipient:
            raise CommunicationValidationError(
                f"The selected contact has no valid {channel.value} recipient."
            )
        return recipient

    @staticmethod
    def _recipient_display(recipient: str, channel: CommunicationChannel) -> str:
        if channel is CommunicationChannel.EMAIL:
            local, _, domain = recipient.partition("@")
            return f"{local[:1]}***@{domain}" if local and domain else "masked email"
        return f"***{recipient[-4:]}" if len(recipient) >= 4 else "masked SMS"

    @staticmethod
    def _validate_source_customer(
        source: BusinessEvent, customer_id: UUID, authoritative_customer_id: UUID | None
    ) -> None:
        recorded_customer = source.payload.get("customer_id")
        if authoritative_customer_id is None:
            raise CommunicationValidationError(
                "Source-domain Customer authority could not be resolved."
            )
        if authoritative_customer_id != customer_id or (
            recorded_customer is not None
            and str(recorded_customer) != str(authoritative_customer_id)
        ):
            raise CommunicationValidationError(
                "Source-domain evidence does not belong to the customer."
            )

    async def request(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        request: CommunicationRequest,
    ) -> CommunicationEvidence:
        self._validate_branch(context, request.branch_id)
        policy = REQUEST_POLICIES.get(request.communication_type)
        if policy is None:
            raise CommunicationValidationError("Unsupported communication type.")
        if request.channel not in policy.allowed_channels:
            raise CommunicationValidationError(
                "Communication channel is not allowed for this message class."
            )
        if request.channel not in {
            CommunicationChannel.EMAIL,
            CommunicationChannel.SMS,
        }:
            raise CommunicationValidationError(
                "General communication requests support Email and SMS only."
            )
        source = await self.repository.source_event(
            session,
            event_id=request.source_event_id,
            company_id=context.company.id,
            branch_id=request.branch_id,
        )
        if source is None:
            raise CommunicationNotFoundError("Source-domain evidence was not found.")
        if source.event_type not in policy.source_event_types:
            raise CommunicationValidationError(
                "Source-domain evidence does not support this communication type."
            )
        source_customer_id = await self.repository.source_customer_id(
            session,
            source=source,
            company_id=context.company.id,
            branch_id=request.branch_id,
        )
        self._validate_source_customer(source, request.customer_id, source_customer_id)
        contact_record = await self.repository.customer_contact(
            session,
            company_id=context.company.id,
            customer_id=request.customer_id,
            contact_id=request.contact_id,
        )
        if contact_record is None:
            raise CommunicationNotFoundError("Customer contact was not found.")
        _, contact = contact_record
        recipient = self._recipient(contact, request.channel)
        if await self.repository.is_recipient_suppressed(
            session,
            company_id=context.company.id,
            channel=request.channel,
            destination_digest_value=destination_digest(recipient),
            purpose=policy.purpose,
        ):
            raise CommunicationAuthorizationError(
                "Current recipient suppression prohibits this communication."
            )
        consent = await self.repository.latest_consent(
            session,
            company_id=context.company.id,
            customer_id=request.customer_id,
            channel=request.channel.value,
        )
        if policy.consent_required and (
            consent is None or consent.payload.get("decision") != "granted"
        ):
            raise CommunicationAuthorizationError(
                "Current customer consent is required for this channel."
            )

        normalized_key = request.request_key.strip()
        if not normalized_key:
            raise CommunicationValidationError("Request key must not be blank.")
        identity_facts: dict[str, object] = {
            "version": 1,
            "company_id": str(context.company.id),
            "branch_id": str(request.branch_id),
            "communication_type": request.communication_type.value,
            "channel": request.channel.value,
            "customer_id": str(request.customer_id),
            "contact_id": str(request.contact_id),
            "source_event_id": str(source.id),
            "request_key": normalized_key,
        }
        request_identity = f"communications:v1:{_canonical_digest(identity_facts)}"
        request_facts = {
            **identity_facts,
            "recipient": recipient,
            "scheduled_at": request.scheduled_at.isoformat(),
            "source_event_type": source.event_type,
            "source_entity_type": source.entity_type,
            "source_entity_id": str(source.entity_id) if source.entity_id else None,
            "consent_event_id": str(consent.id) if consent else None,
            "communication_purpose": policy.purpose.value,
        }
        request_digest = _canonical_digest(request_facts)
        payload: dict[str, object] = {
            **request_facts,
            "request_digest": request_digest,
            "requested_by": str(context.user.id),
        }
        source_correlation_id = source.correlation_id
        source_event_id = source.id
        source_event_type = source.event_type
        now = datetime.now(timezone.utc)
        # Scope/evidence reads start an implicit transaction. End that read-only
        # transaction before the atomic outbox enqueue boundary.
        await session.rollback()
        async with session.begin():
            record, created = await NotificationOutboxRepository.enqueue(
                session,
                notification_type=f"communications.{request.communication_type.value}",
                template_identifier=policy.template_identifier,
                recipient=recipient,
                payload=payload,
                correlation_id=source_correlation_id,
                idempotency_key=request_identity,
                scheduled_at=request.scheduled_at,
                now=now,
                company_id=context.company.id,
                branch_id=request.branch_id,
                channel=request.channel.value,
                recipient_reference=str(request.contact_id),
                source_event_id=source_event_id,
                source_action=source_event_type,
                actor_user_id=context.user.id,
            )
            if not created and record.payload.get("request_digest") != request_digest:
                raise CommunicationConflictError(
                    "The request identity is already bound to different evidence."
                )
            if created:
                BusinessEventService.stage(
                    session,
                    BusinessEventCreate(
                        event_type=EventType.COMMUNICATION_REQUESTED,
                        entity_type="communication",
                        entity_id=record.id,
                        company_id=context.company.id,
                        branch_id=request.branch_id,
                        user_id=context.user.id,
                        correlation_id=source_correlation_id,
                        payload={
                            "communication_type": request.communication_type.value,
                            "channel": request.channel.value,
                            "customer_id": str(request.customer_id),
                            "contact_id": str(request.contact_id),
                            "source_event_id": str(request.source_event_id),
                            "request_identity": request_identity,
                        },
                    ),
                )
        return self._evidence(record)

    async def list(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        branch_id: UUID | None,
        customer_id: UUID | None,
        limit: int,
    ) -> tuple[CommunicationEvidence, ...]:
        if branch_id is not None:
            self._validate_branch(context, branch_id)
        records = await self.repository.list_scoped(
            session,
            company_id=context.company.id,
            branch_id=branch_id,
            customer_id=customer_id,
            limit=limit,
        )
        return tuple(self._evidence(record) for record in records)

    async def operations_summary(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        branch_id: UUID | None,
    ) -> dict[str, object]:
        if branch_id is not None:
            self._validate_branch(context, branch_id)
        return await self.repository.operations_summary(
            session,
            company_id=context.company.id,
            branch_id=branch_id,
        )

    @staticmethod
    def _evidence(record: NotificationOutbox) -> CommunicationEvidence:
        payload = record.payload
        try:
            return CommunicationEvidence(
                id=record.id,
                communication_type=CommunicationType(
                    str(payload["communication_type"])
                ),
                channel=CommunicationChannel(str(payload["channel"])),
                company_id=UUID(str(payload["company_id"])),
                branch_id=UUID(str(payload["branch_id"])),
                customer_id=UUID(str(payload["customer_id"])),
                contact_id=UUID(str(payload["contact_id"])),
                recipient_display=CommunicationService._recipient_display(
                    record.recipient,
                    CommunicationChannel(str(payload["channel"])),
                ),
                source_event_id=UUID(str(payload["source_event_id"])),
                source_event_type=str(payload["source_event_type"]),
                source_entity_type=str(payload["source_entity_type"]),
                source_entity_id=(
                    UUID(str(payload["source_entity_id"]))
                    if payload.get("source_entity_id")
                    else None
                ),
                request_identity=record.idempotency_key,
                state=CommunicationDeliveryState(
                    "delivered"
                    if record.status == "sent"
                    else "uncertain"
                    if record.status == "ambiguous"
                    else record.status
                ),
                retry_count=record.retry_count,
                terminal_failure=record.terminal_failure,
                scheduled_at=record.scheduled_at,
                sent_at=record.sent_at,
                failed_at=record.failed_at,
                error_code=record.last_error_code,
                error_category=record.last_error_category,
                created_at=record.created_at,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise CommunicationConflictError(
                "Communication evidence requires reconciliation."
            ) from error


communication_service = CommunicationService(communication_repository)
