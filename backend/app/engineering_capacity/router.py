from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EngineeringCapacityPermission
from app.platform.permissions.dependencies import require_permission

from .errors import EngineeringCapacityError
from .schemas import (
    CapacityAllocationRequest,
    CapacityAllocationResponse,
    CapacityBaselineRequest,
    CapacityMachineResponse,
    CapacityPolicyResponse,
    CapacityPolicyUpdate,
    CapacityQueueItem,
    CapacityReconciliationRequest,
    CapacityReleaseRequest,
    CapacityReservationRequest,
    CapacityReservationResponse,
    CapacitySummaryResponse,
    EligibleWorkerResponse,
    ExistingWorkerCapacitySetup,
    WorkerCapacityRegister,
    WorkerCapacityResponse,
    WorkerCapacityUpdate,
    WorkerStateUpdate,
)
from .service import engineering_capacity_service

router = APIRouter(prefix="/api/v1/engineering/capacity", tags=["Engineering Capacity"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
ReadContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(EngineeringCapacityPermission.READ)),
]
ManageContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(EngineeringCapacityPermission.MANAGE)),
]


def capacity_http_error(error: EngineeringCapacityError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": str(error)},
    )


@router.get("/summary", response_model=CapacitySummaryResponse)
async def read_capacity_summary(
    context: ReadContext, session: DatabaseSession
) -> CapacitySummaryResponse:
    return await engineering_capacity_service.summary(session, context=context)


@router.get("/workers", response_model=tuple[WorkerCapacityResponse, ...])
async def read_worker_capacity(
    context: ReadContext, session: DatabaseSession
) -> tuple[WorkerCapacityResponse, ...]:
    return (
        await engineering_capacity_service.summary(session, context=context)
    ).workers


@router.get("/eligible-workers", response_model=tuple[EligibleWorkerResponse, ...])
async def read_eligible_workers(
    context: ReadContext, session: DatabaseSession
) -> tuple[EligibleWorkerResponse, ...]:
    return (
        await engineering_capacity_service.summary(session, context=context)
    ).eligible_workers


@router.get("/reservations", response_model=tuple[CapacityReservationResponse, ...])
async def read_reservations(
    context: ReadContext, session: DatabaseSession
) -> tuple[CapacityReservationResponse, ...]:
    return (
        await engineering_capacity_service.summary(session, context=context)
    ).active_reservations


@router.get("/allocations", response_model=tuple[CapacityAllocationResponse, ...])
async def read_allocations(
    context: ReadContext, session: DatabaseSession
) -> tuple[CapacityAllocationResponse, ...]:
    return (
        await engineering_capacity_service.summary(session, context=context)
    ).active_allocations


@router.get("/queue", response_model=tuple[CapacityQueueItem, ...])
async def read_capacity_queue(
    context: ReadContext, session: DatabaseSession
) -> tuple[CapacityQueueItem, ...]:
    return (
        await engineering_capacity_service.summary(session, context=context)
    ).waiting_workstreams


@router.put("/policy", response_model=CapacityPolicyResponse)
async def update_capacity_policy(
    data: CapacityPolicyUpdate, context: ManageContext, session: DatabaseSession
) -> CapacityPolicyResponse:
    try:
        return await engineering_capacity_service.update_policy(
            session, context=context, data=data
        )
    except EngineeringCapacityError as error:
        raise capacity_http_error(error) from error


@router.post("/machines", response_model=CapacityMachineResponse)
async def record_machine(
    data: CapacityBaselineRequest, context: ManageContext, session: DatabaseSession
) -> CapacityMachineResponse:
    return await engineering_capacity_service.add_machine(
        session, context=context, data=data
    )


@router.post("/workers", response_model=WorkerCapacityResponse)
async def configure_worker_capacity(
    data: WorkerCapacityRegister, context: ManageContext, session: DatabaseSession
) -> WorkerCapacityResponse:
    try:
        return await engineering_capacity_service.register_worker_capacity(
            session, context=context, data=data
        )
    except EngineeringCapacityError as error:
        raise capacity_http_error(error) from error


@router.post("/workers/configure-existing", response_model=WorkerCapacityResponse)
async def configure_existing_worker_capacity(
    data: ExistingWorkerCapacitySetup,
    context: ManageContext,
    session: DatabaseSession,
) -> WorkerCapacityResponse:
    try:
        return await engineering_capacity_service.configure_existing_worker(
            session, context=context, data=data
        )
    except EngineeringCapacityError as error:
        raise capacity_http_error(error) from error


