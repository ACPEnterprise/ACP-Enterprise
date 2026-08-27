import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256
from typing import Protocol
from uuid import UUID


class PostingSide(str, Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class PostingOutcome(str, Enum):
    POSTED = "posted"
    RECONCILIATION_REQUIRED = "reconciliation_required"


@dataclass(frozen=True, slots=True)
class PostingFact:
    """Accepted, immutable financial fact supplied by an owning domain."""

    schema_version: str
    company_id: UUID
    branch_id: UUID | None
    source_event_id: UUID
    source_type: str
    source_id: UUID
    event_type: str
    effective_date: date
    occurred_at: datetime
    currency: str
    components: Mapping[str, Decimal]
    evidence_digest: str

    @property
    def source_identity(self) -> str:
        return f"{self.source_type}:{self.source_id}:{self.source_event_id}"

    def canonical_digest(self) -> str:
        document = {
            "branch_id": str(self.branch_id) if self.branch_id else None,
            "company_id": str(self.company_id),
            "components": {
                key: format(Decimal(value).normalize(), "f")
                for key, value in sorted(self.components.items())
            },
            "currency": self.currency,
            "effective_date": self.effective_date.isoformat(),
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "schema_version": self.schema_version,
            "source_event_id": str(self.source_event_id),
            "source_id": str(self.source_id),
            "source_type": self.source_type,
        }
        return sha256(
            json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class PostingLeg:
    component: str
    account_id: UUID
    side: PostingSide
    description: str


@dataclass(frozen=True, slots=True)
class PostingRule:
    company_id: UUID
    event_type: str
    version: str
    effective_from: date
    effective_to: date | None
    approved_at: datetime
    approved_by_user_id: UUID
    legs: tuple[PostingLeg, ...]
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class PostingReceipt:
    company_id: UUID
    branch_id: UUID | None
    source_event_id: UUID
    source_type: str
    source_id: UUID
    journal_id: UUID | None
    journal_version: int | None
    policy_version: str
    status: PostingOutcome
    effective_date: date
    posted_at: datetime | None
    failure_reason: str | None = None


class PostingReceiptSink(Protocol):
    async def deliver(self, receipt: PostingReceipt) -> None: ...
