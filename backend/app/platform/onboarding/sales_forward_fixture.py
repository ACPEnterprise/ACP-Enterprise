"""Governed Preview-only persistent fixture for the Sales Forward workflow."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from typing import TypeVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, settings
from app.customers.models import Customer, ServiceLocation
from app.dispatch.models import DispatchAssignment
from app.estimates.models import Estimate, EstimateLineItem, EstimateRevision
from app.invoicing.models import Invoice, InvoiceLine, ManualPaymentReceipt
from app.jobs.models import Job, JobAppointmentLink
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.branch.models import Branch
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.onboarding.preview_tenant_fixture import (
    REQUIRED_PERMISSIONS,
)
from app.platform.onboarding.service import OnboardingConflictError
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.users.models import User
from app.price_book.models import (
    PriceBookCategory,
    PriceBookPriceVersion,
    PriceBookServiceItem,
    PriceBookTaxClassification,
)
from app.scheduling.models import Appointment
from app.timekeeping.models import WorkdayPunchEvent, WorkdayTimeEntryRevision

SALES_FORWARD_FIXTURE_VERSION = "preview.synthetic.sales_forward.v1"
SALES_FORWARD_ADVISORY_LOCK_ID = 7_056_984_111_269_342
SALES_FORWARD_COMPANY_ID = UUID("7fbe4c2e-1a3d-5f67-9b80-c2d4e6f8a091")
SALES_FORWARD_BRANCH_ID = UUID("8acd5d3f-2b4e-5078-ac91-d3e5f709b102")
SALES_FORWARD_COMPANY_NAME = "Sales Forward"
SALES_FORWARD_COMPANY_CODE = "SALES_FORWARD"
SALES_FORWARD_BRANCH_NAME = "Sales Forward Main"
SALES_FORWARD_BRANCH_CODE = "SF_MAIN"

FIXTURE_USER_ID = UUID("23c53957-bc79-5d65-a363-1969fb9e0b3e")
FIXTURE_EMPLOYEE_ID = UUID("3c016d86-56de-51bd-a017-d913c0d3348a")
FIXTURE_CUSTOMER_ID = UUID("aef40633-57d0-5cec-9f4e-ec3ca187c8b8")
FIXTURE_LOCATION_ID = UUID("680c2321-59df-54af-bd8f-fb0403be5a71")
FIXTURE_CATEGORY_ID = UUID("5df19832-6b76-5d58-897a-f2e1dcd29553")
FIXTURE_TAX_ID = UUID("8d48b127-a8fc-53f5-a7c9-367bf6935bec")
FIXTURE_SERVICE_ITEM_ID = UUID("603e1912-54a6-5f6e-a038-46e63f9618f1")
FIXTURE_PRICE_VERSION_ID = UUID("565a7f1b-b9b7-54c2-a804-ac885cf5e40c")
FIXTURE_APPOINTMENT_ID = UUID("2e7a7a3a-88aa-5e81-89b9-4d78f386811e")
FIXTURE_JOB_ID = UUID("ae15afe1-3305-52f2-abf4-bc3b1e51b07e")
FIXTURE_JOB_LINK_ID = UUID("92fdb3f7-514b-5cda-bfa6-ff36d83e3986")
FIXTURE_ASSIGNMENT_ID = UUID("3410ab52-470d-5d03-888f-0e0ee27435bf")
FIXTURE_CLOCK_IN_ID = UUID("be2c8359-ab7e-50cd-86fc-4a286f2f4e65")
FIXTURE_CLOCK_OUT_ID = UUID("a6a21dde-c269-5816-ad22-025c24c76c3f")
FIXTURE_TIME_ENTRY_ID = UUID("0aa74a31-355e-55b7-bae4-d350888db3ea")
FIXTURE_TIME_REVISION_ID = UUID("9afc2e73-d377-5513-b24d-e423f7e30f16")
FIXTURE_ESTIMATE_ID = UUID("22d987d6-eb94-5e27-9463-df2960864dba")
FIXTURE_ESTIMATE_REVISION_ID = UUID("7b803ecd-0845-56f5-bd96-f91c8694b7b3")
FIXTURE_ESTIMATE_LINE_ID = UUID("01f88402-c6dd-5fb0-b176-3f546fc6bf4a")
FIXTURE_INVOICE_ID = UUID("17394ac9-d417-5d28-a238-739fc2b73ee0")
FIXTURE_INVOICE_LINE_ID = UUID("83a1ba70-9847-592f-86aa-597bbd348a30")
FIXTURE_RECEIPT_ID = UUID("5a347717-bb2b-5263-b7ef-cf82c06b0ad1")

WINDOW_START = datetime(2030, 1, 15, 14, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2030, 1, 15, 16, 0, tzinfo=timezone.utc)
PRICE_EFFECTIVE_AT = datetime(2025, 1, 1, tzinfo=timezone.utc)

ModelT = TypeVar("ModelT")


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SalesForwardFixtureCommand:
    fixture_version: str
    authorized: bool


@dataclass(frozen=True)
class SalesForwardFixtureResult:
    company_id: UUID
    branch_id: UUID
    customer_id: UUID
    appointment_id: UUID
    estimate_id: UUID
    invoice_id: UUID
    receipt_id: UUID
    action: str
    audit_record_id: UUID


class SalesForwardFixtureService:
    """Seed one deterministic, isolated scenario without external side effects."""

    def __init__(
        self,
        *,
        configuration: Settings = settings,
        auditing: AuditService = audit_service,
    ) -> None:
        self.configuration = configuration
        self.auditing = auditing

    def _authorize(
        self,
        context: AuthorizationContext,
        command: SalesForwardFixtureCommand,
    ) -> None:
        if (
            self.configuration.environment != "preview"
            or not self.configuration.preview_acceptance_fixture_enabled
            or not command.authorized
            or command.fixture_version != SALES_FORWARD_FIXTURE_VERSION
        ):
            raise OnboardingConflictError(
                "Sales Forward fixture requires explicit Preview authority."
            )
        if not REQUIRED_PERMISSIONS.issubset(context.permission_codes):
            raise OnboardingConflictError(
                "Sales Forward fixture administrator permission is missing."
            )

    async def create_or_reuse(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: SalesForwardFixtureCommand,
    ) -> SalesForwardFixtureResult:
        self._authorize(context, command)
        created = False
        async with session.begin():
            await session.execute(
                select(func.pg_advisory_xact_lock(SALES_FORWARD_ADVISORY_LOCK_ID))
            )
            _, was_created = await self._ensure(
                session,
                Company,
                SALES_FORWARD_COMPANY_ID,
                {
                    "name": SALES_FORWARD_COMPANY_NAME,
                    "code": SALES_FORWARD_COMPANY_CODE,
                    "status": "active",
                    "timezone": "America/New_York",
                },
                lambda: Company(
                    id=SALES_FORWARD_COMPANY_ID,
                    name=SALES_FORWARD_COMPANY_NAME,
                    code=SALES_FORWARD_COMPANY_CODE,
                    status="active",
                    timezone="America/New_York",
                ),
            )
            created |= was_created
            _, was_created = await self._ensure(
                session,
                Branch,
                SALES_FORWARD_BRANCH_ID,
                {
                    "company_id": SALES_FORWARD_COMPANY_ID,
                    "name": SALES_FORWARD_BRANCH_NAME,
                    "code": SALES_FORWARD_BRANCH_CODE,
                    "status": "active",
                    "timezone": "America/New_York",
                    "is_primary": True,
                },
                lambda: Branch(
                    id=SALES_FORWARD_BRANCH_ID,
                    company_id=SALES_FORWARD_COMPANY_ID,
                    name=SALES_FORWARD_BRANCH_NAME,
                    code=SALES_FORWARD_BRANCH_CODE,
                    status="active",
                    timezone="America/New_York",
                    is_primary=True,
                ),
            )
            created |= was_created
            actor, was_created = await self._ensure(
                session,
                User,
                FIXTURE_USER_ID,
                {
                    "normalized_email": "sales-forward-fixture@example.invalid",
                    "status": "active",
                },
                lambda: User(
                    id=FIXTURE_USER_ID,
                    normalized_email="sales-forward-fixture@example.invalid",
                    first_name="Synthetic",
                    last_name="Technician",
                    display_name="Synthetic Technician",
                    status="active",
                ),
            )
            created |= was_created
            _, was_created = await self._ensure(
                session,
                Employee,
                FIXTURE_EMPLOYEE_ID,
                {
                    "company_id": SALES_FORWARD_COMPANY_ID,
                    "home_branch_id": SALES_FORWARD_BRANCH_ID,
                    "employee_number": "SYN-0001",
                },
                lambda: Employee(
                    id=FIXTURE_EMPLOYEE_ID,
                    company_id=SALES_FORWARD_COMPANY_ID,
                    home_branch_id=SALES_FORWARD_BRANCH_ID,
                    employee_number="SYN-0001",
                    first_name="Synthetic",
                    last_name="Technician",
                    display_name="Synthetic Technician",
                    employee_type="employee",
                    status="active",
                    created_by_user_id=actor.id,
                    updated_by_user_id=actor.id,
                ),
            )
            created |= was_created
            _, was_created = await self._ensure(
                session,
                Customer,
                FIXTURE_CUSTOMER_ID,
                {
                    "company_id": SALES_FORWARD_COMPANY_ID,
                    "customer_number": "CUS-900001",
                },
                lambda: Customer(
                    id=FIXTURE_CUSTOMER_ID,
                    company_id=SALES_FORWARD_COMPANY_ID,
                    customer_number="CUS-900001",
                    status="active",
                    customer_type="commercial",
                    display_name="Synthetic Sales Forward Customer",
                    normalized_name="synthetic sales forward customer",
                    preferred_contact_method="email",
                    email="sales-forward-customer@example.invalid",
                    normalized_email="sales-forward-customer@example.invalid",
                ),
            )
            created |= was_created
            _, was_created = await self._ensure(
                session,
                ServiceLocation,
                FIXTURE_LOCATION_ID,
                {"customer_id": FIXTURE_CUSTOMER_ID},
                lambda: ServiceLocation(
                    id=FIXTURE_LOCATION_ID,
                    customer_id=FIXTURE_CUSTOMER_ID,
                    nickname="Synthetic Acceptance Site",
                    address="100 Synthetic Way",
                    city="Raleigh",
                    state="NC",
                    postal_code="27601",
                    country="US",
                    normalized_address="100 synthetic way raleigh nc 27601 us",
                    active=True,
                    is_primary=True,
                ),
            )
            created |= was_created
            created |= await self._ensure_price_book(session, actor.id)
            created |= await self._ensure_operations(session, actor.id)
            created |= await self._ensure_commercial_documents(session, actor.id)

            audit = self.auditing.stage(
                session,
                AuditEntry(
                    action="preview.sales_forward_fixture",
                    actor_user_id=context.user.id,
                    company_id=SALES_FORWARD_COMPANY_ID,
                    branch_id=SALES_FORWARD_BRANCH_ID,
                    resource_type="preview_sales_forward_scenario",
                    resource_id=FIXTURE_CUSTOMER_ID,
                    reason_code="operator_acceptance",
                    details={
                        "environment": "preview",
                        "fixture_version": SALES_FORWARD_FIXTURE_VERSION,
                        "action": "created" if created else "reused",
                        "provider_writes": False,
                        "money_movement": False,
                        "result": "success",
                    },
                ),
            )
            await session.flush()
            return SalesForwardFixtureResult(
                company_id=SALES_FORWARD_COMPANY_ID,
                branch_id=SALES_FORWARD_BRANCH_ID,
                customer_id=FIXTURE_CUSTOMER_ID,
                appointment_id=FIXTURE_APPOINTMENT_ID,
                estimate_id=FIXTURE_ESTIMATE_ID,
                invoice_id=FIXTURE_INVOICE_ID,
                receipt_id=FIXTURE_RECEIPT_ID,
                action="created" if created else "reused",
                audit_record_id=audit.id,
            )

    async def _ensure_price_book(self, session: AsyncSession, actor_id: UUID) -> bool:
        created = False
        for model, identity, expected, factory in (
            (
                PriceBookCategory,
                FIXTURE_CATEGORY_ID,
                {"company_id": SALES_FORWARD_COMPANY_ID, "code": "SYNTHETIC_SERVICE"},
                lambda: PriceBookCategory(
                    id=FIXTURE_CATEGORY_ID,
                    company_id=SALES_FORWARD_COMPANY_ID,
                    code="SYNTHETIC_SERVICE",
                    name="Synthetic Services",
                    status="active",
                    created_by_user_id=actor_id,
                ),
            ),
            (
                PriceBookTaxClassification,
                FIXTURE_TAX_ID,
                {"company_id": SALES_FORWARD_COMPANY_ID, "code": "SYNTHETIC_NONTAX"},
                lambda: PriceBookTaxClassification(
                    id=FIXTURE_TAX_ID,
                    company_id=SALES_FORWARD_COMPANY_ID,
                    code="SYNTHETIC_NONTAX",
                    name="Synthetic Non-Taxable",
                    taxable=False,
                    status="active",
                    created_by_user_id=actor_id,
                ),
            ),
            (
                PriceBookServiceItem,
                FIXTURE_SERVICE_ITEM_ID,
                {
                    "company_id": SALES_FORWARD_COMPANY_ID,
                    "branch_id": SALES_FORWARD_BRANCH_ID,
                    "category_id": FIXTURE_CATEGORY_ID,
                    "code": "SYN-DIAG-001",
                },
                lambda: PriceBookServiceItem(
                    id=FIXTURE_SERVICE_ITEM_ID,
                    company_id=SALES_FORWARD_COMPANY_ID,
                    branch_id=SALES_FORWARD_BRANCH_ID,
                    category_id=FIXTURE_CATEGORY_ID,
                    code="SYN-DIAG-001",
                    name="Synthetic Diagnostic Visit",
                    customer_description="Non-production diagnostic fixture service.",
                    status="active",
                    created_by_user_id=actor_id,
                ),
            ),
            (
                PriceBookPriceVersion,
                FIXTURE_PRICE_VERSION_ID,
                {
                    "company_id": SALES_FORWARD_COMPANY_ID,
                    "service_item_id": FIXTURE_SERVICE_ITEM_ID,
                    "branch_id": SALES_FORWARD_BRANCH_ID,
                    "tax_classification_id": FIXTURE_TAX_ID,
                    "currency": "USD",
                    "unit_price": Decimal("129.0000"),
                    "status": "active",
                },
                lambda: PriceBookPriceVersion(
                    id=FIXTURE_PRICE_VERSION_ID,
                    company_id=SALES_FORWARD_COMPANY_ID,
                    service_item_id=FIXTURE_SERVICE_ITEM_ID,
                    branch_id=SALES_FORWARD_BRANCH_ID,
                    tax_classification_id=FIXTURE_TAX_ID,
                    revision=1,
                    currency="USD",
                    unit_price=Decimal("129.0000"),
                    effective_at=PRICE_EFFECTIVE_AT,
                    status="active",
                    activation_reason="Approved synthetic acceptance fixture",
                    created_by_user_id=actor_id,
                    activated_by_user_id=actor_id,
                    activated_at=PRICE_EFFECTIVE_AT,
                ),
            ),
        ):
            _, was_created = await self._ensure(
                session, model, identity, expected, factory
            )
            created |= was_created
        item = await session.get(PriceBookServiceItem, FIXTURE_SERVICE_ITEM_ID)
        if item is None:
            raise OnboardingConflictError("Sales Forward price-book item is missing.")
        if item.current_version_id is None:
            item.current_version_id = FIXTURE_PRICE_VERSION_ID
            created = True
        elif item.current_version_id != FIXTURE_PRICE_VERSION_ID:
            self._collision(PriceBookServiceItem)
        return created

    async def _ensure_operations(self, session: AsyncSession, actor_id: UUID) -> bool:
        created = False
        punch_request = _digest("sales-forward-punch-request-v1")
        records = (
            (
                Appointment,
                FIXTURE_APPOINTMENT_ID,
                {
                    "company_id": SALES_FORWARD_COMPANY_ID,
                    "branch_id": SALES_FORWARD_BRANCH_ID,
                    "customer_id": FIXTURE_CUSTOMER_ID,
                    "service_location_id": FIXTURE_LOCATION_ID,
                    "status": "scheduled",
                    "arrival_window_start_at": WINDOW_START,
                    "arrival_window_end_at": WINDOW_END,
                },
                lambda: Appointment(
                    id=FIXTURE_APPOINTMENT_ID,
                    company_id=SALES_FORWARD_COMPANY_ID,
                    branch_id=SALES_FORWARD_BRANCH_ID,
                    appointment_number="APT-900001",
                    customer_id=FIXTURE_CUSTOMER_ID,
                    service_location_id=FIXTURE_LOCATION_ID,
                    status="scheduled",
                    arrival_window_start_at=WINDOW_START,
                    arrival_window_end_at=WINDOW_END,
                    expected_duration_minutes=120,
                    capacity_state="intentionally_unassigned",
                    scheduling_timezone="America/New_York",
                    created_by_user_id=actor_id,
                    updated_by_user_id=actor_id,
                ),
            ),
            (
                Job,
                FIXTURE_JOB_ID,
                {
                    "company_id": SALES_FORWARD_COMPANY_ID,
                    "branch_id": SALES_FORWARD_BRANCH_ID,
                    "customer_id": FIXTURE_CUSTOMER_ID,
                    "service_location_id": FIXTURE_LOCATION_ID,
                    "status": "ready",
                    "activated_at": WINDOW_START,
                },
                lambda: Job(
                    id=FIXTURE_JOB_ID,
                    company_id=SALES_FORWARD_COMPANY_ID,
                    branch_id=SALES_FORWARD_BRANCH_ID,
                    job_number="JOB-900001",
                    customer_id=FIXTURE_CUSTOMER_ID,
                    service_location_id=FIXTURE_LOCATION_ID,
                    status="ready",
                    job_type_code="synthetic_diagnostic",
                    priority="normal",
                    customer_reported_problem="Synthetic non-production workflow.",
                    activated_at=WINDOW_START,
                    created_by_user_id=actor_id,
                    updated_by_user_id=actor_id,
                ),
            ),
            (
                JobAppointmentLink,
                FIXTURE_JOB_LINK_ID,
                {
                    "company_id": SALES_FORWARD_COMPANY_ID,
                    "branch_id": SALES_FORWARD_BRANCH_ID,
                    "job_id": FIXTURE_JOB_ID,
                    "appointment_id": FIXTURE_APPOINTMENT_ID,
                },
                lambda: JobAppointmentLink(
                    id=FIXTURE_JOB_LINK_ID,
                    company_id=SALES_FORWARD_COMPANY_ID,
                    branch_id=SALES_FORWARD_BRANCH_ID,
                    job_id=FIXTURE_JOB_ID,
                    appointment_id=FIXTURE_APPOINTMENT_ID,
                    visit_sequence=1,
                    linked_by_user_id=actor_id,
                ),
            ),
            (
                DispatchAssignment,
                FIXTURE_ASSIGNMENT_ID,
                {
                    "company_id": SALES_FORWARD_COMPANY_ID,
                    "branch_id": SALES_FORWARD_BRANCH_ID,
                    "appointment_id": FIXTURE_APPOINTMENT_ID,
                    "job_id": FIXTURE_JOB_ID,
                    "primary_employee_id": FIXTURE_EMPLOYEE_ID,
                    "status": "assigned",
                    "window_start_at": WINDOW_START,
                    "window_end_at": WINDOW_END,
                },
                lambda: DispatchAssignment(
                    id=FIXTURE_ASSIGNMENT_ID,
                    company_id=SALES_FORWARD_COMPANY_ID,
                    branch_id=SALES_FORWARD_BRANCH_ID,
                    appointment_id=FIXTURE_APPOINTMENT_ID,
                    job_id=FIXTURE_JOB_ID,
                    primary_employee_id=FIXTURE_EMPLOYEE_ID,
                    status="assigned",
                    assignment_reason="Synthetic operator acceptance",
                    assigned_by_user_id=actor_id,
                    window_start_at=WINDOW_START,
                    window_end_at=WINDOW_END,
                    effective_at=WINDOW_START,
                ),
            ),
            (
                WorkdayPunchEvent,
                FIXTURE_CLOCK_IN_ID,
                {
                    "company_id": SALES_FORWARD_COMPANY_ID,
                    "branch_id": SALES_FORWARD_BRANCH_ID,
                    "employee_id": FIXTURE_EMPLOYEE_ID,
                    "kind": "clock_in",
                    "occurred_at": WINDOW_START,
                },
                lambda: WorkdayPunchEvent(
                    id=FIXTURE_CLOCK_IN_ID,
                    company_id=SALES_FORWARD_COMPANY_ID,
                    branch_id=SALES_FORWARD_BRANCH_ID,
                    employee_id=FIXTURE_EMPLOYEE_ID,
                    kind="clock_in",
                    occurred_at=WINDOW_START,
                    timezone="America/New_York",
                    recorded_by_user_id=actor_id,
                    source_device_reference="synthetic-preview-fixture",
                    idempotency_key="sales-forward-clock-in-v1",
                    request_digest=punch_request,
                    event_digest=_digest("sales-forward-clock-in-event-v1"),
                ),
            ),
            (
                WorkdayPunchEvent,
                FIXTURE_CLOCK_OUT_ID,
                {
                    "company_id": SALES_FORWARD_COMPANY_ID,
                    "branch_id": SALES_FORWARD_BRANCH_ID,
                    "employee_id": FIXTURE_EMPLOYEE_ID,
                    "kind": "clock_out",
                    "occurred_at": WINDOW_END,
                },
                lambda: WorkdayPunchEvent(
                    id=FIXTURE_CLOCK_OUT_ID,
                    company_id=SALES_FORWARD_COMPANY_ID,
                    branch_id=SALES_FORWARD_BRANCH_ID,
                    employee_id=FIXTURE_EMPLOYEE_ID,
                    kind="clock_out",
                    occurred_at=WINDOW_END,
                    timezone="America/New_York",
                    recorded_by_user_id=actor_id,
                    source_device_reference="synthetic-preview-fixture",
                    idempotency_key="sales-forward-clock-out-v1",
                    request_digest=punch_request,
                    event_digest=_digest("sales-forward-clock-out-event-v1"),
                ),
            ),
            (
                WorkdayTimeEntryRevision,
                FIXTURE_TIME_REVISION_ID,
                {
                    "company_id": SALES_FORWARD_COMPANY_ID,
                    "branch_id": SALES_FORWARD_BRANCH_ID,
                    "employee_id": FIXTURE_EMPLOYEE_ID,
                    "entry_id": FIXTURE_TIME_ENTRY_ID,
                    "state": "recorded",
                    "start_at": WINDOW_START,
                    "end_at": WINDOW_END,
                },
                lambda: WorkdayTimeEntryRevision(
                    id=FIXTURE_TIME_REVISION_ID,
                    entry_id=FIXTURE_TIME_ENTRY_ID,
                    revision_number=1,
                    lineage_revision_ids=[],
                    company_id=SALES_FORWARD_COMPANY_ID,
                    branch_id=SALES_FORWARD_BRANCH_ID,
                    employee_id=FIXTURE_EMPLOYEE_ID,
                    work_date=date(2030, 1, 15),
                    timezone="America/New_York",
                    provenance="employee_punch",
                    start_at=WINDOW_START,
                    end_at=WINDOW_END,
                    punch_event_ids=[
                        str(FIXTURE_CLOCK_IN_ID),
                        str(FIXTURE_CLOCK_OUT_ID),
                    ],
                    state="recorded",
                    source_user_id=actor_id,
                    responsible_user_id=actor_id,
                    evidence_digest=_digest("sales-forward-time-entry-v1"),
                ),
            ),
        )
        for model, identity, expected, factory in records:
            _, was_created = await self._ensure(
                session, model, identity, expected, factory
            )
            created |= was_created
        return created

    async def _ensure_commercial_documents(
        self, session: AsyncSession, actor_id: UUID
    ) -> bool:
        created = False
        records = (
            (
                Estimate,
                FIXTURE_ESTIMATE_ID,
                {
                    "company_id": SALES_FORWARD_COMPANY_ID,
                    "branch_id": SALES_FORWARD_BRANCH_ID,
                    "customer_id": FIXTURE_CUSTOMER_ID,
                    "service_location_id": FIXTURE_LOCATION_ID,
                    "status": "approved",
                    "acceptance_status": "approved",
                },
                lambda: Estimate(
                    id=FIXTURE_ESTIMATE_ID,
                    company_id=SALES_FORWARD_COMPANY_ID,
                    branch_id=SALES_FORWARD_BRANCH_ID,
                    customer_id=FIXTURE_CUSTOMER_ID,
                    service_location_id=FIXTURE_LOCATION_ID,
                    estimate_number="EST-900001",
                    status="approved",
                    acceptance_status="approved",
                    created_by_user_id=actor_id,
                    updated_by_user_id=actor_id,
                ),
            ),
            (
                EstimateRevision,
                FIXTURE_ESTIMATE_REVISION_ID,
                {
                    "company_id": SALES_FORWARD_COMPANY_ID,
                    "estimate_id": FIXTURE_ESTIMATE_ID,
                    "status": "issued",
                    "currency": "USD",
                    "subtotal_amount": Decimal("129.00"),
                    "total_amount": Decimal("129.00"),
                },
                lambda: EstimateRevision(
                    id=FIXTURE_ESTIMATE_REVISION_ID,
                    company_id=SALES_FORWARD_COMPANY_ID,
                    estimate_id=FIXTURE_ESTIMATE_ID,
                    revision_number=1,
                    status="issued",
                    proposal_title="Synthetic Diagnostic Visit",
                    customer_message="Synthetic non-production acceptance evidence.",
                    currency="USD",
                    subtotal_amount=Decimal("129.00"),
                    discount_amount=Decimal("0.00"),
                    taxable_basis=Decimal("0.00"),
                    tax_amount=Decimal("0.00"),
                    total_amount=Decimal("129.00"),
                    calculation_evidence={"fixture": SALES_FORWARD_FIXTURE_VERSION},
                    issued_at=WINDOW_START,
                    created_by_user_id=actor_id,
                ),
            ),
            (
                EstimateLineItem,
                FIXTURE_ESTIMATE_LINE_ID,
                {
                    "company_id": SALES_FORWARD_COMPANY_ID,
                    "revision_id": FIXTURE_ESTIMATE_REVISION_ID,
                },
                lambda: EstimateLineItem(
                    id=FIXTURE_ESTIMATE_LINE_ID,
                    company_id=SALES_FORWARD_COMPANY_ID,
                    revision_id=FIXTURE_ESTIMATE_REVISION_ID,
                    position=1,
                    title="Synthetic Diagnostic Visit",
                    description="Synthetic non-production price-book line.",
                    quantity=Decimal("1.000000"),
                    unit_price=Decimal("129.0000"),
                    line_total=Decimal("129.00"),
                    discount_allocation=Decimal("0.00"),
                    discounted_basis=Decimal("129.00"),
                    tax_amount=Decimal("0.00"),
                    taxable=False,
                    tax_classification_id=FIXTURE_TAX_ID,
                    currency="USD",
                ),
            ),
            (
                Invoice,
                FIXTURE_INVOICE_ID,
                {
                    "company_id": SALES_FORWARD_COMPANY_ID,
                    "branch_id": SALES_FORWARD_BRANCH_ID,
                    "customer_id": FIXTURE_CUSTOMER_ID,
                    "service_location_id": FIXTURE_LOCATION_ID,
                    "job_id": FIXTURE_JOB_ID,
                    "estimate_id": FIXTURE_ESTIMATE_ID,
                    "estimate_revision_id": FIXTURE_ESTIMATE_REVISION_ID,
                    "status": "issued",
                    "accounting_status": "pending",
                    "currency": "USD",
                    "total_amount": Decimal("129.00"),
                    "open_amount": Decimal("129.00"),
                },
                lambda: Invoice(
                    id=FIXTURE_INVOICE_ID,
                    company_id=SALES_FORWARD_COMPANY_ID,
                    branch_id=SALES_FORWARD_BRANCH_ID,
                    customer_id=FIXTURE_CUSTOMER_ID,
                    service_location_id=FIXTURE_LOCATION_ID,
                    job_id=FIXTURE_JOB_ID,
                    estimate_id=FIXTURE_ESTIMATE_ID,
                    estimate_revision_id=FIXTURE_ESTIMATE_REVISION_ID,
                    invoice_number="INV-900001",
                    identity_origin="native",
                    status="issued",
                    accounting_status="pending",
                    currency="USD",
                    issue_date=date(2030, 1, 15),
                    due_date=date(2030, 2, 14),
                    terms="Synthetic acceptance fixture; no payment requested.",
                    subtotal_amount=Decimal("129.00"),
                    discount_amount=Decimal("0.00"),
                    taxable_basis=Decimal("0.00"),
                    tax_amount=Decimal("0.00"),
                    total_amount=Decimal("129.00"),
                    open_amount=Decimal("129.00"),
                    calculation_digest=_digest("sales-forward-invoice-calculation-v1"),
                    issued_at=WINDOW_START,
                    created_by_user_id=actor_id,
                    updated_by_user_id=actor_id,
                ),
            ),
            (
                InvoiceLine,
                FIXTURE_INVOICE_LINE_ID,
                {
                    "company_id": SALES_FORWARD_COMPANY_ID,
                    "invoice_id": FIXTURE_INVOICE_ID,
                    "estimate_line_id": FIXTURE_ESTIMATE_LINE_ID,
                },
                lambda: InvoiceLine(
                    id=FIXTURE_INVOICE_LINE_ID,
                    company_id=SALES_FORWARD_COMPANY_ID,
                    invoice_id=FIXTURE_INVOICE_ID,
                    estimate_line_id=FIXTURE_ESTIMATE_LINE_ID,
                    position=1,
                    title="Synthetic Diagnostic Visit",
                    description="Synthetic non-production price-book line.",
                    quantity=Decimal("1.000000"),
                    unit_price=Decimal("129.0000"),
                    line_total=Decimal("129.00"),
                    discount_allocation=Decimal("0.00"),
                    discounted_basis=Decimal("129.00"),
                    taxable=False,
                    tax_classification_id=FIXTURE_TAX_ID,
                    tax_amount=Decimal("0.00"),
                    currency="USD",
                    evidence={"fixture": SALES_FORWARD_FIXTURE_VERSION},
                ),
            ),
            (
                ManualPaymentReceipt,
                FIXTURE_RECEIPT_ID,
                {
                    "company_id": SALES_FORWARD_COMPANY_ID,
                    "branch_id": SALES_FORWARD_BRANCH_ID,
                    "customer_id": FIXTURE_CUSTOMER_ID,
                    "invoice_id": FIXTURE_INVOICE_ID,
                    "amount": Decimal("1.00"),
                    "settlement_state": "not_asserted",
                    "accounting_state": "not_posted",
                },
                lambda: ManualPaymentReceipt(
                    id=FIXTURE_RECEIPT_ID,
                    company_id=SALES_FORWARD_COMPANY_ID,
                    branch_id=SALES_FORWARD_BRANCH_ID,
                    customer_id=FIXTURE_CUSTOMER_ID,
                    invoice_id=FIXTURE_INVOICE_ID,
                    payment_method="other_manual",
                    reference_label="SYNTHETIC-EVIDENCE",
                    reference_digest=_digest("sales-forward-manual-reference-v1"),
                    amount=Decimal("1.00"),
                    currency="USD",
                    occurred_at=WINDOW_END,
                    settlement_state="not_asserted",
                    accounting_state="not_posted",
                    evidence_digest=_digest("sales-forward-manual-evidence-v1"),
                    request_digest=_digest("sales-forward-manual-request-v1"),
                    idempotency_key="sales-forward-manual-receipt-v1",
                    recorded_by_user_id=actor_id,
                ),
            ),
        )
        for model, identity, expected, factory in records:
            _, was_created = await self._ensure(
                session, model, identity, expected, factory
            )
            created |= was_created
        estimate = await session.get(Estimate, FIXTURE_ESTIMATE_ID)
        if estimate is None:
            raise OnboardingConflictError("Sales Forward estimate is missing.")
        if estimate.current_revision_id is None:
            estimate.current_revision_id = FIXTURE_ESTIMATE_REVISION_ID
            created = True
        elif estimate.current_revision_id != FIXTURE_ESTIMATE_REVISION_ID:
            self._collision(Estimate)
        return created

    @classmethod
    async def _ensure(
        cls,
        session: AsyncSession,
        model: type[ModelT],
        identity: UUID,
        expected: Mapping[str, object],
        factory: Callable[[], ModelT],
    ) -> tuple[ModelT, bool]:
        record = await session.get(model, identity)
        if record is None:
            record = factory()
            session.add(record)
            await session.flush()
            return record, True
        if any(getattr(record, key) != value for key, value in expected.items()):
            cls._collision(model)
        return record, False

    @staticmethod
    def _collision(model: type[object]) -> None:
        raise OnboardingConflictError(
            f"Sales Forward fixture identity collides with {model.__name__} state."
        )


sales_forward_fixture_service = SalesForwardFixtureService()
