"""Transactional SQL adapter for governed break-even policy operation events."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .break_even_policy import (
    BreakEvenPolicyKind,
    PolicyApprovalState,
    PolicyApproverRole,
    seal_break_even_policy,
)
from .models import BreakEvenPolicyOperationRecord, CompanyFinancePolicyVersion
from .owner_policy_operations import (
    OPERATIONS_VERSION,
    PolicyOperationEvent,
    verify_policy_operation_event,
)


class PolicyPersistenceConflict(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LegacyPolicyCompatibility:
    policy_id: UUID
    family_key: str
    state: str
    reason: str


class SqlPolicyOperationStore:
    """Append/reload events; callers own commit and transaction rollback."""

    async def list_events(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        branch_id: UUID | None,
    ) -> tuple[PolicyOperationEvent, ...]:
        scope_id = branch_id or company_id
        rows = tuple(
            (
                await session.scalars(
                    select(BreakEvenPolicyOperationRecord)
                    .where(
                        BreakEvenPolicyOperationRecord.company_id == company_id,
                        BreakEvenPolicyOperationRecord.scope_id == scope_id,
                    )
                    .order_by(
                        BreakEvenPolicyOperationRecord.occurred_at,
                        BreakEvenPolicyOperationRecord.id,
                    )
                )
            ).all()
        )
        return tuple(_from_record(row) for row in rows)

    async def append(
        self,
        session: AsyncSession,
        events: tuple[PolicyOperationEvent, ...],
    ) -> tuple[PolicyOperationEvent, ...]:
        if not events:
            return ()
        scopes = {(x.company_id, x.branch_id, x.policy.kind) for x in events}
        for company_id, branch_id, kind in sorted(
            scopes, key=lambda item: (str(item[0]), str(item[1]), item[2].value)
        ):
            lock_key = f"eco-break-even-policy:{company_id}:{branch_id or company_id}:{kind.value}"
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": lock_key},
            )
        persisted = []
        for event in events:
            verify_policy_operation_event(event)
            existing = await session.scalar(
                select(BreakEvenPolicyOperationRecord).where(
                    BreakEvenPolicyOperationRecord.event_digest == event.event_digest
                )
            )
            if existing is not None:
                replay = _from_record(existing)
                if replay != event:
                    raise PolicyPersistenceConflict("contradictory policy event replay")
                persisted.append(replay)
                continue
            collision = await session.scalar(
                select(BreakEvenPolicyOperationRecord.id).where(
                    BreakEvenPolicyOperationRecord.company_id == event.company_id,
                    BreakEvenPolicyOperationRecord.scope_id
                    == (event.branch_id or event.company_id),
                    BreakEvenPolicyOperationRecord.family_key
                    == event.policy.kind.value,
                    BreakEvenPolicyOperationRecord.policy_version
                    == event.policy_version,
                    BreakEvenPolicyOperationRecord.state == event.state.value,
                )
            )
            if collision is not None:
                raise PolicyPersistenceConflict(
                    "policy version/state already exists in governed scope"
                )
            session.add(_to_record(event))
            persisted.append(event)
        await session.flush()
        return tuple(persisted)


async def legacy_policy_compatibility(
    session: AsyncSession, *, company_id: UUID
) -> tuple[LegacyPolicyCompatibility, ...]:
    """Classify legacy rows without promoting or reinterpreting them."""
    rows = tuple(
        (
            await session.scalars(
                select(CompanyFinancePolicyVersion)
                .where(CompanyFinancePolicyVersion.company_id == company_id)
                .order_by(
                    CompanyFinancePolicyVersion.family_key,
                    CompanyFinancePolicyVersion.policy_version,
                )
            )
        ).all()
    )
    supported = {item.value for item in BreakEvenPolicyKind}
    return tuple(
        LegacyPolicyCompatibility(
            row.id,
            row.family_key,
            "LEGACY_COMPATIBLE_READ_ONLY"
            if row.family_key in supported
            else "LEGACY_INCOMPATIBLE",
            "explicit_migration_required_before_governed_use"
            if row.family_key not in supported
            else "legacy_row_remains_read_only_until_explicit_contract_admission",
        )
        for row in rows
    )


def _to_record(event: PolicyOperationEvent) -> BreakEvenPolicyOperationRecord:
    value = event.policy.value
    payload = {
        "type": "decimal" if isinstance(value, Decimal) else "string",
        "value": str(value) if value is not None else None,
    }
    return BreakEvenPolicyOperationRecord(
        id=event.event_id,
        company_id=event.company_id,
        branch_id=event.branch_id,
        scope_id=event.branch_id or event.company_id,
        policy_id=event.policy_id,
        family_key=event.policy.kind.value,
        policy_version=event.policy_version,
        state=event.state.value,
        value_payload=payload,
        effective_start=event.policy.effective_start,
        effective_end=event.policy.effective_end,
        actor_id=event.actor_id,
        approved_by_user_id=event.policy.approved_by_user_id,
        approver_role=event.policy.approver_role.value
        if event.policy.approver_role
        else None,
        approved_at=event.policy.approved_at,
        occurred_at=event.occurred_at,
        rationale=event.rationale,
        provenance=event.policy.provenance,
        provenance_digest=event.policy.provenance_digest,
        policy_digest=event.policy.policy_digest,
        supersedes_policy_id=event.policy.supersedes_policy_id,
        prior_event_digest=event.prior_event_digest,
        event_digest=event.event_digest,
        contract_version=OPERATIONS_VERSION,
    )


def _from_record(row: BreakEvenPolicyOperationRecord) -> PolicyOperationEvent:
    if row.contract_version != OPERATIONS_VERSION:
        raise PolicyPersistenceConflict("unsupported persisted policy contract")
    payload = row.value_payload
    if not isinstance(payload, dict) or payload.get("type") not in {
        "decimal",
        "string",
    }:
        raise PolicyPersistenceConflict("incompatible policy value payload")
    raw = payload.get("value")
    value = Decimal(str(raw)) if payload["type"] == "decimal" else raw
    policy = seal_break_even_policy(
        policy_id=row.policy_id,
        company_id=row.company_id,
        branch_id=row.branch_id,
        kind=BreakEvenPolicyKind(row.family_key),
        version=row.policy_version,
        value=value,
        effective_start=row.effective_start,
        effective_end=row.effective_end,
        approval_state=PolicyApprovalState(row.state),
        approved_by_user_id=row.approved_by_user_id,
        approver_role=PolicyApproverRole(row.approver_role)
        if row.approver_role
        else None,
        approved_at=row.approved_at,
        provenance=row.provenance,
        provenance_digest=row.provenance_digest,
        rationale_notes=row.rationale,
        supersedes_policy_id=row.supersedes_policy_id,
    )
    if policy.policy_digest != row.policy_digest:
        raise PolicyPersistenceConflict("persisted policy digest mismatch")
    event = PolicyOperationEvent(
        row.id,
        row.company_id,
        row.branch_id,
        row.policy_id,
        row.policy_version,
        PolicyApprovalState(row.state),
        row.actor_id,
        row.occurred_at,
        row.rationale,
        row.prior_event_digest,
        policy,
        row.event_digest,
    )
    verify_policy_operation_event(event)
    return event
