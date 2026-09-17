"""Exact canonical-reference resolution for bounded LIA record navigation."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.estimates.models import Estimate
from app.invoicing.models import Invoice
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import (
    EstimatePermission,
    InvoicePermission,
    SchedulingPermission,
)
from app.scheduling.models import Appointment

_MODELS: dict[str, tuple[Any, Any, str]] = {
    "estimates": (Estimate, Estimate.estimate_number, EstimatePermission.READ),
    "invoicing": (Invoice, Invoice.invoice_number, InvoicePermission.READ),
    "scheduling": (
        Appointment,
        Appointment.appointment_number,
        SchedulingPermission.READ,
    ),
}


async def resolve_canonical_reference(
    session: AsyncSession,
    *,
    context: AuthorizationContext,
    domain: str,
    reference: str,
) -> tuple[UUID, ...]:
    """Return only exact records in the current Company and authorized Branch scope."""
    model, reference_column, permission = _MODELS[domain]
    if not context.has_permission(permission):
        return ()
    branch_ids = (
        frozenset({context.active_branch.id})
        if context.active_branch is not None
        else context.authorized_branch_ids
    )
    if not branch_ids:
        return ()
    normalized = reference.strip().upper()
    return tuple(
        (
            await session.scalars(
                select(model.id)
                .where(
                    model.company_id == context.company.id,
                    model.branch_id.in_(branch_ids),
                    reference_column == normalized,
                )
                .order_by(model.id)
                .limit(2)
            )
        ).all()
    )
