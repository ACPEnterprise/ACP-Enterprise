"""Append-only recipient suppression authority for provider-neutral delivery."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, select, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

from .types import CommunicationChannel, CommunicationPurpose


class SuppressionScope(StrEnum):
    ALL = "all"
    MARKETING_OUTREACH = "marketing_outreach"
    OPERATIONAL = "operational"
    TRANSACTIONAL = "transactional"


class SuppressionSource(StrEnum):
    CUSTOMER_NO_CONTACT = "customer_no_contact"
    MARKETING_OPT_OUT = "marketing_opt_out"
    SMS_STOP = "sms_stop"
    EMAIL_UNSUBSCRIBE = "email_unsubscribe"
    INVALID_RECIPIENT = "invalid_recipient"
    HARD_BOUNCE = "hard_bounce"
    PROVIDER_SUPPRESSION = "provider_suppression"
    COMPANY_ADMINISTRATOR = "company_administrator"


class CommunicationRecipientControl(Base):
    """One immutable suppression decision; later rows supersede by authority key."""

    __tablename__ = "communication_recipient_controls"
    __table_args__ = (
        CheckConstraint(
            "channel IN ('email', 'sms')", name="ck_recipient_control_channel"
        ),
        CheckConstraint(
            "scope IN ('all', 'marketing_outreach', 'operational', 'transactional')",
            name="ck_recipient_control_scope",
        ),
        CheckConstraint(
            "source IN ('customer_no_contact', 'marketing_opt_out', 'sms_stop', "
            "'email_unsubscribe', 'invalid_recipient', 'hard_bounce', "
            "'provider_suppression', 'company_administrator')",
            name="ck_recipient_control_source",
        ),
        CheckConstraint(
            "length(destination_digest) = 64",
            name="ck_recipient_control_destination_digest",
        ),
        Index(
            "uq_recipient_control_provider_event",
            "company_id",
            "provider_event_key",
            unique=True,
            postgresql_where=text("provider_event_key IS NOT NULL"),
        ),
        Index(
            "ix_recipient_control_lookup",
            "company_id",
            "channel",
            "destination_digest",
            "scope",
            "source",
            "occurred_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    customer_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    contact_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    destination_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    provider_event_key: Mapped[str | None] = mapped_column(String(200))
    source_evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


@dataclass(frozen=True)
class RecipientControlDecision:
    company_id: UUID
    channel: CommunicationChannel
    destination_digest: str
    scope: SuppressionScope
    source: SuppressionSource
    active: bool
    source_evidence_digest: str
    occurred_at: datetime
    recorded_at: datetime
    branch_id: UUID | None = None
    customer_id: UUID | None = None
    contact_id: UUID | None = None
    provider_event_key: str | None = None


def destination_digest(destination: str) -> str:
    return hashlib.sha256(destination.encode("utf-8")).hexdigest()


class RecipientSuppressionRepository:
    @staticmethod
    async def record(
        session: AsyncSession, decision: RecipientControlDecision
    ) -> tuple[CommunicationRecipientControl, bool]:
        if len(decision.destination_digest) != 64:
            raise ValueError("Recipient destination evidence is invalid.")
        if len(decision.source_evidence_digest) != 64:
            raise ValueError("Recipient control source evidence is invalid.")
        values = {
            **decision.__dict__,
            "id": uuid4(),
            "channel": decision.channel.value,
            "scope": decision.scope.value,
            "source": decision.source.value,
        }
        statement = insert(CommunicationRecipientControl).values(**values)
        if decision.provider_event_key is not None:
            statement = statement.on_conflict_do_nothing(
                index_elements=(
                    CommunicationRecipientControl.company_id,
                    CommunicationRecipientControl.provider_event_key,
                ),
                index_where=CommunicationRecipientControl.provider_event_key.is_not(
                    None
                ),
            )
        record = (
            await session.scalars(statement.returning(CommunicationRecipientControl))
        ).one_or_none()
        if record is not None:
            return record, True
        existing = await session.scalar(
            select(CommunicationRecipientControl).where(
                CommunicationRecipientControl.company_id == decision.company_id,
                CommunicationRecipientControl.provider_event_key
                == decision.provider_event_key,
            )
        )
        if existing is None:
            raise RuntimeError("Recipient control replay did not resolve.")
        return existing, False

    @staticmethod
    async def is_suppressed(
        session: AsyncSession,
        *,
        company_id: UUID,
        channel: CommunicationChannel,
        destination_digest_value: str,
        purpose: CommunicationPurpose,
    ) -> bool:
        applicable = [SuppressionScope.ALL.value]
        if purpose is CommunicationPurpose.MARKETING_OUTREACH:
            applicable.append(SuppressionScope.MARKETING_OUTREACH.value)
        elif purpose is CommunicationPurpose.OPERATIONAL:
            applicable.append(SuppressionScope.OPERATIONAL.value)
        elif purpose is CommunicationPurpose.TRANSACTIONAL:
            applicable.append(SuppressionScope.TRANSACTIONAL.value)

        rows = (
            await session.scalars(
                select(CommunicationRecipientControl)
                .where(
                    CommunicationRecipientControl.company_id == company_id,
                    CommunicationRecipientControl.channel == channel.value,
                    CommunicationRecipientControl.destination_digest
                    == destination_digest_value,
                    CommunicationRecipientControl.scope.in_(applicable),
                )
                .order_by(
                    CommunicationRecipientControl.source,
                    CommunicationRecipientControl.occurred_at.desc(),
                    CommunicationRecipientControl.id.desc(),
                )
            )
        ).all()
        latest_by_source: dict[str, CommunicationRecipientControl] = {}
        for row in rows:
            latest_by_source.setdefault(f"{row.scope}:{row.source}", row)
        return any(row.active for row in latest_by_source.values())


recipient_suppression_repository = RecipientSuppressionRepository()
