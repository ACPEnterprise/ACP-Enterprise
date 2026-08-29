"""Shared semantics for domain-owned durable API idempotency.

This module does not persist receipts. Domains retain their accepted durable
command/receipt implementations; these types define the invariant those
implementations expose at the HTTP boundary.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

CONTRACT_VERSION = "1"


class IdempotencyContractError(ValueError):
    """Base error for invalid or unsafe idempotency evidence."""


class ContradictoryReplayError(IdempotencyContractError):
    """The same scoped identity was reused for a different command."""


class ReplayAuthorizationError(IdempotencyContractError):
    """Current authority does not permit recovery of the prior result."""


class ReplayDecision(StrEnum):
    EXECUTE = "EXECUTE"
    REPLAY = "REPLAY"


@dataclass(frozen=True, slots=True)
class IdempotencyIdentity:
    """Tenant-scoped semantic command identity.

    Branch is immutable authorization context, not part of the default unique
    identity. A domain may include it in ``operation`` only when its accepted
    aggregate identity is explicitly Branch-scoped.
    """

    company_id: UUID
    operation: str
    idempotency_key: str
    branch_id: UUID | None = None

    def __post_init__(self) -> None:
        if not self.operation.strip():
            raise IdempotencyContractError("operation identity is required")
        if not self.idempotency_key.strip():
            raise IdempotencyContractError("idempotency key is required")
        if len(self.idempotency_key) > 255:
            raise IdempotencyContractError("idempotency key exceeds 255 characters")

    @property
    def tenant_key(self) -> tuple[UUID, str, str]:
        return (self.company_id, self.operation, self.idempotency_key)


def _canonical(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        raise IdempotencyContractError(
            "binary floating-point values are not canonical request evidence"
        )
    if isinstance(value, Decimal):
        return {"$decimal": format(value, "f")}
    if isinstance(value, UUID):
        return {"$uuid": str(value)}
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise IdempotencyContractError("datetime evidence must include a timezone")
        return {"$datetime": value.isoformat()}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise IdempotencyContractError("canonical request keys must be strings")
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    raise IdempotencyContractError(
        f"unsupported canonical request value: {type(value).__name__}"
    )


def canonical_request_digest(payload: object) -> str:
    """Digest semantically normalized request evidence.

    Mapping order is irrelevant. Sequence order remains significant unless a
    domain contract normalizes an unordered collection before calling here.
    Server-authored transport fields must be omitted by that domain adapter.
    """

    encoded = json.dumps(
        _canonical(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def decide_replay(
    *,
    stored_request_digest: str | None,
    incoming_request_digest: str,
    currently_authorized: bool,
) -> ReplayDecision:
    """Return execute/replay or fail closed for an unsafe recovery attempt.

    Possession of a key is never authorization. Routers must establish current
    Company/Branch permission before resolving a durable receipt.
    """

    if not currently_authorized:
        raise ReplayAuthorizationError("current authority is required for replay")
    if stored_request_digest is None:
        return ReplayDecision.EXECUTE
    if stored_request_digest != incoming_request_digest:
        raise ContradictoryReplayError(
            "idempotency identity conflicts with the original request"
        )
    return ReplayDecision.REPLAY
