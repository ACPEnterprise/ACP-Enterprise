from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.customer_migration.population_reconciliation import (
    CustomerPopulationReconciliationError,
    customer_population_reconciliation_service,
)
from app.database.session import AsyncSessionFactory, get_database_session
from app.platform.idempotency.errors import reliability_http_error
from app.platform.idempotency.reliability import MutationReliabilityError
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import CustomerPermission
from app.platform.permissions.dependencies import require_permission
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

router = APIRouter(
    prefix="/api/v1/customer-migration/population",
    tags=["Customer Migration"],
)
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
CustomerManager = Annotated[
    AuthorizationContext,
    Depends(require_permission(CustomerPermission.MANAGE)),
]
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=160),
]


def get_population_session_factory() -> async_sessionmaker[AsyncSession]:
    return AsyncSessionFactory


PopulationSessionFactory = Annotated[
    async_sessionmaker[AsyncSession],
    Depends(get_population_session_factory),
]


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PopulationRefreshRequest(StrictSchema):
    source_system: Literal["housecall_pro"] = "housecall_pro"


class PopulationCountsResponse(StrictSchema):
    total: int
    bound: int
    held: int
    ambiguous: int
    unexplained: int


class PopulationRefreshResponse(StrictSchema):
    classification: Literal["CUSTOMER_POPULATION_RECONCILED"]
    run_id: UUID
    receipt_id: UUID
    replay: Literal["executed", "replayed"]
    source_system: Literal["housecall_pro"]
    counts: PopulationCountsResponse
    evidence_digest: str
    completed_at: str
    customer_admission_performed: Literal[False] = False


class CleanMajorityAdmissionRequest(StrictSchema):
    source_system: Literal["housecall_pro"] = "housecall_pro"
    limit: int = 5000


class CleanMajorityAdmissionResponse(StrictSchema):
    classification: Literal["CUSTOMER_CLEAN_MAJORITY_ADMITTED"]
    source_system: Literal["housecall_pro"]
    selected: int
    admitted: int
    replayed: int
    quarantined: int
    remaining_unexplained: int
    before_evidence_digest: str
    after_evidence_digest: str
    customer_admission_performed: Literal[True] = True


def reconciliation_error() -> HTTPException:
    failure = SafeFailure(
        FailureCode.RECONCILIATION_REQUIRED,
        "Customer population evidence could not be refreshed safely.",
        ClientRecovery.RECONCILIATION_REQUIRED,
        current_correlation_id(),
    )
    return HTTPException(status.HTTP_409_CONFLICT, detail=failure.detail())


@router.post("/refresh", response_model=PopulationRefreshResponse)
async def refresh_customer_population(
    data: PopulationRefreshRequest,
    context: CustomerManager,
    session: DatabaseSession,
    response: Response,
    idempotency_key: IdempotencyKey,
) -> PopulationRefreshResponse:
    """Record exact source-population dispositions; never admit Customers."""

    try:
        (
            run,
            disposition,
            receipt_id,
        ) = await customer_population_reconciliation_service.refresh_population_idempotent(
            session,
            context=context,
            source_system=data.source_system,
            idempotency_key=idempotency_key,
        )
    except MutationReliabilityError as error:
        raise reliability_http_error(error) from error
    except CustomerPopulationReconciliationError as error:
        raise reconciliation_error() from error
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Idempotency-Status"] = disposition.value
    return PopulationRefreshResponse(
        classification="CUSTOMER_POPULATION_RECONCILED",
        run_id=run.id,
        receipt_id=receipt_id,
        replay=disposition.value,
        source_system="housecall_pro",
        counts=PopulationCountsResponse(
            total=run.total_count,
            bound=run.bound_count,
            held=run.held_count,
            ambiguous=run.ambiguous_count,
            unexplained=run.unexplained_count,
        ),
        evidence_digest=run.evidence_digest,
        completed_at=run.completed_at.isoformat(),
    )


@router.post(
    "/admit-clean-majority",
    response_model=CleanMajorityAdmissionResponse,
)
async def admit_customer_clean_majority(
    data: CleanMajorityAdmissionRequest,
    context: CustomerManager,
    factory: PopulationSessionFactory,
    response: Response,
) -> CleanMajorityAdmissionResponse:
    """Admit exact safe HCP identities and quarantine only failed records."""

    try:
        result = await customer_population_reconciliation_service.admit_clean_majority(
            factory,
            context=context,
            source_system=data.source_system,
            limit=data.limit,
        )
    except CustomerPopulationReconciliationError as error:
        raise reconciliation_error() from error
    response.headers["Cache-Control"] = "private, no-store"
    return CleanMajorityAdmissionResponse(
        classification="CUSTOMER_CLEAN_MAJORITY_ADMITTED",
        source_system="housecall_pro",
        selected=result.selected,
        admitted=result.admitted,
        replayed=result.replayed,
        quarantined=result.quarantined,
        remaining_unexplained=result.remaining_unexplained,
        before_evidence_digest=result.before_digest,
        after_evidence_digest=result.after_digest,
    )
