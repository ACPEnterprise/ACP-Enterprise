"""Governed operational message catalog; source domains retain business truth."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from .contracts import CommunicationPolicy
from .types import CommunicationChannel, CommunicationType

EMAIL_SMS = frozenset({CommunicationChannel.EMAIL, CommunicationChannel.SMS})
EMAIL_ONLY = frozenset({CommunicationChannel.EMAIL})
DOCUMENT_CHANNELS = frozenset(
    {
        CommunicationChannel.EMAIL,
        CommunicationChannel.SMS,
        CommunicationChannel.PROTECTED_LINK,
        CommunicationChannel.PRINT,
    }
)


def _policy(
    kind: CommunicationType,
    owner: str,
    source_events: set[str],
    channels: frozenset[CommunicationChannel],
    *,
    consent_required: bool = True,
    policy_required: bool = False,
) -> CommunicationPolicy:
    return CommunicationPolicy(
        communication_type=kind,
        source_event_types=frozenset(source_events),
        template_identifier=f"{kind.value.replace('_', '-')}-v1",
        consent_required=consent_required,
        owner_domain=owner,
        allowed_channels=channels,
        policy_required=policy_required,
    )


OPERATIONAL_MESSAGE_CATALOG: dict[CommunicationType, CommunicationPolicy] = {
    CommunicationType.EMPLOYEE_INVITATION: _policy(
        CommunicationType.EMPLOYEE_INVITATION,
        "identity",
        {"identity.invitation_created"},
        EMAIL_ONLY,
        consent_required=False,
    ),
    CommunicationType.ACCOUNT_ACTIVATION: _policy(
        CommunicationType.ACCOUNT_ACTIVATION,
        "identity",
        {"identity.invitation_claimed"},
        EMAIL_ONLY,
        consent_required=False,
    ),
    CommunicationType.SECURITY_NOTIFICATION: _policy(
        CommunicationType.SECURITY_NOTIFICATION,
        "identity",
        {"identity.security_notification_requested"},
        EMAIL_ONLY,
        consent_required=False,
        policy_required=True,
    ),
    CommunicationType.APPOINTMENT_CONFIRMATION: _policy(
        CommunicationType.APPOINTMENT_CONFIRMATION,
        "scheduling",
        {"appointment.booked"},
        EMAIL_SMS,
    ),
    CommunicationType.APPOINTMENT_REMINDER: _policy(
        CommunicationType.APPOINTMENT_REMINDER,
        "scheduling",
        {"appointment.booked", "appointment.rescheduled"},
        EMAIL_SMS,
        policy_required=True,
    ),
    CommunicationType.APPOINTMENT_RESCHEDULED: _policy(
        CommunicationType.APPOINTMENT_RESCHEDULED,
        "scheduling",
        {"appointment.rescheduled"},
        EMAIL_SMS,
    ),
    CommunicationType.APPOINTMENT_CANCELLED: _policy(
        CommunicationType.APPOINTMENT_CANCELLED,
        "scheduling",
        {"appointment.cancelled"},
        EMAIL_SMS,
    ),
    CommunicationType.TECHNICIAN_ASSIGNED: _policy(
        CommunicationType.TECHNICIAN_ASSIGNED,
        "dispatch",
        {"technician.assigned"},
        EMAIL_SMS,
        policy_required=True,
    ),
    CommunicationType.TECHNICIAN_EN_ROUTE: _policy(
        CommunicationType.TECHNICIAN_EN_ROUTE,
        "dispatch",
        {"technician.en_route"},
        EMAIL_SMS,
        policy_required=True,
    ),
    CommunicationType.TECHNICIAN_ARRIVED: _policy(
        CommunicationType.TECHNICIAN_ARRIVED,
        "dispatch",
        {"technician.arrived"},
        EMAIL_SMS,
        policy_required=True,
    ),
    CommunicationType.WORK_COMPLETED: _policy(
        CommunicationType.WORK_COMPLETED,
        "jobs",
        {"job.completed", "field.completion_requirements_satisfied"},
        EMAIL_SMS,
        policy_required=True,
    ),
    CommunicationType.ESTIMATE_ACTION_REQUESTED: _policy(
        CommunicationType.ESTIMATE_ACTION_REQUESTED,
        "estimates",
        {"estimate.sent"},
        DOCUMENT_CHANNELS,
    ),
    CommunicationType.ESTIMATE_FOLLOW_UP: _policy(
        CommunicationType.ESTIMATE_FOLLOW_UP,
        "estimates",
        {"estimate.sent"},
        EMAIL_SMS,
        policy_required=True,
    ),
    CommunicationType.ESTIMATE_STATUS_NOTICE: _policy(
        CommunicationType.ESTIMATE_STATUS_NOTICE,
        "estimates",
        {"estimate.approved", "estimate.rejected", "estimate.expired"},
        EMAIL_SMS,
    ),
    CommunicationType.INVOICE_READY: _policy(
        CommunicationType.INVOICE_READY,
        "invoicing",
        {"invoice.issued"},
        DOCUMENT_CHANNELS,
    ),
    CommunicationType.PAYMENT_RECEIPT: _policy(
        CommunicationType.PAYMENT_RECEIPT,
        "payments",
        {"payment.receipt_captured", "payment.settlement_received"},
        DOCUMENT_CHANNELS,
    ),
    CommunicationType.PAYMENT_STATUS_NOTIFICATION: _policy(
        CommunicationType.PAYMENT_STATUS_NOTIFICATION,
        "payments",
        {"payment.failed", "payment.refund_succeeded"},
        EMAIL_SMS,
        policy_required=True,
    ),
    CommunicationType.SERVICE_AGREEMENT_NOTICE: _policy(
        CommunicationType.SERVICE_AGREEMENT_NOTICE,
        "service_agreements",
        {"service_agreement.changed", "service_agreement.billing_ready"},
        EMAIL_SMS,
        policy_required=True,
    ),
}


def catalog_fingerprint() -> str:
    facts = [
        {
            **asdict(policy),
            "communication_type": policy.communication_type.value,
            "source_event_types": sorted(policy.source_event_types),
            "allowed_channels": sorted(c.value for c in policy.allowed_channels),
        }
        for policy in OPERATIONAL_MESSAGE_CATALOG.values()
    ]
    facts.sort(key=lambda item: str(item["communication_type"]))
    return hashlib.sha256(
        json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class ChannelEligibility:
    channel: CommunicationChannel
    available: bool
    transactional_allowed: bool
    marketing_consented: bool | None = None
    suppressed: bool = False


@dataclass(frozen=True)
class ChannelSelection:
    channel: CommunicationChannel
    fallback_from: CommunicationChannel | None
    reason: str


def select_channel(
    *,
    policy: CommunicationPolicy,
    preferred: CommunicationChannel | None,
    eligibility: tuple[ChannelEligibility, ...],
    fallback_order: tuple[CommunicationChannel, ...],
) -> ChannelSelection:
    """Select deterministically; marketing consent never substitutes for operations."""
    by_channel = {item.channel: item for item in eligibility}
    order = tuple(dict.fromkeys((preferred,) + fallback_order)) if preferred else fallback_order
    for candidate in order:
        state = by_channel.get(candidate)
        if (
            candidate in policy.allowed_channels
            and state is not None
            and state.available
            and state.transactional_allowed
            and not state.suppressed
        ):
            return ChannelSelection(
                channel=candidate,
                fallback_from=(preferred if preferred and candidate != preferred else None),
                reason=("preferred_channel" if candidate == preferred else "governed_fallback"),
            )
    raise ValueError("No eligible transactional communication channel is available.")
