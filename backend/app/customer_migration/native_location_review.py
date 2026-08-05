"""Tenant-safe read projection for acquired native Service Location evidence."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customer_migration.models import (
    ServiceLocationIdentityEvidence,
    ServiceLocationReconciliationEvidence,
)
from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import CustomerPermission
from app.platform.permissions.dependencies import require_permission

router = APIRouter(
    prefix="/api/v1/customer-migration/location-identities", tags=["Customer Migration"]
)
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
CustomerReadContext = Annotated[
    AuthorizationContext, Depends(require_permission(CustomerPermission.READ))
]


class LocationIdentityEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    branch_id: UUID
    customer_source_identity_id: UUID | None
    source_system: str
    source_entity_type: str
    source_location_id_sha256: str | None
    classification: str
    readiness: str
    evidence_digest: str
    evidence_version: int


class LocationIdentityEvidenceList(BaseModel):
    items: list[LocationIdentityEvidenceResponse]
    total: int
    limit: int
    offset: int


class LocationReconciliationEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    branch_id: UUID
    identity_evidence_id: UUID
    service_location_id: UUID | None
    customer_id: UUID | None
    matching_contract_version: str
    outcome: str
    candidate_count: int
    input_digest: str
    evidence_digest: str


class LocationReconciliationEvidenceList(BaseModel):
    items: list[LocationReconciliationEvidenceResponse]
    total: int
    limit: int
    offset: int


@router.get("", response_model=LocationIdentityEvidenceList)
async def list_location_identity_evidence(
    context: CustomerReadContext,
    session: DatabaseSession,
    readiness: Annotated[str | None, Query(max_length=30)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LocationIdentityEvidenceList:
    conditions = [ServiceLocationIdentityEvidence.company_id == context.company.id]
    if context.active_branch is not None:
        conditions.append(
            ServiceLocationIdentityEvidence.branch_id == context.active_branch.id
        )
    if readiness is not None:
        conditions.append(ServiceLocationIdentityEvidence.readiness == readiness)
    total = await session.scalar(
        select(func.count(ServiceLocationIdentityEvidence.id)).where(*conditions)
    )
    records = (
        await session.scalars(
            select(ServiceLocationIdentityEvidence)
            .where(*conditions)
            .order_by(
                ServiceLocationIdentityEvidence.created_at,
                ServiceLocationIdentityEvidence.id,
            )
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return LocationIdentityEvidenceList(
        items=[
            LocationIdentityEvidenceResponse.model_validate(item) for item in records
        ],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/reconciliations", response_model=LocationReconciliationEvidenceList)
async def list_location_reconciliation_evidence(
    context: CustomerReadContext,
    session: DatabaseSession,
    outcome: Annotated[str | None, Query(max_length=50)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LocationReconciliationEvidenceList:
    conditions = [
        ServiceLocationReconciliationEvidence.company_id == context.company.id
    ]
    if context.active_branch is not None:
        conditions.append(
            ServiceLocationReconciliationEvidence.branch_id == context.active_branch.id
        )
    if outcome is not None:
        conditions.append(ServiceLocationReconciliationEvidence.outcome == outcome)
    total = await session.scalar(
        select(func.count(ServiceLocationReconciliationEvidence.id)).where(*conditions)
    )
    records = (
        await session.scalars(
            select(ServiceLocationReconciliationEvidence)
            .where(*conditions)
            .order_by(
                ServiceLocationReconciliationEvidence.created_at,
                ServiceLocationReconciliationEvidence.id,
            )
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return LocationReconciliationEvidenceList(
        items=[
            LocationReconciliationEvidenceResponse.model_validate(item)
            for item in records
        ],
        total=total or 0,
        limit=limit,
        offset=offset,
    )
