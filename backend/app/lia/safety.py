"""Deterministic validation boundaries for untrusted content and tool inputs."""

from __future__ import annotations

import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .foundation import (
    EvidenceEnvelope,
    EvidenceState,
    PrincipalSnapshot,
    StructuredClaim,
)

SECRET_MARKERS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\b(?:access|refresh|session)[_-]?token\b", re.IGNORECASE),
    re.compile(r"\bclient[_-]?secret\b", re.IGNORECASE),
    re.compile(r"\bpostgres(?:ql)?://", re.IGNORECASE),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


class ScopedEntityToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    company_id: UUID
    branch_id: UUID | None
    entity_id: UUID
    expected_version: int = Field(ge=0)

    def authorize(self, principal: PrincipalSnapshot) -> None:
        if self.company_id != principal.company_id:
            raise PermissionError("Requested entity is outside the authorized Company.")
        if (
            self.branch_id is not None
            and self.branch_id not in principal.authorized_branch_ids
        ):
            raise PermissionError(
                "Requested entity is outside the authorized Branch scope."
            )


class UntrustedBusinessContent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_type: str = Field(max_length=64)
    text: str = Field(max_length=4000)
    trust: str = "UNTRUSTED_DATA_NEVER_INSTRUCTION"


def assert_context_secret_safe(values: tuple[str, ...]) -> None:
    if any(pattern.search(value) for value in values for pattern in SECRET_MARKERS):
        raise ValueError("Secret-like material is prohibited from LIA context.")


def untrusted_content_cannot_change_authority(
    content: UntrustedBusinessContent, principal: PrincipalSnapshot
) -> PrincipalSnapshot:
    """Content is carried only as labeled data; authority is immutable."""
    assert_context_secret_safe((content.text,))
    return principal


def validate_structured_claim(
    claim: StructuredClaim, evidence: tuple[EvidenceEnvelope, ...]
) -> bool:
    """Validate binding and temporal authority without inspecting model reasoning."""
    available = {item.evidence_id: item for item in evidence}
    if not claim.evidence_ids or any(
        item not in available for item in claim.evidence_ids
    ):
        return False
    selected = tuple(available[item] for item in claim.evidence_ids)
    if any(
        item.state
        in (
            EvidenceState.CONFLICTING,
            EvidenceState.UNRESOLVED,
            EvidenceState.UNAVAILABLE,
        )
        for item in selected
    ):
        return False
    if claim.claim_type in {"CHANGED", "CURRENT", "OVERDUE", "INCREASED"}:
        return claim.effective_at is not None and claim.policy_reference is not None
    if claim.claim_type == "NUMERIC":
        # Numeric claims require an exact structured value in an evidence summary;
        # prose inference and approximate matching are deliberately unsupported.
        return any(item.safe_summary == claim.value for item in selected)
    return True
