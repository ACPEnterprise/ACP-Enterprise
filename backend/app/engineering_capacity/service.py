from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.engineering_control.mobile.roadmaps import (
    EngineeringMilestone,
    EngineeringRoadmap,
)
from app.engineering_control.models import EngineeringCommand
from app.engineering_control.workstream_runtime import EngineeringWorkstreamRuntime
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.permissions.authorization import AuthorizationContext
from app.worker_control.models import EngineeringWorker
from app.worker_identity.models import WorkerCredential, WorkerIdentity

from .errors import (
    CapacityConflictError,
    CapacityNotFoundError,
    CapacityReconciliationRequiredError,
    CapacityUnavailableError,
)
from .models import (
    EngineeringCapacityAllocation,
    EngineeringCapacityEvent,
    EngineeringCapacityMachine,
    EngineeringCapacityPolicy,
    EngineeringCapacityReservation,
    EngineeringWorkerCapacity,
)
from .schemas import (
    CapacityAllocationRequest,
    CapacityAllocationResponse,
    CapacityBaselineRequest,
    CapacityDecision,
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

ACTIVE_RESERVATION_STATES = ("active", "allocated", "reconciliation_required")
ACTIVE_ALLOCATION_STATES = ("active", "reconciliation_required")
USABLE_STATES = ("available", "reserved", "occupied")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EngineeringCapacityService:
    async def observe_worker_health_in_transaction(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        worker_id: UUID,
        health: str,
        observed_at: datetime,
    ) -> None:
        """Persist authenticated health without treating heartbeat as capacity itself."""
        capacity = await session.scalar(
            select(EngineeringWorkerCapacity)
            .where(
                EngineeringWorkerCapacity.company_id == company_id,
                EngineeringWorkerCapacity.worker_id == worker_id,
            )
            .with_for_update()
        )
        if capacity is None:
            return
        capacity.health_state = health
        if capacity.operational_state not in {"paused", "reconciliation_required"}:
            if health == "unhealthy":
                capacity.operational_state = "unhealthy"
            elif health == "healthy":
                capacity.operational_state = (
                    "occupied"
                    if capacity.allocated_capacity
                    else "reserved"
                    if capacity.reserved_capacity
                    else "available"
                )
        capacity.last_reconciled_at = observed_at
        capacity.version += 1
        capacity.updated_at = observed_at

    async def summary(
        self, session: AsyncSession, *, context: AuthorizationContext
    ) -> CapacitySummaryResponse:
        company_id = context.company.id
        policy = await session.scalar(
            select(EngineeringCapacityPolicy).where(
                EngineeringCapacityPolicy.company_id == company_id
            )
        )
        rows = (
            await session.execute(
                select(EngineeringWorkerCapacity, EngineeringCapacityMachine)
                .join(
                    EngineeringCapacityMachine,
                    EngineeringCapacityMachine.id
                    == EngineeringWorkerCapacity.machine_id,
                )
                .where(EngineeringWorkerCapacity.company_id == company_id)
                .order_by(EngineeringCapacityMachine.machine_label)
            )
        ).all()
        machines = tuple(
            CapacityMachineResponse.model_validate(machine)
            for machine in (
                await session.scalars(
                    select(EngineeringCapacityMachine)
                    .where(EngineeringCapacityMachine.company_id == company_id)
                    .order_by(EngineeringCapacityMachine.machine_label)
                )
            ).all()
        )
        workers = tuple(
            self._worker_response(capacity, machine) for capacity, machine in rows
        )
        eligible_workers = await self._eligible_workers(session, company_id, workers)
        reservations = await self._reservation_responses(session, company_id)
        allocations = await self._allocation_responses(session, company_id)
        queue = await self._queue(
            session,
            company_id,
            policy,
            workers,
            eligible_workers,
            reservations,
            allocations,
        )
        configured = sum(worker.configured_limit for worker in workers)
        allocated = sum(worker.allocated_capacity for worker in workers)
        reserved = sum(worker.reserved_capacity for worker in workers)
        system_limit = policy.maximum_concurrent_workstreams if policy else 0
        available = max(0, min(configured, system_limit) - allocated - reserved)
        return CapacitySummaryResponse(
            policy=CapacityPolicyResponse.model_validate(policy) if policy else None,
            configured_capacity=configured,
            allocated_capacity=allocated,
            reserved_capacity=reserved,
            available_capacity=available,
            offline_workers=sum(
                worker.operational_state == "offline" for worker in workers
            ),
            unhealthy_workers=sum(
                worker.operational_state == "unhealthy" for worker in workers
            ),
            reconciliation_required=sum(
                worker.operational_state == "reconciliation_required"
                for worker in workers
            ),
            workers=workers,
            eligible_workers=eligible_workers,
            machines=machines,
            active_reservations=reservations,
            active_allocations=allocations,
            waiting_workstreams=queue,
        )

    async def update_policy(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: CapacityPolicyUpdate,
    ) -> CapacityPolicyResponse:
        now = utc_now()
        async with session.begin():
            policy = await session.scalar(
                select(EngineeringCapacityPolicy)
                .where(EngineeringCapacityPolicy.company_id == context.company.id)
                .with_for_update()
            )
            consumed = await self._system_consumed(session, context.company.id)
            if data.maximum_concurrent_workstreams < consumed:
                raise CapacityConflictError(
                    "System capacity cannot be reduced below active reservations and allocations."
                )
            largest_worker_use = (
                await session.scalar(
                    select(
                        func.max(
                            EngineeringWorkerCapacity.allocated_capacity
                            + EngineeringWorkerCapacity.reserved_capacity
                        )
                    ).where(EngineeringWorkerCapacity.company_id == context.company.id)
                )
                or 0
            )
            if data.maximum_per_worker < largest_worker_use:
                raise CapacityConflictError(
                    "Per-worker capacity cannot be reduced below active use."
                )
            if policy is None:
                if data.expected_version is not None:
                    raise CapacityConflictError(
                        "Capacity policy does not exist at the expected version."
                    )
                policy = EngineeringCapacityPolicy(
                    company_id=context.company.id,
                    updated_by_user_id=context.user.id,
                    **data.model_dump(exclude={"expected_version"}),
                    created_at=now,
                    updated_at=now,
                )
                session.add(policy)
                await session.flush()
            else:
                if data.expected_version != policy.version:
                    raise CapacityConflictError("Capacity policy version is stale.")
                policy.maximum_concurrent_workstreams = (
                    data.maximum_concurrent_workstreams
                )
                policy.maximum_per_worker = data.maximum_per_worker
                policy.reserved_capacity = data.reserved_capacity
                policy.auto_allocate_released_capacity = (
                    data.auto_allocate_released_capacity
                )
                policy.updated_by_user_id = context.user.id
                policy.version += 1
                policy.updated_at = now
            self._event(
                session,
                context,
                "capacity.policy_updated",
                "owner",
                f"policy:{policy.id}:{policy.version}",
                policy_id=policy.id,
            )
            self._audit(
                session,
                context,
                "engineering.capacity.policy_updated",
                policy.id,
                {
                    "maximum_concurrent_workstreams": policy.maximum_concurrent_workstreams,
                    "maximum_per_worker": policy.maximum_per_worker,
                    "reserved_capacity": policy.reserved_capacity,
                },
            )
        return CapacityPolicyResponse.model_validate(policy)

    async def add_machine(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: CapacityBaselineRequest,
    ) -> CapacityMachineResponse:
        label = " ".join(data.machine_label.split())
        async with session.begin():
            existing = await session.scalar(
                select(EngineeringCapacityMachine).where(
                    EngineeringCapacityMachine.company_id == context.company.id,
                    EngineeringCapacityMachine.machine_label == label,
                )
            )
            if existing:
                return CapacityMachineResponse.model_validate(existing)
            machine = EngineeringCapacityMachine(
                company_id=context.company.id,
                machine_label=label,
                expected_available_on=data.expected_available_on,
                enrollment_state="unenrolled",
            )
            session.add(machine)
            await session.flush()
            self._event(
                session,
                context,
                "capacity.machine_recorded",
                "owner",
                f"machine:{machine.id}",
                details={"machine_label": label, "enrollment_state": "unenrolled"},
            )
        return CapacityMachineResponse.model_validate(machine)

    async def register_worker_capacity(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: WorkerCapacityRegister,
    ) -> WorkerCapacityResponse:
        now = utc_now()
        async with session.begin():
            worker = await session.scalar(
                select(EngineeringWorker)
                .where(
                    EngineeringWorker.company_id == context.company.id,
                    EngineeringWorker.id == data.worker_id,
                )
                .with_for_update()
            )
            machine = await session.scalar(
                select(EngineeringCapacityMachine)
                .where(
                    EngineeringCapacityMachine.company_id == context.company.id,
                    EngineeringCapacityMachine.id == data.machine_id,
                )
                .with_for_update()
            )
            policy = await self._require_policy(session, context.company.id, lock=True)
            if worker is None or machine is None:
                raise CapacityNotFoundError(
                    "Worker or machine inventory record was not found."
                )
            if data.configured_limit > policy.maximum_per_worker:
                raise CapacityConflictError(
                    "Worker limit exceeds Company capacity policy."
                )
            existing = await session.scalar(
                select(EngineeringWorkerCapacity).where(
                    EngineeringWorkerCapacity.company_id == context.company.id,
                    or_(
                        EngineeringWorkerCapacity.worker_id == worker.id,
                        EngineeringWorkerCapacity.machine_id == machine.id,
                    ),
                )
            )
            if existing:
                return self._worker_response(existing, machine)
            machine.worker_id = worker.id
            machine.enrollment_state = "enrolled"
            machine.version += 1
            machine.updated_at = now
            capacity = EngineeringWorkerCapacity(
                company_id=context.company.id,
                worker_id=worker.id,
                machine_id=machine.id,
                configured_limit=data.configured_limit,
                operational_state="offline",
                health_state="unknown",
                created_at=now,
                updated_at=now,
            )
            session.add(capacity)
            await session.flush()
            self._event(
                session,
                context,
                "capacity.worker_configured",
                "owner",
                data.idempotency_key,
                worker_capacity_id=capacity.id,
            )
        return self._worker_response(capacity, machine)

    async def configure_existing_worker(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: ExistingWorkerCapacitySetup,
    ) -> WorkerCapacityResponse:
        now = utc_now()
        label = " ".join(data.machine_label.split())
        async with session.begin():
            worker = await session.scalar(
                select(EngineeringWorker)
                .join(
                    WorkerIdentity,
                    WorkerIdentity.orchestration_worker_id == EngineeringWorker.id,
                )
                .join(
                    WorkerCredential,
                    WorkerCredential.identity_id == WorkerIdentity.id,
                )
                .where(
                    EngineeringWorker.company_id == context.company.id,
                    EngineeringWorker.id == data.worker_id,
                    WorkerIdentity.company_id == context.company.id,
                    WorkerIdentity.state == "active",
                    WorkerCredential.company_id == context.company.id,
                    WorkerCredential.state == "active",
                    WorkerCredential.expires_at > now,
                )
            )
            if worker is None:
                raise CapacityConflictError(
                    "Only an existing active enrolled worker may receive capacity."
                )
            policy = await self._require_policy(session, context.company.id, lock=True)
            if data.configured_limit > min(
                policy.maximum_per_worker, policy.maximum_concurrent_workstreams
            ):
                raise CapacityConflictError(
                    "Worker limit exceeds Company capacity policy."
                )
            existing = await session.scalar(
                select(EngineeringWorkerCapacity).where(
                    EngineeringWorkerCapacity.company_id == context.company.id,
                    EngineeringWorkerCapacity.worker_id == worker.id,
                )
            )
            if existing is not None:
                machine = await session.get(
                    EngineeringCapacityMachine, existing.machine_id
                )
                if machine is None:
                    raise CapacityReconciliationRequiredError(
                        "Configured worker machine linkage is missing."
                    )
                return self._worker_response(existing, machine)
            machine = await session.scalar(
                select(EngineeringCapacityMachine)
                .where(
                    EngineeringCapacityMachine.company_id == context.company.id,
                    EngineeringCapacityMachine.machine_label == label,
                )
                .with_for_update()
            )
            if machine is not None and machine.enrollment_state != "unenrolled":
                raise CapacityConflictError(
                    "Machine label is already associated with another worker."
                )
            if machine is None:
                machine = EngineeringCapacityMachine(
                    company_id=context.company.id,
                    machine_label=label,
                    enrollment_state="unenrolled",
                    created_at=now,
                    updated_at=now,
                )
                session.add(machine)
                await session.flush()
            machine.worker_id = worker.id
            machine.enrollment_state = "enrolled"
            machine.version += 1
            machine.updated_at = now
            heartbeat_fresh = bool(
                worker.last_heartbeat_at
                and now - worker.last_heartbeat_at <= timedelta(minutes=2)
                and worker.lifecycle_state in {"available", "leased"}
            )
            capacity = EngineeringWorkerCapacity(
                company_id=context.company.id,
                worker_id=worker.id,
                machine_id=machine.id,
                configured_limit=data.configured_limit,
                operational_state="available" if heartbeat_fresh else "offline",
                health_state="healthy" if heartbeat_fresh else "unknown",
                last_reconciled_at=(
                    worker.last_heartbeat_at if heartbeat_fresh else None
                ),
                created_at=now,
                updated_at=now,
            )
            session.add(capacity)
            await session.flush()
            self._event(
                session,
                context,
                "capacity.existing_worker_configured",
                "owner",
                data.idempotency_key,
                worker_capacity_id=capacity.id,
                details={
                    "machine_label": machine.machine_label,
                    "identity_reused": True,
                },
            )
        return self._worker_response(capacity, machine)

    async def update_worker_limit(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        worker_id: UUID,
        data: WorkerCapacityUpdate,
    ) -> WorkerCapacityResponse:
        async with session.begin():
            capacity, machine = await self._require_worker(
                session, context.company.id, worker_id, lock=True
            )
            policy = await self._require_policy(session, context.company.id, lock=True)
            if data.expected_version != capacity.version:
                raise CapacityConflictError("Worker capacity version is stale.")
            if (
                data.configured_limit > policy.maximum_per_worker
                or data.configured_limit > policy.maximum_concurrent_workstreams
            ):
                raise CapacityConflictError(
                    "Worker limit exceeds Company capacity policy."
                )
            if (
                data.configured_limit
                < capacity.allocated_capacity + capacity.reserved_capacity
            ):
                raise CapacityConflictError(
                    "Worker limit cannot be reduced below active use."
                )
            capacity.configured_limit = data.configured_limit
            capacity.version += 1
            capacity.updated_at = utc_now()
            self._event(
                session,
                context,
                "capacity.worker_limit_updated",
                "owner",
                f"worker-limit:{capacity.id}:{capacity.version}",
                worker_capacity_id=capacity.id,
            )
        return self._worker_response(capacity, machine)

    async def set_worker_state(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        worker_id: UUID,
        state: str,
        data: WorkerStateUpdate,
    ) -> WorkerCapacityResponse:
        if state not in {"paused", "available"}:
            raise CapacityConflictError("Only pause or restore is owner configurable.")
        async with session.begin():
            capacity, machine = await self._require_worker(
                session, context.company.id, worker_id, lock=True
            )
            if data.expected_version != capacity.version:
                raise CapacityConflictError("Worker capacity version is stale.")
            if state == "available" and capacity.health_state != "healthy":
                raise CapacityUnavailableError(
                    "Worker cannot be restored until authoritative health is healthy."
                )
            if capacity.allocated_capacity and state == "paused":
                raise CapacityConflictError(
                    "An allocated worker cannot be paused; reconcile or release the assignment first."
                )
            capacity.operational_state = state
            capacity.version += 1
            capacity.updated_at = utc_now()
            self._event(
                session,
                context,
                f"capacity.worker_{state}",
                "owner",
                f"worker-state:{capacity.id}:{capacity.version}",
                worker_capacity_id=capacity.id,
                details={"reason": data.reason},
            )
        return self._worker_response(capacity, machine)

    async def mark_worker_reconciliation_required(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        worker_id: UUID,
        data: WorkerStateUpdate,
    ) -> WorkerCapacityResponse:
        """Hold every ambiguous slot; a disconnect never implies capacity is free."""
        async with session.begin():
            capacity, machine = await self._require_worker(
                session, context.company.id, worker_id, lock=True
            )
            if data.expected_version != capacity.version:
                raise CapacityConflictError("Worker capacity version is stale.")
            capacity.operational_state = "reconciliation_required"
            capacity.version += 1
            capacity.updated_at = utc_now()
            allocations = (
                await session.scalars(
                    select(EngineeringCapacityAllocation)
                    .where(
                        EngineeringCapacityAllocation.company_id == context.company.id,
                        EngineeringCapacityAllocation.worker_capacity_id == capacity.id,
                        EngineeringCapacityAllocation.status == "active",
                    )
                    .with_for_update()
                )
            ).all()
            for allocation in allocations:
                allocation.status = "reconciliation_required"
                allocation.version += 1
                allocation.updated_at = utc_now()
            reservations = (
                await session.scalars(
                    select(EngineeringCapacityReservation)
                    .where(
                        EngineeringCapacityReservation.company_id == context.company.id,
                        EngineeringCapacityReservation.worker_capacity_id
                        == capacity.id,
                        EngineeringCapacityReservation.status == "active",
                    )
                    .with_for_update()
                )
            ).all()
            for reservation in reservations:
                reservation.status = "reconciliation_required"
                reservation.version += 1
                reservation.updated_at = utc_now()
            self._event(
                session,
                context,
                "capacity.reconciliation_required",
                "system",
                f"worker-reconciliation:{capacity.id}:{capacity.version}",
                worker_capacity_id=capacity.id,
                details={"reason": data.reason},
            )
            self._audit(
                session,
                context,
                "engineering.capacity.reconciliation_required",
                capacity.id,
                {"reason": data.reason},
            )
        return self._worker_response(capacity, machine)

    async def reserve(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: CapacityReservationRequest,
    ) -> CapacityReservationResponse:
        now = utc_now()
        try:
            async with session.begin():
                existing = await session.scalar(
                    select(EngineeringCapacityReservation).where(
                        EngineeringCapacityReservation.company_id == context.company.id,
                        EngineeringCapacityReservation.idempotency_key
                        == data.idempotency_key,
                    )
                )
                if existing:
                    return await self._reservation_response(session, existing)
                command = await session.scalar(
                    select(EngineeringCommand)
                    .where(
                        EngineeringCommand.company_id == context.company.id,
                        EngineeringCommand.id == data.command_id,
                    )
                    .with_for_update()
                )
                if command is None:
                    raise CapacityNotFoundError("Engineering workstream was not found.")
                if command.approval_state != "approved":
                    raise CapacityConflictError(
                        "Only an approved Engineering Command may reserve capacity."
                    )
                await self._require_unambiguous_milestone(
                    session, context.company.id, command.id
                )
                policy = await self._require_policy(
                    session, context.company.id, lock=True
                )
                if (
                    await self._system_consumed(session, context.company.id)
                    >= policy.maximum_concurrent_workstreams
                ):
                    raise CapacityUnavailableError(
                        "System capacity is fully reserved or allocated."
                    )
                capacity, _ = await self._select_worker(
                    session,
                    context.company.id,
                    data.worker_id,
                    policy.maximum_per_worker,
                )
                capacity.reserved_capacity += 1
                capacity.operational_state = (
                    "reserved" if capacity.allocated_capacity == 0 else "occupied"
                )
                capacity.version += 1
                capacity.updated_at = now
                reservation = EngineeringCapacityReservation(
                    company_id=context.company.id,
                    worker_capacity_id=capacity.id,
                    command_id=command.id,
                    owner_intent_reference=data.owner_intent_reference,
                    status="active",
                    transition_source=data.transition_source,
                    idempotency_key=data.idempotency_key,
                    requested_at=now,
                    reserved_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(reservation)
                await session.flush()
                self._event(
                    session,
                    context,
                    "capacity.reserved",
                    data.transition_source,
                    f"event:{data.idempotency_key}",
                    worker_capacity_id=capacity.id,
                    reservation_id=reservation.id,
                    details={"command_id": str(command.id)},
                )
                self._audit(
                    session,
                    context,
                    "engineering.capacity.reserved",
                    reservation.id,
                    {
                        "command_id": str(command.id),
                        "worker_id": str(capacity.worker_id),
                        "transition_source": data.transition_source,
                    },
                )
            return await self._reservation_response(session, reservation)
        except IntegrityError as error:
            await session.rollback()
            raise CapacityConflictError(
                "Capacity changed concurrently; retry with authoritative state."
            ) from error

    async def allocate(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        data: CapacityAllocationRequest,
    ) -> CapacityAllocationResponse:
        now = utc_now()
        try:
            async with session.begin():
                existing = await session.scalar(
                    select(EngineeringCapacityAllocation).where(
                        EngineeringCapacityAllocation.company_id == context.company.id,
                        EngineeringCapacityAllocation.idempotency_key
                        == data.idempotency_key,
                    )
                )
                if existing:
                    return await self._allocation_response(session, existing)
                reservation = await session.scalar(
                    select(EngineeringCapacityReservation)
                    .where(
                        EngineeringCapacityReservation.company_id == context.company.id,
                        EngineeringCapacityReservation.id == data.reservation_id,
                    )
                    .with_for_update()
                )
                if reservation is None:
                    raise CapacityNotFoundError("Capacity reservation was not found.")
                if reservation.status == "allocated":
                    existing_allocation = await session.scalar(
                        select(EngineeringCapacityAllocation).where(
                            EngineeringCapacityAllocation.company_id
                            == context.company.id,
                            EngineeringCapacityAllocation.reservation_id
                            == reservation.id,
                            EngineeringCapacityAllocation.status.in_(
                                ACTIVE_ALLOCATION_STATES
                            ),
                        )
                    )
                    if existing_allocation:
                        return await self._allocation_response(
                            session, existing_allocation
                        )
                if reservation.status != "active":
                    raise CapacityConflictError(
                        "Reservation is not eligible for allocation."
                    )
                capacity, _ = await self._require_capacity_id(
                    session,
                    context.company.id,
                    reservation.worker_capacity_id,
                    lock=True,
                )
                if (
                    capacity.operational_state not in USABLE_STATES
                    or capacity.health_state != "healthy"
                ):
                    raise CapacityUnavailableError(
                        "Reserved worker is not healthy and available."
                    )
                capacity.reserved_capacity -= 1
                capacity.allocated_capacity += 1
                capacity.operational_state = "occupied"
                capacity.version += 1
                capacity.updated_at = now
                reservation.status = "allocated"
                reservation.execution_id = data.execution_id
                reservation.version += 1
                reservation.updated_at = now
                allocation = EngineeringCapacityAllocation(
                    company_id=context.company.id,
                    worker_capacity_id=capacity.id,
                    reservation_id=reservation.id,
                    command_id=reservation.command_id,
                    execution_id=data.execution_id,
                    status="active",
                    transition_source=data.transition_source,
                    idempotency_key=data.idempotency_key,
                    allocated_at=now,
                    created_at=now,
                    updated_at=now,
                )
                session.add(allocation)
                await session.flush()
                self._event(
                    session,
                    context,
                    "capacity.allocated",
                    data.transition_source,
                    f"event:{data.idempotency_key}",
                    worker_capacity_id=capacity.id,
                    reservation_id=reservation.id,
                    allocation_id=allocation.id,
                )
            return await self._allocation_response(session, allocation)
        except IntegrityError as error:
            await session.rollback()
            raise CapacityConflictError(
                "Capacity changed concurrently; duplicate allocation was rejected."
            ) from error

    async def release_reservation(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        reservation_id: UUID,
        data: CapacityReleaseRequest,
    ) -> CapacityReservationResponse:
        async with session.begin():
            reservation = await session.scalar(
                select(EngineeringCapacityReservation)
                .where(
                    EngineeringCapacityReservation.company_id == context.company.id,
                    EngineeringCapacityReservation.id == reservation_id,
                )
                .with_for_update()
            )
            if reservation is None:
                raise CapacityNotFoundError("Capacity reservation was not found.")
            if reservation.status == "released":
                return await self._reservation_response(session, reservation)
            if (
                reservation.status != "active"
                or reservation.version != data.expected_version
            ):
                raise CapacityConflictError(
                    "Reservation state or version is not releasable."
                )
            capacity, _ = await self._require_capacity_id(
                session, context.company.id, reservation.worker_capacity_id, lock=True
            )
            capacity.reserved_capacity -= 1
            self._refresh_state(capacity)
            capacity.version += 1
            reservation.status = "released"
            reservation.released_at = utc_now()
            reservation.release_reason = data.reason
            reservation.version += 1
            self._event(
                session,
                context,
                "capacity.reservation_released",
                "owner",
                data.idempotency_key,
                worker_capacity_id=capacity.id,
                reservation_id=reservation.id,
                details={"reason": data.reason},
            )
        return await self._reservation_response(session, reservation)

    async def release_allocation(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        allocation_id: UUID,
        data: CapacityReleaseRequest,
    ) -> CapacityAllocationResponse:
        async with session.begin():
            allocation = await session.scalar(
                select(EngineeringCapacityAllocation)
                .where(
                    EngineeringCapacityAllocation.company_id == context.company.id,
                    EngineeringCapacityAllocation.id == allocation_id,
                )
                .with_for_update()
            )
            if allocation is None:
                raise CapacityNotFoundError("Capacity allocation was not found.")
            if allocation.status == "released":
                return await self._allocation_response(session, allocation)
            if (
                allocation.status != "active"
                or allocation.version != data.expected_version
            ):
                raise CapacityConflictError(
                    "Allocation state or version is not releasable."
                )
            capacity, _ = await self._require_capacity_id(
                session, context.company.id, allocation.worker_capacity_id, lock=True
            )
            capacity.allocated_capacity -= 1
            self._refresh_state(capacity)
            capacity.version += 1
            allocation.status = "released"
            allocation.released_at = utc_now()
            allocation.release_reason = data.reason
            allocation.version += 1
            self._event(
                session,
                context,
                "capacity.allocation_released",
                "owner",
                data.idempotency_key,
                worker_capacity_id=capacity.id,
                allocation_id=allocation.id,
                details={"reason": data.reason},
            )
        return await self._allocation_response(session, allocation)

    async def reconcile(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        allocation_id: UUID,
        data: CapacityReconciliationRequest,
    ) -> CapacityAllocationResponse:
        async with session.begin():
            allocation = await session.scalar(
                select(EngineeringCapacityAllocation)
                .where(
                    EngineeringCapacityAllocation.company_id == context.company.id,
                    EngineeringCapacityAllocation.id == allocation_id,
                )
                .with_for_update()
            )
            if allocation is None:
                raise CapacityNotFoundError("Capacity allocation was not found.")
            if (
                allocation.status != "reconciliation_required"
                or allocation.version != data.expected_version
            ):
                raise CapacityReconciliationRequiredError(
                    "Allocation is not at the expected reconciliation state."
                )
            capacity, _ = await self._require_capacity_id(
                session, context.company.id, allocation.worker_capacity_id, lock=True
            )
            if data.resolution == "confirmed_released":
                allocation.status = "released"
                allocation.released_at = utc_now()
                allocation.release_reason = data.reason
                capacity.allocated_capacity -= 1
            else:
                allocation.status = "active"
            allocation.version += 1
            capacity.version += 1
            capacity.last_reconciled_at = utc_now()
            await self._resolve_worker_state_if_clear(session, capacity)
            self._event(
                session,
                context,
                "capacity.reconciliation_resolved",
                "owner",
                data.idempotency_key,
                worker_capacity_id=capacity.id,
                allocation_id=allocation.id,
                details={"resolution": data.resolution, "reason": data.reason},
            )
            self._audit(
                session,
                context,
                "engineering.capacity.reconciliation_resolved",
                allocation.id,
                {"resolution": data.resolution, "reason": data.reason},
            )
        return await self._allocation_response(session, allocation)

    async def reconcile_reservation(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        reservation_id: UUID,
        data: CapacityReconciliationRequest,
    ) -> CapacityReservationResponse:
        async with session.begin():
            reservation = await session.scalar(
                select(EngineeringCapacityReservation)
                .where(
                    EngineeringCapacityReservation.company_id == context.company.id,
                    EngineeringCapacityReservation.id == reservation_id,
                )
                .with_for_update()
            )
            if reservation is None:
                raise CapacityNotFoundError("Capacity reservation was not found.")
            if (
                reservation.status != "reconciliation_required"
                or reservation.version != data.expected_version
            ):
                raise CapacityReconciliationRequiredError(
                    "Reservation is not at the expected reconciliation state."
                )
            capacity, _ = await self._require_capacity_id(
                session, context.company.id, reservation.worker_capacity_id, lock=True
            )
            if data.resolution == "confirmed_released":
                reservation.status = "released"
                reservation.released_at = utc_now()
                reservation.release_reason = data.reason
                capacity.reserved_capacity -= 1
            else:
                reservation.status = "active"
            reservation.version += 1
            capacity.version += 1
            capacity.last_reconciled_at = utc_now()
            await self._resolve_worker_state_if_clear(session, capacity)
            self._event(
                session,
                context,
                "capacity.reservation_reconciliation_resolved",
                "owner",
                data.idempotency_key,
                worker_capacity_id=capacity.id,
                reservation_id=reservation.id,
                details={"resolution": data.resolution, "reason": data.reason},
            )
        return await self._reservation_response(session, reservation)

    async def _require_policy(
        self, session: AsyncSession, company_id: UUID, *, lock: bool
    ) -> EngineeringCapacityPolicy:
        statement = select(EngineeringCapacityPolicy).where(
            EngineeringCapacityPolicy.company_id == company_id
        )
        policy = await session.scalar(
            statement.with_for_update() if lock else statement
        )
        if policy is None:
            raise CapacityUnavailableError(
                "Company capacity policy is missing; capacity fails closed."
            )
        if policy.reserved_capacity > policy.maximum_concurrent_workstreams:
            raise CapacityReconciliationRequiredError(
                "Company capacity policy is contradictory."
            )
        return policy

    async def _system_consumed(self, session: AsyncSession, company_id: UUID) -> int:
        return int(
            await session.scalar(
                select(
                    func.coalesce(
                        func.sum(
                            EngineeringWorkerCapacity.allocated_capacity
                            + EngineeringWorkerCapacity.reserved_capacity
                        ),
                        0,
                    )
                ).where(EngineeringWorkerCapacity.company_id == company_id)
            )
            or 0
        )

    async def _select_worker(
        self,
        session: AsyncSession,
        company_id: UUID,
        worker_id: UUID | None,
        policy_worker_limit: int,
    ) -> tuple[EngineeringWorkerCapacity, EngineeringCapacityMachine]:
        statement = (
            select(EngineeringWorkerCapacity, EngineeringCapacityMachine)
            .join(
                EngineeringCapacityMachine,
                EngineeringCapacityMachine.id == EngineeringWorkerCapacity.machine_id,
            )
            .where(EngineeringWorkerCapacity.company_id == company_id)
        )
        if worker_id:
            statement = statement.where(
                EngineeringWorkerCapacity.worker_id == worker_id
            )
        rows = (
            await session.execute(
                statement.order_by(
                    EngineeringWorkerCapacity.allocated_capacity
                    + EngineeringWorkerCapacity.reserved_capacity,
                    EngineeringCapacityMachine.machine_label,
                ).with_for_update()
            )
        ).all()
        if not rows:
            raise CapacityUnavailableError(
                "No configured worker capacity is available."
            )
        health_blocked = False
        for capacity, machine in rows:
            if capacity.operational_state == "reconciliation_required":
                raise CapacityReconciliationRequiredError(
                    "Worker capacity requires reconciliation."
                )
            if (
                capacity.operational_state not in USABLE_STATES
                or capacity.health_state != "healthy"
            ):
                health_blocked = True
                continue
            effective_limit = min(capacity.configured_limit, policy_worker_limit)
            if (
                capacity.allocated_capacity + capacity.reserved_capacity
                < effective_limit
            ):
                return capacity, machine
        if health_blocked:
            raise CapacityUnavailableError(
                "Capacity is blocked by worker health or operational state."
            )
        raise CapacityUnavailableError(
            "All eligible worker capacity is occupied or reserved."
        )

    async def _require_worker(
        self, session: AsyncSession, company_id: UUID, worker_id: UUID, *, lock: bool
    ) -> tuple[EngineeringWorkerCapacity, EngineeringCapacityMachine]:
        statement = (
            select(EngineeringWorkerCapacity, EngineeringCapacityMachine)
            .join(
                EngineeringCapacityMachine,
                EngineeringCapacityMachine.id == EngineeringWorkerCapacity.machine_id,
            )
            .where(
                EngineeringWorkerCapacity.company_id == company_id,
                EngineeringWorkerCapacity.worker_id == worker_id,
            )
        )
        row = (
            await session.execute(statement.with_for_update() if lock else statement)
        ).one_or_none()
        if row is None:
            raise CapacityNotFoundError("Worker capacity was not found.")
        return row[0], row[1]

    async def _require_capacity_id(
        self, session: AsyncSession, company_id: UUID, capacity_id: UUID, *, lock: bool
    ) -> tuple[EngineeringWorkerCapacity, EngineeringCapacityMachine]:
        statement = (
            select(EngineeringWorkerCapacity, EngineeringCapacityMachine)
            .join(
                EngineeringCapacityMachine,
                EngineeringCapacityMachine.id == EngineeringWorkerCapacity.machine_id,
            )
            .where(
                EngineeringWorkerCapacity.company_id == company_id,
                EngineeringWorkerCapacity.id == capacity_id,
            )
        )
        row = (
            await session.execute(statement.with_for_update() if lock else statement)
        ).one_or_none()
        if row is None:
            raise CapacityNotFoundError("Worker capacity was not found.")
        return row[0], row[1]

    async def _queue(
        self,
        session: AsyncSession,
        company_id: UUID,
        policy: EngineeringCapacityPolicy | None,
        workers: tuple[WorkerCapacityResponse, ...],
        eligible_workers: tuple[EligibleWorkerResponse, ...],
        reservations: tuple[CapacityReservationResponse, ...],
        allocations: tuple[CapacityAllocationResponse, ...],
    ) -> tuple[CapacityQueueItem, ...]:
        held = {item.command_id for item in reservations} | {
            item.command_id for item in allocations
        }
        rows = (
            await session.execute(
                select(EngineeringCommand, EngineeringMilestone, EngineeringRoadmap)
                .join(
                    EngineeringMilestone,
                    EngineeringMilestone.command_id == EngineeringCommand.id,
                )
                .join(
                    EngineeringRoadmap,
                    EngineeringRoadmap.id == EngineeringMilestone.roadmap_id,
                )
                .outerjoin(
                    EngineeringWorkstreamRuntime,
                    EngineeringWorkstreamRuntime.command_id == EngineeringCommand.id,
                )
                .where(
                    EngineeringCommand.company_id == company_id,
                    EngineeringCommand.approval_state == "approved",
                    EngineeringCommand.execution_state == "execution_not_connected",
                    EngineeringMilestone.company_id == company_id,
                    EngineeringRoadmap.company_id == company_id,
                    EngineeringMilestone.status == "running",
                    or_(
                        EngineeringWorkstreamRuntime.id.is_(None),
                        EngineeringWorkstreamRuntime.runtime_state.in_(
                            ("queued", "acknowledged", "recovering")
                        ),
                    ),
                )
                .order_by(EngineeringCommand.approved_at, EngineeringCommand.created_at)
            )
        ).all()
        identities: dict[
            UUID,
            list[tuple[EngineeringCommand, EngineeringMilestone, EngineeringRoadmap]],
        ] = {}
        for command, milestone, roadmap in rows:
            identities.setdefault(command.id, []).append((command, milestone, roadmap))
        result: list[CapacityQueueItem] = []
        worker_names = {item.worker_id: item.worker_name for item in eligible_workers}
        for command_id, matches in identities.items():
            command = matches[0][0]
            if command.id in held:
                continue
            identity_resolved = len(matches) == 1
            if identity_resolved:
                _, milestone, roadmap = matches[0]
                decision, reason = self._decision(policy, workers)
                assigned = self._recommended_worker(workers, decision)
            else:
                milestone = None
                roadmap = None
                assigned = None
                decision = "reconciliation_required"
                reason = (
                    "The Engineering Command is linked to multiple active milestones; "
                    "milestone identity must be reconciled before capacity can be reserved."
                )
            result.append(
                CapacityQueueItem(
                    command_id=command_id,
                    ecid=command.ecid,
                    repository_key=command.repository_key,
                    expected_branch=command.expected_branch,
                    milestone_id=milestone.id if milestone else None,
                    milestone_title=milestone.title if milestone else None,
                    milestone_position=milestone.position if milestone else None,
                    workstream=milestone.owning_workstream if milestone else None,
                    roadmap_title=roadmap.title if roadmap else None,
                    owning_branch=milestone.owning_branch if milestone else None,
                    identity_state=(
                        "resolved" if identity_resolved else "reconciliation_required"
                    ),
                    assigned_worker_id=assigned.worker_id if assigned else None,
                    assigned_worker_name=(
                        worker_names.get(assigned.worker_id) if assigned else None
                    ),
                    machine_label=assigned.machine_label if assigned else None,
                    capacity_amount=1,
                    requested_at=command.approved_at or command.created_at,
                    decision=decision,
                    reason=reason,
                )
            )
        return tuple(result)

    async def _command_identity(
        self, session: AsyncSession, company_id: UUID, command_id: UUID
    ) -> tuple[EngineeringCommand, EngineeringMilestone, EngineeringRoadmap] | None:
        rows = (
            await session.execute(
                select(EngineeringCommand, EngineeringMilestone, EngineeringRoadmap)
                .join(
                    EngineeringMilestone,
                    EngineeringMilestone.command_id == EngineeringCommand.id,
                )
                .join(
                    EngineeringRoadmap,
                    EngineeringRoadmap.id == EngineeringMilestone.roadmap_id,
                )
                .where(
                    EngineeringCommand.company_id == company_id,
                    EngineeringCommand.id == command_id,
                    EngineeringMilestone.company_id == company_id,
                    EngineeringRoadmap.company_id == company_id,
                )
            )
        ).all()
        if len(rows) != 1:
            return None
        command, milestone, roadmap = rows[0]
        return command, milestone, roadmap

    async def _require_unambiguous_milestone(
        self, session: AsyncSession, company_id: UUID, command_id: UUID
    ) -> tuple[EngineeringCommand, EngineeringMilestone, EngineeringRoadmap]:
        identity = await self._command_identity(session, company_id, command_id)
        if identity is None:
            raise CapacityReconciliationRequiredError(
                "Engineering Command milestone identity must be reconciled before capacity can be reserved."
            )
        return identity

    @staticmethod
    def _recommended_worker(
        workers: tuple[WorkerCapacityResponse, ...], decision: CapacityDecision
    ) -> WorkerCapacityResponse | None:
        if decision != "capacity_available":
            return None
        eligible = sorted(
            (
                worker
                for worker in workers
                if worker.operational_state in USABLE_STATES
                and worker.health_state == "healthy"
                and worker.available_capacity > 0
            ),
            key=lambda worker: (
                worker.allocated_capacity + worker.reserved_capacity,
                worker.machine_label,
            ),
        )
        return eligible[0] if eligible else None

    async def _eligible_workers(
        self,
        session: AsyncSession,
        company_id: UUID,
        configured: tuple[WorkerCapacityResponse, ...],
    ) -> tuple[EligibleWorkerResponse, ...]:
        now = utc_now()
        configured_ids = {item.worker_id for item in configured}
        rows = (
            await session.execute(
                select(EngineeringWorker, WorkerIdentity)
                .join(
                    WorkerIdentity,
                    WorkerIdentity.orchestration_worker_id == EngineeringWorker.id,
                )
                .join(
                    WorkerCredential,
                    WorkerCredential.identity_id == WorkerIdentity.id,
                )
                .where(
                    EngineeringWorker.company_id == company_id,
                    WorkerIdentity.company_id == company_id,
                    WorkerIdentity.state == "active",
                    WorkerCredential.company_id == company_id,
                    WorkerCredential.state == "active",
                    WorkerCredential.expires_at > now,
                )
                .order_by(EngineeringWorker.name, EngineeringWorker.id)
            )
        ).all()
        return tuple(
            EligibleWorkerResponse(
                worker_id=worker.id,
                worker_name=worker.name,
                provider_identifier=worker.provider_identifier,
                lifecycle_state=worker.lifecycle_state,
                identity_name=identity.name,
                identity_state=identity.state,
                last_heartbeat_at=worker.last_heartbeat_at,
                health_state=(
                    "healthy"
                    if worker.last_heartbeat_at
                    and now - worker.last_heartbeat_at <= timedelta(minutes=2)
                    and worker.lifecycle_state in {"available", "leased"}
                    else "offline"
                ),
                capacity_configured=worker.id in configured_ids,
            )
            for worker, identity in rows
        )

    @staticmethod
    def _decision(
        policy: EngineeringCapacityPolicy | None,
        workers: tuple[WorkerCapacityResponse, ...],
    ) -> tuple[CapacityDecision, str]:
        if policy is None:
            return (
                "blocked_by_policy",
                "Capacity policy is missing and capacity fails closed.",
            )
        if any(
            worker.operational_state == "reconciliation_required" for worker in workers
        ):
            return (
                "reconciliation_required",
                "Ambiguous worker capacity requires authoritative reconciliation.",
            )
        usable = [
            worker
            for worker in workers
            if worker.operational_state in USABLE_STATES
            and worker.health_state == "healthy"
        ]
        if not usable:
            return (
                "blocked_by_worker_health",
                "No healthy operational worker has configured capacity.",
            )
        consumed = sum(
            worker.allocated_capacity + worker.reserved_capacity for worker in workers
        )
        if consumed >= policy.maximum_concurrent_workstreams:
            return (
                "waiting_for_capacity",
                "Company concurrent-workstream capacity is full.",
            )
        if not any(worker.available_capacity > 0 for worker in usable):
            return "waiting_for_capacity", "Per-worker capacity is full."
        return (
            "capacity_available",
            "Healthy configured capacity is available; explicit dispatch remains required.",
        )

    async def _reservation_responses(
        self, session: AsyncSession, company_id: UUID
    ) -> tuple[CapacityReservationResponse, ...]:
        rows = (
            await session.execute(
                select(EngineeringCapacityReservation, EngineeringCapacityMachine)
                .join(
                    EngineeringWorkerCapacity,
                    EngineeringWorkerCapacity.id
                    == EngineeringCapacityReservation.worker_capacity_id,
                )
                .join(
                    EngineeringCapacityMachine,
                    EngineeringCapacityMachine.id
                    == EngineeringWorkerCapacity.machine_id,
                )
                .where(
                    EngineeringCapacityReservation.company_id == company_id,
                    EngineeringCapacityReservation.status.in_(
                        ACTIVE_RESERVATION_STATES
                    ),
                )
                .order_by(EngineeringCapacityReservation.reserved_at)
            )
        ).all()
        return tuple(
            [
                await self._reservation_response_value(
                    session, item, machine.machine_label
                )
                for item, machine in rows
            ]
        )

    async def _allocation_responses(
        self, session: AsyncSession, company_id: UUID
    ) -> tuple[CapacityAllocationResponse, ...]:
        rows = (
            await session.execute(
                select(EngineeringCapacityAllocation, EngineeringCapacityMachine)
                .join(
                    EngineeringWorkerCapacity,
                    EngineeringWorkerCapacity.id
                    == EngineeringCapacityAllocation.worker_capacity_id,
                )
                .join(
                    EngineeringCapacityMachine,
                    EngineeringCapacityMachine.id
                    == EngineeringWorkerCapacity.machine_id,
                )
                .where(
                    EngineeringCapacityAllocation.company_id == company_id,
                    EngineeringCapacityAllocation.status.in_(ACTIVE_ALLOCATION_STATES),
                )
                .order_by(EngineeringCapacityAllocation.allocated_at)
            )
        ).all()
        return tuple(
            [
                await self._allocation_response_value(
                    session, item, machine.machine_label
                )
                for item, machine in rows
            ]
        )

    async def _reservation_response(
        self, session: AsyncSession, reservation: EngineeringCapacityReservation
    ) -> CapacityReservationResponse:
        _, machine = await self._require_capacity_id(
            session, reservation.company_id, reservation.worker_capacity_id, lock=False
        )
        return await self._reservation_response_value(
            session, reservation, machine.machine_label
        )

    async def _allocation_response(
        self, session: AsyncSession, allocation: EngineeringCapacityAllocation
    ) -> CapacityAllocationResponse:
        _, machine = await self._require_capacity_id(
            session, allocation.company_id, allocation.worker_capacity_id, lock=False
        )
        return await self._allocation_response_value(
            session, allocation, machine.machine_label
        )

    @staticmethod
    def _worker_response(
        capacity: EngineeringWorkerCapacity, machine: EngineeringCapacityMachine
    ) -> WorkerCapacityResponse:
        return WorkerCapacityResponse(
            id=capacity.id,
            worker_id=capacity.worker_id,
            machine_id=capacity.machine_id,
            machine_label=machine.machine_label,
            configured_limit=capacity.configured_limit,
            allocated_capacity=capacity.allocated_capacity,
            reserved_capacity=capacity.reserved_capacity,
            available_capacity=max(
                0,
                capacity.configured_limit
                - capacity.allocated_capacity
                - capacity.reserved_capacity,
            ),
            operational_state=capacity.operational_state,
            health_state=capacity.health_state,
            last_reconciled_at=capacity.last_reconciled_at,
            version=capacity.version,
        )

    async def _reservation_response_value(
        self,
        session: AsyncSession,
        item: EngineeringCapacityReservation,
        label: str,
    ) -> CapacityReservationResponse:
        identity = await self._command_identity(
            session, item.company_id, item.command_id
        )
        command, milestone, _ = identity if identity else (None, None, None)
        return CapacityReservationResponse(
            id=item.id,
            command_id=item.command_id,
            execution_id=item.execution_id,
            worker_capacity_id=item.worker_capacity_id,
            machine_label=label,
            ecid=command.ecid if command else None,
            milestone_title=milestone.title if milestone else None,
            milestone_position=milestone.position if milestone else None,
            workstream=milestone.owning_workstream if milestone else None,
            owning_branch=milestone.owning_branch if milestone else None,
            owner_intent_reference=item.owner_intent_reference,
            status=item.status,
            transition_source=item.transition_source,
            requested_at=item.requested_at,
            reserved_at=item.reserved_at,
            released_at=item.released_at,
            release_reason=item.release_reason,
            version=item.version,
        )

    async def _allocation_response_value(
        self,
        session: AsyncSession,
        item: EngineeringCapacityAllocation,
        label: str,
    ) -> CapacityAllocationResponse:
        identity = await self._command_identity(
            session, item.company_id, item.command_id
        )
        command, milestone, _ = identity if identity else (None, None, None)
        return CapacityAllocationResponse(
            id=item.id,
            reservation_id=item.reservation_id,
            command_id=item.command_id,
            execution_id=item.execution_id,
            worker_capacity_id=item.worker_capacity_id,
            machine_label=label,
            ecid=command.ecid if command else None,
            milestone_title=milestone.title if milestone else None,
            milestone_position=milestone.position if milestone else None,
            workstream=milestone.owning_workstream if milestone else None,
            owning_branch=milestone.owning_branch if milestone else None,
            status=item.status,
            transition_source=item.transition_source,
            allocated_at=item.allocated_at,
            released_at=item.released_at,
            release_reason=item.release_reason,
            version=item.version,
        )

    @staticmethod
    def _refresh_state(capacity: EngineeringWorkerCapacity) -> None:
        if capacity.operational_state in {
            "paused",
            "offline",
            "unhealthy",
            "reconciliation_required",
        }:
            return
        capacity.operational_state = (
            "occupied"
            if capacity.allocated_capacity
            else "reserved"
            if capacity.reserved_capacity
            else "available"
        )
        capacity.updated_at = utc_now()

    @staticmethod
    async def _resolve_worker_state_if_clear(
        session: AsyncSession, capacity: EngineeringWorkerCapacity
    ) -> None:
        ambiguous_allocations = await session.scalar(
            select(func.count())
            .select_from(EngineeringCapacityAllocation)
            .where(
                EngineeringCapacityAllocation.company_id == capacity.company_id,
                EngineeringCapacityAllocation.worker_capacity_id == capacity.id,
                EngineeringCapacityAllocation.status == "reconciliation_required",
            )
        )
        ambiguous_reservations = await session.scalar(
            select(func.count())
            .select_from(EngineeringCapacityReservation)
            .where(
                EngineeringCapacityReservation.company_id == capacity.company_id,
                EngineeringCapacityReservation.worker_capacity_id == capacity.id,
                EngineeringCapacityReservation.status == "reconciliation_required",
            )
        )
        if ambiguous_allocations or ambiguous_reservations:
            capacity.operational_state = "reconciliation_required"
        elif capacity.health_state != "healthy":
            capacity.operational_state = "unhealthy"
        else:
            capacity.operational_state = (
                "occupied"
                if capacity.allocated_capacity
                else "reserved"
                if capacity.reserved_capacity
                else "available"
            )
        capacity.updated_at = utc_now()

    @staticmethod
    def _event(
        session: AsyncSession,
        context: AuthorizationContext,
        event_type: str,
        source: str,
        idempotency_key: str,
        *,
        policy_id: UUID | None = None,
        worker_capacity_id: UUID | None = None,
        reservation_id: UUID | None = None,
        allocation_id: UUID | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        session.add(
            EngineeringCapacityEvent(
                company_id=context.company.id,
                event_type=event_type,
                actor_user_id=context.user.id,
                policy_id=policy_id,
                worker_capacity_id=worker_capacity_id,
                reservation_id=reservation_id,
                allocation_id=allocation_id,
                transition_source=source,
                idempotency_key=idempotency_key,
                details=details or {},
            )
        )

    @staticmethod
    def _audit(
        session: AsyncSession,
        context: AuthorizationContext,
        action: str,
        resource_id: UUID,
        details: dict[str, object],
    ) -> None:
        audit_service.stage(
            session,
            AuditEntry(
                action=action,
                resource_type="engineering_capacity",
                actor_user_id=context.user.id,
                company_id=context.company.id,
                resource_id=resource_id,
                correlation_id=uuid4(),
                details=details,
            ),
        )


engineering_capacity_service = EngineeringCapacityService()
