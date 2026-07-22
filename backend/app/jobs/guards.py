from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.authorization import AuthorizationContext


@dataclass(frozen=True)
class JobGuardContext:
    job_id: UUID
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    service_location_id: UUID
    status: str
    concurrency_version: int


class JobCompletionGuard(Protocol):
    async def validate_completion(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job: JobGuardContext,
    ) -> None: ...


class JobCancellationGuard(Protocol):
    async def validate_cancellation(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job: JobGuardContext,
    ) -> None: ...


class JobReopeningGuard(Protocol):
    async def validate_reopening(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job: JobGuardContext,
    ) -> None: ...
