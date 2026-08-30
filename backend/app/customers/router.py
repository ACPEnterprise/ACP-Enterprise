from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.detail import customer_detail_service
from app.customers.errors import CustomerError, CustomerStatusTransitionError
from app.customers.launch import customer_launch_service
from app.customers.lifecycle import customer_lifecycle_service
from app.customers.schemas import (
    ContactCreate,
    ContactResponse,
    ContactUpdate,
    CustomerConsentCreate,
    CustomerConsentResponse,
    CustomerCreate,
    CustomerDetail,
    CustomerDetailResponse,
    CustomerIntakeCreate,
    CustomerIntakeResponse,
    CustomerLifecycleResponse,
    CustomerListResponse,
    CustomerNoteCreate,
    CustomerNoteResponse,
    CustomerResponse,
    CustomerSearchQuery,
    CustomerSearchResponse,
    CustomerStatusUpdate,
    CustomerTimelineResponse,
    CustomerUpdateRequest,
    DuplicateCheckRequest,
    DuplicateCheckResponse,
    ServiceLocationCreate,
    ServiceLocationResponse,
    ServiceLocationUpdate,
)
from app.customers.search import customer_search_service
from app.customers.service import customer_service
from app.customers.timeline import customer_timeline_service
from app.customers.update import customer_update_service
from app.database.session import get_database_session
from app.platform.idempotency.errors import reliability_http_error
from app.platform.idempotency.reliability import MutationReliabilityError
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import CustomerPermission
from app.platform.permissions.dependencies import require_permission
from app.platform.reliability.correlation import current_correlation_id
from app.platform.reliability.failures import ClientRecovery, FailureCode, SafeFailure

router = APIRouter(prefix="/api/v1/customers", tags=["Customers"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
CustomerReadContext = Annotated[
    AuthorizationContext, Depends(require_permission(CustomerPermission.READ))
]
CustomerManageContext = Annotated[
    AuthorizationContext, Depends(require_permission(CustomerPermission.MANAGE))
]


def not_found(error: CustomerError) -> HTTPException:
    del error
    failure = SafeFailure(
        FailureCode.NOT_FOUND,
        "Customer resource was not found.",
        ClientRecovery.TERMINAL_FAILURE,
        current_correlation_id(),
    )
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=failure.detail(),
    )


def update_error(error: CustomerError) -> HTTPException:
    if isinstance(error, CustomerStatusTransitionError):
        failure = SafeFailure(
            FailureCode.RESOURCE_STATE_CONFLICT,
            "The requested Customer status transition is not allowed.",
            ClientRecovery.RETRY_AFTER_REFRESH,
            current_correlation_id(),
        )
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=failure.detail(),
        )
    return not_found(error)


