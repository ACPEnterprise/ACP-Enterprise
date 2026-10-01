"""Server-owned CSR/Dispatch composition over canonical LIA evidence.

This module carries transient interpretation and recommendation metadata only.
It deliberately has no persistence or mutation authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .contracts import (
    CsrDispatchCopilot,
    CustomerIntakeBranch,
    NavigationSuggestion,
    SpeechInterpretation,
)
from .dispatch_reasoning import GhostSlot, GhostSlotClass, LiaDispatchReasoning


@dataclass(frozen=True, slots=True)
class CustomerMatch:
    """Result of a canonical Customer/Location resolver, never fuzzy identity."""

    state: str
    customer_id: UUID | None = None
    location_id: UUID | None = None
    missing_fields: tuple[str, ...] = ()
    next_questions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


def compose_csr_dispatch_copilot(
    reasoning: LiaDispatchReasoning,
    *,
    customer_match: CustomerMatch,
    evaluated_at: datetime,
    speech: tuple[SpeechInterpretation, ...] = (),
    actions: tuple[NavigationSuggestion, ...] = (),
) -> CsrDispatchCopilot:
    """Compose a CSR payload without promoting unconfirmed speech to authority."""

    if customer_match.state not in {"EXISTING", "NEW_CUSTOMER_INTAKE_REQUIRED", "AMBIGUOUS"}:
        raise ValueError("customer match must be canonical EXISTING, NEW, or AMBIGUOUS")
    if customer_match.state == "EXISTING" and not customer_match.customer_id:
        raise ValueError("existing Customer branch requires canonical customer_id")
    if customer_match.state == "EXISTING" and not customer_match.location_id:
        raise ValueError("existing Customer branch requires canonical location_id")
    if any(item.confirmed and item.state != "CONFIDENT" for item in speech):
        raise ValueError("confirmed speech facts must be CONFIDENT")
    if evaluated_at.tzinfo is None:
        raise ValueError("evaluation time must be timezone-aware")

    clarification = tuple(
        item for item in speech if item.state != "CONFIDENT" or not item.confirmed
    )
    expired = evaluated_at >= reasoning.expires_at
    current = customer_match.state == "EXISTING" and not clarification and not expired
    slots = tuple(_slot_payload(item) for item in (reasoning.primary, *reasoning.alternates))
    primary = (
        slots[0]
        if not expired
        and reasoning.primary.slot_class is GhostSlotClass.PRIMARY_GHOST_SLOT
        else None
    )
    alternates = tuple(
        item
        for item in slots[1:]
        if not expired
        and item["slot_class"] == GhostSlotClass.ALTERNATE_GHOST_SLOT.value
    )
    constrained = tuple(
        item
        for item in slots
        if not expired
        and item["slot_class"] == GhostSlotClass.CONSTRAINED_OPTION.value
    )
    limitations = list(reasoning.limitations) + list(customer_match.limitations)
    if customer_match.state != "EXISTING":
        limitations.append("Recommendations remain provisional until canonical Customer and Location are confirmed.")
    if clarification:
        limitations.append("Unconfirmed speech interpretations require CSR/customer confirmation.")
    if expired:
        limitations.append("Dispatch reasoning expired; refresh before offering a slot.")
    question = _next_question(customer_match, clarification, reasoning.next_question)
    return CsrDispatchCopilot(
        reasoning_id=reasoning.reasoning_id,
        reasoning_revision=reasoning.revision,
        reasoning_digest=reasoning.reasoning_digest,
        supersedes_reasoning_id=reasoning.supersedes_reasoning_id,
        suggested_question=question,
        customer_branch=CustomerIntakeBranch(
            state=customer_match.state,
            customer_id=customer_match.customer_id,
            location_id=customer_match.location_id,
            missing_fields=customer_match.missing_fields,
            next_questions=customer_match.next_questions,
            limitations=customer_match.limitations,
        ),
        speech_interpretations=speech,
        clarification_required=bool(clarification),
        translation_available=any(item.translation_state == "TRANSLATED" for item in speech),
        recommendation_state=(
            "EXPIRED" if expired else "CURRENT" if current else "PROVISIONAL"
        ),
        primary_ghost_slot=primary,
        alternates=alternates,
        constrained_options=constrained,
        facts=reasoning.facts,
        interpretation=reasoning.interpretation,
        recommendation=reasoning.recommendation,
        why=reasoning.why,
        as_of=reasoning.as_of,
        expires_at=reasoning.expires_at,
        action_metadata=actions,
        limitations=tuple(dict.fromkeys(limitations)),
    )


def _next_question(
    customer_match: CustomerMatch,
    clarification: tuple[SpeechInterpretation, ...],
    reasoning_question: str | None,
) -> str | None:
    if clarification:
        return clarification[0].suggested_confirmation or "Please confirm that detail."
    if customer_match.next_questions:
        return customer_match.next_questions[0]
    return reasoning_question


def _slot_payload(slot: GhostSlot) -> dict[str, object]:
    return {
        "slot_class": slot.slot_class.value,
        "employee_id": str(slot.employee_id) if slot.employee_id else None,
        "start_at": slot.start_at.isoformat() if slot.start_at else None,
        "end_at": slot.end_at.isoformat() if slot.end_at else None,
        "facts": slot.facts,
        "why": slot.why,
        "limitations": slot.limitations,
        "evidence": tuple(
            {"authority": item.authority, "identity": item.identity, "digest": item.digest}
            for item in slot.evidence
        ),
    }
