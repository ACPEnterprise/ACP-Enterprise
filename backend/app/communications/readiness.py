"""Truthful provider and policy readiness projections for operators."""

from dataclasses import dataclass
from enum import StrEnum


class ReadinessState(StrEnum):
    EMAIL_PROVIDER_NOT_CONFIGURED = "EMAIL_PROVIDER_NOT_CONFIGURED"
    EMAIL_SENDER_NOT_VERIFIED = "EMAIL_SENDER_NOT_VERIFIED"
    EMAIL_DOMAIN_NOT_VERIFIED = "EMAIL_DOMAIN_NOT_VERIFIED"
    EMAIL_READY = "EMAIL_READY"
    SMS_PROVIDER_NOT_CONFIGURED = "SMS_PROVIDER_NOT_CONFIGURED"
    SMS_SENDER_NOT_CONFIGURED = "SMS_SENDER_NOT_CONFIGURED"
    SMS_REGISTRATION_REQUIRED = "SMS_REGISTRATION_REQUIRED"
    SMS_READY = "SMS_READY"
    WEBHOOK_NOT_CONFIGURED = "WEBHOOK_NOT_CONFIGURED"
    WEBHOOK_READY = "WEBHOOK_READY"
    DEGRADED = "DEGRADED"
    READY = "READY"


@dataclass(frozen=True)
class ProviderConfiguration:
    email_provider: bool = False
    email_sender_verified: bool = False
    email_domain_verified: bool = False
    sms_provider: bool = False
    sms_sender: bool = False
    sms_registration: bool = False
    webhook: bool = False


@dataclass(frozen=True)
class CommunicationsReadiness:
    email: ReadinessState
    sms: ReadinessState
    webhook: ReadinessState
    overall: ReadinessState
    synthetic_only: bool


def project_readiness(config: ProviderConfiguration) -> CommunicationsReadiness:
    if not config.email_provider:
        email = ReadinessState.EMAIL_PROVIDER_NOT_CONFIGURED
    elif not config.email_sender_verified:
        email = ReadinessState.EMAIL_SENDER_NOT_VERIFIED
    elif not config.email_domain_verified:
        email = ReadinessState.EMAIL_DOMAIN_NOT_VERIFIED
    else:
        email = ReadinessState.EMAIL_READY

    if not config.sms_provider:
        sms = ReadinessState.SMS_PROVIDER_NOT_CONFIGURED
    elif not config.sms_sender:
        sms = ReadinessState.SMS_SENDER_NOT_CONFIGURED
    elif not config.sms_registration:
        sms = ReadinessState.SMS_REGISTRATION_REQUIRED
    else:
        sms = ReadinessState.SMS_READY
    webhook = (
        ReadinessState.WEBHOOK_READY
        if config.webhook
        else ReadinessState.WEBHOOK_NOT_CONFIGURED
    )
    ready = (
        email is ReadinessState.EMAIL_READY
        and sms is ReadinessState.SMS_READY
        and webhook is ReadinessState.WEBHOOK_READY
    )
    return CommunicationsReadiness(
        email=email,
        sms=sms,
        webhook=webhook,
        overall=ReadinessState.READY if ready else ReadinessState.DEGRADED,
        synthetic_only=not ready,
    )