@router.get("", response_model=CustomerListResponse)
async def list_customers(
    context: CustomerReadContext,
    session: DatabaseSession,
    search: Annotated[str | None, Query(min_length=1, max_length=300)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CustomerListResponse:
    records, total = await customer_service.list_customers(
        session,
        context=context,
        search=search,
        limit=limit,
        offset=offset,
    )
    return CustomerListResponse(
        items=[CustomerResponse.model_validate(record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=CustomerDetail, status_code=status.HTTP_201_CREATED)
async def create_customer(
    data: CustomerCreate,
    context: CustomerManageContext,
    session: DatabaseSession,
    response: Response,
    idempotency_key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ] = None,
) -> CustomerDetail:
    if idempotency_key is None:
        record = await customer_service.create_customer(
            session, context=context, data=data
        )
        return CustomerDetail.model_validate(record)
    try:
        record, disposition = await customer_service.create_customer_idempotent(
            session,
            context=context,
            data=data,
            idempotency_key=idempotency_key,
        )
    except MutationReliabilityError as error:
        raise reliability_http_error(error) from error
    response.headers["Idempotency-Status"] = disposition.value
    return CustomerDetail.model_validate(record)


@router.post(
    "/intake",
    response_model=CustomerIntakeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def intake_customer(
    data: CustomerIntakeCreate,
    context: CustomerManageContext,
    session: DatabaseSession,
) -> CustomerIntakeResponse:
    try:
        return await customer_launch_service.intake(session, context=context, data=data)
    except CustomerError as error:
        raise not_found(error) from error


@router.post("/duplicate-check", response_model=DuplicateCheckResponse)
async def check_customer_duplicates(
    data: DuplicateCheckRequest,
    context: CustomerReadContext,
    session: DatabaseSession,
) -> DuplicateCheckResponse:
    try:
        return await customer_launch_service.duplicate_check(
            session, context=context, data=data
        )
    except CustomerError as error:
        raise not_found(error) from error


@router.get("/search", response_model=CustomerSearchResponse)
async def search_customers(
    criteria: Annotated[CustomerSearchQuery, Query()],
    context: CustomerReadContext,
    session: DatabaseSession,
) -> CustomerSearchResponse:
    records, total = await customer_search_service.search(
        session, context=context, criteria=criteria
    )
    return CustomerSearchResponse.build(
        items=[CustomerResponse.model_validate(record) for record in records],
        page=criteria.page,
        page_size=criteria.page_size,
        total_count=total,
    )


@router.get("/{customer_id}", response_model=CustomerDetailResponse)
async def get_customer(
    customer_id: UUID,
    context: CustomerReadContext,
    session: DatabaseSession,
) -> CustomerDetailResponse:
    try:
        return await customer_detail_service.get_detail(
            session, context=context, customer_id=customer_id
        )
    except CustomerError as error:
        raise not_found(error) from error


@router.get("/{customer_id}/timeline", response_model=CustomerTimelineResponse)
async def get_customer_timeline(
    customer_id: UUID,
    context: CustomerReadContext,
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> CustomerTimelineResponse:
    try:
        timeline = await customer_timeline_service.get_timeline(
            session,
            context=context,
            customer_id=customer_id,
            page=page,
            page_size=page_size,
        )
    except CustomerError as error:
        raise not_found(error) from error
    return CustomerTimelineResponse.build(
        items=timeline.items,
        page=page,
        page_size=page_size,
        total_count=timeline.total_count,
    )


@router.patch("/{customer_id}", response_model=CustomerDetailResponse)
async def update_customer(
    customer_id: UUID,
    data: CustomerUpdateRequest,
    context: CustomerManageContext,
    session: DatabaseSession,
) -> CustomerDetailResponse:
    try:
        return await customer_update_service.update(
            session, context=context, customer_id=customer_id, data=data
        )
    except CustomerError as error:
        raise update_error(error) from error


@router.patch("/{customer_id}/status", response_model=CustomerDetailResponse)
async def update_customer_status(
    customer_id: UUID,
    data: CustomerStatusUpdate,
    context: CustomerManageContext,
    session: DatabaseSession,
) -> CustomerDetailResponse:
    try:
        return await customer_update_service.update(
            session,
            context=context,
            customer_id=customer_id,
            data=CustomerUpdateRequest(status=data.status),
        )
    except CustomerError as error:
        raise update_error(error) from error


@router.post("/{customer_id}/archive", response_model=CustomerLifecycleResponse)
async def archive_customer(
    customer_id: UUID,
    context: CustomerManageContext,
    session: DatabaseSession,
) -> CustomerLifecycleResponse:
    try:
        return await customer_lifecycle_service.archive(
            session, context=context, customer_id=customer_id
        )
    except CustomerError as error:
        raise not_found(error) from error


@router.post("/{customer_id}/restore", response_model=CustomerLifecycleResponse)
async def restore_customer(
    customer_id: UUID,
    context: CustomerManageContext,
    session: DatabaseSession,
) -> CustomerLifecycleResponse:
    try:
        return await customer_lifecycle_service.restore(
            session, context=context, customer_id=customer_id
        )
    except CustomerError as error:
        raise not_found(error) from error


@router.get("/{customer_id}/contacts", response_model=list[ContactResponse])
async def list_contacts(
    customer_id: UUID,
    context: CustomerReadContext,
    session: DatabaseSession,
) -> list[ContactResponse]:
    try:
        records = await customer_service.list_contacts(
            session, context=context, customer_id=customer_id
        )
    except CustomerError as error:
        raise not_found(error) from error
    return [ContactResponse.model_validate(record) for record in records]


@router.post(
    "/{customer_id}/contacts",
    response_model=ContactResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_contact(
    customer_id: UUID,
    data: ContactCreate,
    context: CustomerManageContext,
    session: DatabaseSession,
) -> ContactResponse:
    try:
        record = await customer_service.add_contact(
            session, context=context, customer_id=customer_id, data=data
        )
    except CustomerError as error:
        raise not_found(error) from error
    return ContactResponse.model_validate(record)


@router.patch("/{customer_id}/contacts/{contact_id}", response_model=ContactResponse)
async def update_contact(
    customer_id: UUID,
    contact_id: UUID,
    data: ContactUpdate,
    context: CustomerManageContext,
    session: DatabaseSession,
) -> ContactResponse:
    try:
        record = await customer_service.update_contact(
            session,
            context=context,
            customer_id=customer_id,
            contact_id=contact_id,
            data=data,
        )
    except CustomerError as error:
        raise not_found(error) from error
    return ContactResponse.model_validate(record)


@router.get("/{customer_id}/locations", response_model=list[ServiceLocationResponse])
async def list_locations(
    customer_id: UUID,
    context: CustomerReadContext,
    session: DatabaseSession,
) -> list[ServiceLocationResponse]:
    try:
        records = await customer_service.list_locations(
            session, context=context, customer_id=customer_id
        )
    except CustomerError as error:
        raise not_found(error) from error
    return [ServiceLocationResponse.model_validate(record) for record in records]


@router.post(
    "/{customer_id}/locations",
    response_model=ServiceLocationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_location(
    customer_id: UUID,
    data: ServiceLocationCreate,
    context: CustomerManageContext,
    session: DatabaseSession,
) -> ServiceLocationResponse:
    try:
        record = await customer_service.add_location(
            session, context=context, customer_id=customer_id, data=data
        )
    except CustomerError as error:
        raise not_found(error) from error
    return ServiceLocationResponse.model_validate(record)


@router.patch(
    "/{customer_id}/locations/{location_id}",
    response_model=ServiceLocationResponse,
)
async def update_location(
    customer_id: UUID,
    location_id: UUID,
    data: ServiceLocationUpdate,
    context: CustomerManageContext,
    session: DatabaseSession,
) -> ServiceLocationResponse:
    try:
        record = await customer_service.update_location(
            session,
            context=context,
            customer_id=customer_id,
            location_id=location_id,
            data=data,
        )
    except CustomerError as error:
        raise not_found(error) from error
    return ServiceLocationResponse.model_validate(record)


@router.post(
    "/{customer_id}/notes",
    response_model=CustomerNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_customer_note(
    customer_id: UUID,
    data: CustomerNoteCreate,
    context: CustomerManageContext,
    session: DatabaseSession,
) -> CustomerNoteResponse:
    try:
        note = await customer_launch_service.add_note(
            session,
            context=context,
            customer_id=customer_id,
            data=data,
        )
    except CustomerError as error:
        raise not_found(error) from error
    return CustomerNoteResponse.model_validate(note)


@router.get("/{customer_id}/consents", response_model=list[CustomerConsentResponse])
async def list_customer_consents(
    customer_id: UUID,
    context: CustomerReadContext,
    session: DatabaseSession,
) -> list[CustomerConsentResponse]:
    try:
        return await customer_launch_service.list_consents(
            session, context=context, customer_id=customer_id
        )
    except CustomerError as error:
        raise not_found(error) from error


@router.post(
    "/{customer_id}/consents",
    response_model=CustomerConsentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_customer_consent(
    customer_id: UUID,
    data: CustomerConsentCreate,
    context: CustomerManageContext,
    session: DatabaseSession,
) -> CustomerConsentResponse:
    try:
        return await customer_launch_service.record_consent(
            session, context=context, customer_id=customer_id, data=data
        )
    except CustomerError as error:
        raise not_found(error) from error