@router.put("/workers/{worker_id}/limit", response_model=WorkerCapacityResponse)
async def update_worker_limit(
    worker_id: UUID,
    data: WorkerCapacityUpdate,
    context: ManageContext,
    session: DatabaseSession,
) -> WorkerCapacityResponse:
    try:
        return await engineering_capacity_service.update_worker_limit(
            session, context=context, worker_id=worker_id, data=data
        )
    except EngineeringCapacityError as error:
        raise capacity_http_error(error) from error


@router.post("/workers/{worker_id}/pause", response_model=WorkerCapacityResponse)
async def pause_worker(
    worker_id: UUID,
    data: WorkerStateUpdate,
    context: ManageContext,
    session: DatabaseSession,
) -> WorkerCapacityResponse:
    try:
        return await engineering_capacity_service.set_worker_state(
            session, context=context, worker_id=worker_id, state="paused", data=data
        )
    except EngineeringCapacityError as error:
        raise capacity_http_error(error) from error


@router.post("/workers/{worker_id}/restore", response_model=WorkerCapacityResponse)
async def restore_worker(
    worker_id: UUID,
    data: WorkerStateUpdate,
    context: ManageContext,
    session: DatabaseSession,
) -> WorkerCapacityResponse:
    try:
        return await engineering_capacity_service.set_worker_state(
            session, context=context, worker_id=worker_id, state="available", data=data
        )
    except EngineeringCapacityError as error:
        raise capacity_http_error(error) from error


@router.post(
    "/workers/{worker_id}/reconciliation-required",
    response_model=WorkerCapacityResponse,
)
async def mark_worker_reconciliation_required(
    worker_id: UUID,
    data: WorkerStateUpdate,
    context: ManageContext,
    session: DatabaseSession,
) -> WorkerCapacityResponse:
    try:
        return await engineering_capacity_service.mark_worker_reconciliation_required(
            session, context=context, worker_id=worker_id, data=data
        )
    except EngineeringCapacityError as error:
        raise capacity_http_error(error) from error


@router.post("/reservations", response_model=CapacityReservationResponse)
async def reserve_capacity(
    data: CapacityReservationRequest, context: ManageContext, session: DatabaseSession
) -> CapacityReservationResponse:
    try:
        return await engineering_capacity_service.reserve(
            session, context=context, data=data
        )
    except EngineeringCapacityError as error:
        raise capacity_http_error(error) from error


@router.post("/allocations", response_model=CapacityAllocationResponse)
async def allocate_capacity(
    data: CapacityAllocationRequest, context: ManageContext, session: DatabaseSession
) -> CapacityAllocationResponse:
    try:
        return await engineering_capacity_service.allocate(
            session, context=context, data=data
        )
    except EngineeringCapacityError as error:
        raise capacity_http_error(error) from error


@router.post(
    "/reservations/{reservation_id}/release", response_model=CapacityReservationResponse
)
async def release_reservation(
    reservation_id: UUID,
    data: CapacityReleaseRequest,
    context: ManageContext,
    session: DatabaseSession,
) -> CapacityReservationResponse:
    try:
        return await engineering_capacity_service.release_reservation(
            session, context=context, reservation_id=reservation_id, data=data
        )
    except EngineeringCapacityError as error:
        raise capacity_http_error(error) from error


@router.post(
    "/allocations/{allocation_id}/release", response_model=CapacityAllocationResponse
)
async def release_allocation(
    allocation_id: UUID,
    data: CapacityReleaseRequest,
    context: ManageContext,
    session: DatabaseSession,
) -> CapacityAllocationResponse:
    try:
        return await engineering_capacity_service.release_allocation(
            session, context=context, allocation_id=allocation_id, data=data
        )
    except EngineeringCapacityError as error:
        raise capacity_http_error(error) from error


@router.post(
    "/allocations/{allocation_id}/reconcile", response_model=CapacityAllocationResponse
)
async def reconcile_allocation(
    allocation_id: UUID,
    data: CapacityReconciliationRequest,
    context: ManageContext,
    session: DatabaseSession,
) -> CapacityAllocationResponse:
    try:
        return await engineering_capacity_service.reconcile(
            session, context=context, allocation_id=allocation_id, data=data
        )
    except EngineeringCapacityError as error:
        raise capacity_http_error(error) from error


@router.post(
    "/reservations/{reservation_id}/reconcile",
    response_model=CapacityReservationResponse,
)
async def reconcile_reservation(
    reservation_id: UUID,
    data: CapacityReconciliationRequest,
    context: ManageContext,
    session: DatabaseSession,
) -> CapacityReservationResponse:
    try:
        return await engineering_capacity_service.reconcile_reservation(
            session, context=context, reservation_id=reservation_id, data=data
        )
    except EngineeringCapacityError as error:
        raise capacity_http_error(error) from error
