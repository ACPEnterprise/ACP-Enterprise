from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounting.models import (
    Account,
    AccountingOperation,
    AccountingPeriod,
    ChartVersion,
    Journal,
    JournalLine,
)
from app.accounts_payable.models import AccountingVendor, VendorBill
from app.core.config import Settings, settings
from app.customers.models import Customer, ServiceLocation
from app.demo.models import DemoEnvironment, DemoFeedback, DemoScenario
from app.dispatch.models import DispatchAssignment
from app.estimates.models import Estimate
from app.inventory.models import InventoryItem
from app.invoicing.models import Invoice
from app.jobs.models import Job, JobAppointmentLink
from app.operational_assets.models import Asset
from app.payroll.models import PayrollRunRecord
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.platform.onboarding.service import OnboardingConflictError
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import (
    AccountingPermission,
    AnalyticsPermission,
    BeaconPermission,
    CustomerPermission,
    DispatchPermission,
    EstimatePermission,
    InventoryPermission,
    InvoicePermission,
    JobPermission,
    LuminaryPermission,
    PaymentPermission,
    PriceBookPermission,
    SchedulingPermission,
    WorkforcePermission,
)
from app.platform.permissions.models import (
    MembershipRole,
    Permission,
    Role,
    RolePermission,
)
from app.price_book.models import (
    PriceBookCategory,
    PriceBookPriceVersion,
    PriceBookServiceItem,
    PriceBookTaxClassification,
)
from app.scheduling.models import Appointment
from app.timekeeping.models import PayPeriod, WorkdayPunchEvent

SEED_VERSION = "twelvehats.sales-demo.v1"
PRESERVED_DEMO_COMPANY_ID = UUID("c36895cf-8a6f-5c31-a2ed-474dee8d0fc4")
DEMO_ROLE_CODE = "SALES_DEMO"
DEMO_ROLE_NAME = "Sales Demo"
DEMO_PERMISSION_CODES = frozenset(
    {
        *CustomerPermission.ALL,
        *SchedulingPermission.ALL,
        *JobPermission.ALL,
        *DispatchPermission.ALL,
        WorkforcePermission.READ,
        WorkforcePermission.PERFORMANCE_READ,
        InventoryPermission.READ,
        PriceBookPermission.READ,
        *EstimatePermission.ALL,
        *InvoicePermission.ALL,
        PaymentPermission.READ,
        PaymentPermission.COLLECT,
        PaymentPermission.APPLY,
        AccountingPermission.READ,
        AccountingPermission.REPORT_READ,
        AnalyticsPermission.READ,
        LuminaryPermission.READ,
        LuminaryPermission.ANALYZE,
        BeaconPermission.REVIEW,
    }
)

CUSTOMERS = (
    "Avery Bennett",
    "Morgan Brooks",
    "Jordan Carter",
    "Riley Cooper",
    "Casey Diaz",
    "Taylor Ellis",
    "Parker Flores",
    "Cameron Grant",
    "Quinn Hayes",
    "Reese Ingram",
    "Jamie Keller",
    "Skyler Lane",
    "Drew Morgan",
    "Harper Nolan",
    "Rowan Owens",
    "Emerson Price",
    "Finley Reed",
    "Sawyer Turner",
)
EMPLOYEES = (
    ("Dana", "Sterling", "Owner / Company Administrator"),
    ("Robin", "Marsh", "Office Manager"),
    ("Cory", "Vance", "Field Manager"),
    ("Blake", "Holloway", "Technician"),
    ("Sage", "Monroe", "Technician"),
    ("Lane", "Prescott", "Technician"),
    ("Arden", "Sinclair", "Technician"),
    ("Kai", "Whitaker", "Helper"),
)
PRICE_BOOK = (
    ("SERVICE-CALL", "Service Call", "89.00"),
    ("AFTER-HOURS", "After-hours Service Call", "189.00"),
    ("DRAIN-CLEAN", "Drain Cleaning", "249.00"),
    ("TOILET-AUGER", "Toilet Auger", "179.00"),
    ("SEWER-CAMERA", "Sewer Camera", "325.00"),
    ("HYDRO-JET", "Hydro Jetting", "799.00"),
    ("WH-REPAIR", "Water Heater Repair", "425.00"),
    ("WH-REPLACE", "Water Heater Replacement", "2495.00"),
    ("FAUCET-REPAIR", "Faucet Repair", "215.00"),
    ("TOILET-REPLACE", "Toilet Replacement", "575.00"),
    ("DISPOSAL", "Garbage Disposal", "495.00"),
    ("REPIPING", "Repiping", "6850.00"),
    ("SEWER-REPAIR", "Sewer Repair", "4850.00"),
    ("WATER-TREAT", "Water Treatment", "1895.00"),
)
INVENTORY = (
    ("PVC-2", "2 inch PVC Pipe"),
    ("PVC-3", "3 inch PVC Pipe"),
    ("WAX-RING", "Toilet Wax Ring"),
    ("SUPPLY-12", "12 inch Supply Line"),
    ("WH-ELEMENT", "Water Heater Element"),
    ("DISPOSAL-075", "3/4 HP Disposal"),
    ("ANGLE-STOP", "Quarter-turn Angle Stop"),
    ("PEX-050", "1/2 inch PEX Tubing"),
)


def _id(environment_id: UUID, generation: int, kind: str, index: int = 0) -> UUID:
    return uuid5(NAMESPACE_URL, f"{environment_id}:{generation}:{kind}:{index}")


@dataclass(frozen=True)
class DemoProvisionResult:
    environment_id: UUID
    company_id: UUID
    branch_id: UUID
    generation: int
    action: str
    counts: dict[str, int]


class SalesDemoService:
    def __init__(
        self,
        *,
        configuration: Settings = settings,
        auditing: AuditService = audit_service,
    ) -> None:
        self.configuration = configuration
        self.auditing = auditing

    def _guard(self) -> None:
        if (
            not self.configuration.sales_demo_enabled
            or self.configuration.environment
            not in {"development", "test", "preview", "demo"}
        ):
            raise OnboardingConflictError(
                "Sales Demo provisioning is disabled outside an authorized non-production runtime."
            )
        unsafe = (
            self.configuration.qbo_production_enabled
            or self.configuration.communications_delivery_enabled
            or self.configuration.google_ads_live_access_enabled
            or self.configuration.identity_outbox_worker_enabled
        )
        if unsafe:
            raise OnboardingConflictError(
                "Sales Demo requires all real-world delivery and production integrations to be disabled."
            )

    async def provision(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        reset: bool = False,
    ) -> DemoProvisionResult:
        self._guard()
        owner_id = context.user.id
        # Serialize first provision and reset for one representative without
        # coupling different representatives during a nationwide training burst.
        await session.execute(
            select(func.pg_advisory_xact_lock(owner_id.int % (2**63 - 1)))
        )
        environment = await session.scalar(
            select(DemoEnvironment)
            .where(DemoEnvironment.owner_user_id == owner_id)
            .with_for_update()
        )
        action = "created"
        if environment is None:
            environment = DemoEnvironment(
                id=uuid5(NAMESPACE_URL, f"sales-demo:{owner_id}"),
                owner_user_id=owner_id,
                generation=0,
                seed_version=SEED_VERSION,
                status="provisioning",
            )
            session.add(environment)
            await session.flush()
        elif (
            not reset
            and environment.status == "ready"
            and environment.active_company_id is not None
        ):
            company = await session.get(Company, environment.active_company_id)
            if company is None:
                raise OnboardingConflictError(
                    "The preserved Demo company is unavailable."
                )
            branch = await session.scalar(
                select(Branch).where(
                    Branch.company_id == company.id, Branch.is_primary.is_(True)
                )
            )
            if branch is None:
                raise OnboardingConflictError(
                    "The preserved Demo branch is unavailable."
                )
            return DemoProvisionResult(
                environment.id,
                company.id,
                branch.id,
                environment.generation,
                "reused",
                await self.counts(session, company.id),
            )
        else:
            action = "reset"
            environment.status = "resetting"
            if environment.active_company_id:
                previous = await session.get(Company, environment.active_company_id)
                if previous:
                    previous.status = "inactive"

        environment.generation += 1
        generation = environment.generation
        company_id = _id(environment.id, generation, "company")
        branch_id = _id(environment.id, generation, "branch")
        company = Company(
            id=company_id,
            name="TwelveHats Demo Services",
            code=f"DEMO_{environment.id.hex[:8].upper()}_{generation}",
            status="active",
            timezone="America/New_York",
        )
        branch = Branch(
            id=branch_id,
            company_id=company_id,
            name="Metro Demo Branch",
            code="METRO",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        session.add_all([company, branch])
        await session.flush()
        await self._seed_access(
            session, context, company_id, branch_id, environment, generation
        )
        counts = await self._seed_business(
            session, context.user.id, environment, company_id, branch_id, generation
        )
        environment.active_company_id = company_id
        environment.seed_version = SEED_VERSION
        environment.status = "ready"
        environment.reset_at = datetime.now(UTC) if action == "reset" else None
        audit = self.auditing.stage(
            session,
            AuditEntry(
                action="sales_demo.reset" if reset else "sales_demo.provision",
                actor_user_id=owner_id,
                company_id=company_id,
                branch_id=branch_id,
                resource_type="demo_environment",
                resource_id=environment.id,
                reason_code="sales_training",
                details={
                    "seed_version": SEED_VERSION,
                    "generation": generation,
                    "action": action,
                    "external_actions": "disabled",
                },
            ),
        )
        await session.flush()
        assert audit.id
        return DemoProvisionResult(
            environment.id, company_id, branch_id, generation, action, counts
        )

    async def restore_preserved_company(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
    ) -> DemoProvisionResult:
        """Restore the approved persistent training tenant for an existing user.

        This is intentionally stricter than ordinary per-representative provisioning:
        the identity must not have any access-bearing membership in another company,
        and its credential is never read or changed.
        """
        self._guard()
        owner_id = context.user.id
        await session.execute(
            select(func.pg_advisory_xact_lock(owner_id.int % (2**63 - 1)))
        )
        conflicting_company_id = await session.scalar(
            select(Membership.company_id).where(
                Membership.user_id == owner_id,
                Membership.company_id != PRESERVED_DEMO_COMPANY_ID,
                Membership.status.in_(("invited", "active", "suspended")),
            )
        )
        if conflicting_company_id is not None:
            raise OnboardingConflictError(
                "Sales Demo restoration refused: the identity has non-Demo company access."
            )

        environment = await session.scalar(
            select(DemoEnvironment)
            .where(DemoEnvironment.owner_user_id == owner_id)
            .with_for_update()
        )
        company = await session.get(Company, PRESERVED_DEMO_COMPANY_ID)
        if environment is not None or company is not None:
            if (
                environment is None
                or company is None
                or environment.active_company_id != PRESERVED_DEMO_COMPANY_ID
                or environment.status != "ready"
                or company.status != "active"
            ):
                raise OnboardingConflictError(
                    "Preserved Sales Demo state is incomplete; restoration requires an empty target or a complete ready tenant."
                )
            membership = await session.scalar(
                select(Membership).where(
                    Membership.user_id == owner_id,
                    Membership.company_id == PRESERVED_DEMO_COMPANY_ID,
                    Membership.status == "active",
                )
            )
            branch = await session.scalar(
                select(Branch).where(
                    Branch.company_id == PRESERVED_DEMO_COMPANY_ID,
                    Branch.is_primary.is_(True),
                )
            )
            if membership is None or branch is None:
                raise OnboardingConflictError(
                    "Preserved Sales Demo access is incomplete and was not changed."
                )
            return DemoProvisionResult(
                environment.id,
                company.id,
                branch.id,
                environment.generation,
                "reused",
                await self.counts(session, company.id),
            )

        environment = DemoEnvironment(
            id=uuid5(NAMESPACE_URL, f"preserved-sales-demo:{owner_id}"),
            owner_user_id=owner_id,
            generation=1,
            seed_version=SEED_VERSION,
            status="provisioning",
        )
        branch_id = _id(environment.id, 1, "branch")
        company = Company(
            id=PRESERVED_DEMO_COMPANY_ID,
            name="TwelveHats Demo Services",
            code="TWELVEHATS_DEMO_SERVICES",
            status="active",
            timezone="America/New_York",
        )
        branch = Branch(
            id=branch_id,
            company_id=company.id,
            name="Metro Demo Branch",
            code="METRO",
            status="active",
            timezone="America/New_York",
            is_primary=True,
        )
        session.add_all([environment, company, branch])
        await session.flush()
        await self._seed_access(session, context, company.id, branch.id, environment, 1)
        counts = await self._seed_business(
            session, owner_id, environment, company.id, branch.id, 1
        )
        environment.active_company_id = company.id
        environment.status = "ready"
        audit = self.auditing.stage(
            session,
            AuditEntry(
                action="sales_demo.restore_preserved",
                actor_user_id=owner_id,
                company_id=company.id,
                branch_id=branch.id,
                resource_type="demo_environment",
                resource_id=environment.id,
                reason_code="sales_training_restoration",
                details={
                    "seed_version": SEED_VERSION,
                    "credential_changed": False,
                    "external_actions": "disabled",
                },
            ),
        )
        await session.flush()
        assert audit.id
        return DemoProvisionResult(
            environment.id, company.id, branch.id, 1, "restored", counts
        )

    async def _seed_access(
        self,
        session: AsyncSession,
        context: AuthorizationContext,
        company_id: UUID,
        branch_id: UUID,
        environment: DemoEnvironment,
        generation: int,
    ) -> None:
        membership = Membership(
            id=_id(environment.id, generation, "membership"),
            user_id=context.user.id,
            company_id=company_id,
            status="active",
            default_branch_id=branch_id,
            has_all_branch_access=True,
            accepted_at=datetime.now(UTC),
        )
        role = Role(
            id=_id(environment.id, generation, "role"),
            company_id=company_id,
            code=DEMO_ROLE_CODE,
            name=DEMO_ROLE_NAME,
            description="Non-production sales and training access; no real money, payroll, tax filing, integrations, secrets, or platform administration.",
            status="active",
            is_system=True,
            created_by_user_id=context.user.id,
            updated_by_user_id=context.user.id,
        )
        session.add_all([membership, role])
        await session.flush()
        permissions = (
            await session.scalars(
                select(Permission).where(
                    Permission.code.in_(DEMO_PERMISSION_CODES),
                    Permission.status == "active",
                )
            )
        ).all()
        if {p.code for p in permissions} != DEMO_PERMISSION_CODES:
            raise OnboardingConflictError(
                "Sales Demo permission catalog is incomplete."
            )
        session.add_all(
            [
                RolePermission(
                    role_id=role.id,
                    permission_id=p.id,
                    assigned_by_user_id=context.user.id,
                )
                for p in permissions
            ]
        )

        session.add(
            MembershipRole(
                company_id=company_id,
                membership_id=membership.id,
                role_id=role.id,
                assigned_by_user_id=context.user.id,
                effective_at=datetime.now(UTC),
            )
        )

    async def _seed_business(
        self,
        session: AsyncSession,
        actor_id: UUID,
        environment: DemoEnvironment,
        company_id: UUID,
        branch_id: UUID,
        generation: int,
    ) -> dict[str, int]:
        now = datetime.now(UTC)
        customer_ids: list[UUID] = []
        location_ids: list[UUID] = []
        for index, name in enumerate(CUSTOMERS, 1):
            cid, lid = (
                _id(environment.id, generation, "customer", index),
                _id(environment.id, generation, "location", index),
            )
            customer_ids.append(cid)
            location_ids.append(lid)
            first, last = name.split(" ", 1)
            session.add(
                Customer(
                    id=cid,
                    company_id=company_id,
                    customer_number=f"CUS-{index:06d}",
                    status="active",
                    customer_type="residential",
                    display_name=name,
                    first_name=first,
                    last_name=last,
                    normalized_name=name.lower(),
                    preferred_contact_method="phone",
                    primary_phone=f"+155501{index:04d}",
                    normalized_primary_phone=f"155501{index:04d}",
                    email=f"customer{index}@example.invalid",
                    normalized_email=f"customer{index}@example.invalid",
                    notes="Fictional sales-demo customer. No external communications.",
                )
            )
            session.add(
                ServiceLocation(
                    id=lid,
                    customer_id=cid,
                    nickname="Home",
                    address=f"{100 + index} Demo Oak Lane",
                    city="Riverton",
                    state="VA",
                    postal_code=f"220{index:02d}",
                    country="US",
                    normalized_address=f"{100 + index} demo oak lane riverton va 220{index:02d}",
                    property_type="single_family",
                    is_primary=True,
                    active=True,
                )
            )
            if index in {2, 7, 13}:
                session.add(
                    ServiceLocation(
                        id=_id(environment.id, generation, "location-secondary", index),
                        customer_id=cid,
                        nickname="Rental Property",
                        address=f"{500 + index} Training Avenue",
                        city="Riverton",
                        state="VA",
                        postal_code=f"221{index:02d}",
                        country="US",
                        normalized_address=f"{500 + index} training avenue riverton va 221{index:02d}",
                        property_type="single_family",
                        is_primary=False,
                        active=True,
                    )
                )
        await session.flush()

        employee_ids: list[UUID] = []
        for index, (first, last, title) in enumerate(EMPLOYEES, 1):
            employee_ids.append(_id(environment.id, generation, "employee", index))
            session.add(
                Employee(
                    id=employee_ids[-1],
                    company_id=company_id,
                    home_branch_id=branch_id,
                    employee_number=f"DEMO-{index:03d}",
                    first_name=first,
                    last_name=last,
                    display_name=f"{first} {last}",
                    phone=f"+155502{index:04d}",
                    job_title=title,
                    employee_type="employee",
                    status="active",
                    hire_date=date(2025, 1, index),
                    created_by_user_id=actor_id,
                    updated_by_user_id=actor_id,
                )
            )

        jobs: list[Job] = []
        statuses = (
            "ready",
            "ready",
            "in_progress",
            "completed",
            "completed",
            "completed",
            "ready",
            "draft",
            "completed",
            "ready",
            "completed",
            "draft",
        )
        for index, status in enumerate(statuses, 1):
            activated = now - timedelta(days=12 - index) if status != "draft" else None
            started = (
                now - timedelta(days=10 - index)
                if status in {"in_progress", "completed"}
                else None
            )
            completed = (
                now - timedelta(days=max(1, 9 - index))
                if status == "completed"
                else None
            )
            job = Job(
                id=_id(environment.id, generation, "job", index),
                company_id=company_id,
                branch_id=branch_id,
                job_number=f"JOB-{index:06d}",
                customer_id=customer_ids[index - 1],
                service_location_id=location_ids[index - 1],
                status=status,
                job_type_code="plumbing_service",
                priority="emergency" if index == 2 else "normal",
                customer_reported_problem=(
                    "Emergency drain backup"
                    if index == 2
                    else "Synthetic plumbing service request"
                ),
                internal_description="Demo-only workflow record",
                activated_at=activated,
                started_at=started,
                completed_at=completed,
                completed_by_user_id=actor_id if completed else None,
            )
            jobs.append(job)
            session.add(job)
        await session.flush()

        # Persist real appointments, Job links, and Dispatch assignments. Two
        # tomorrow-morning visits intentionally remain unassigned for Beacon/LIA.
        for index, job in enumerate(jobs[:10], 1):
            start = (
                now
                + timedelta(days=1, hours=8 - now.hour)
                + timedelta(minutes=0 if index in {1, 2} else index * 75)
            )
            appointment_status = (
                "completed" if job.status == "completed" else "scheduled"
            )
            appointment = Appointment(
                id=_id(environment.id, generation, "appointment", index),
                company_id=company_id,
                branch_id=branch_id,
                appointment_number=f"APT-{index:06d}",
                customer_id=job.customer_id,
                service_location_id=job.service_location_id,
                status=appointment_status,
                arrival_window_start_at=start,
                arrival_window_end_at=start + timedelta(hours=2),
                expected_duration_minutes=120,
                capacity_state="intentionally_unassigned"
                if index in {1, 2}
                else "reserved",
                scheduling_timezone="America/New_York",
                created_by_user_id=actor_id,
                updated_by_user_id=actor_id,
            )
            session.add(appointment)
            await session.flush()
            session.add(
                JobAppointmentLink(
                    id=_id(environment.id, generation, "job-appointment", index),
                    company_id=company_id,
                    branch_id=branch_id,
                    job_id=job.id,
                    appointment_id=appointment.id,
                    visit_sequence=1,
                    linked_by_user_id=actor_id,
                )
            )
            if index not in {1, 2}:
                session.add(
                    DispatchAssignment(
                        id=_id(environment.id, generation, "dispatch", index),
                        company_id=company_id,
                        branch_id=branch_id,
                        appointment_id=appointment.id,
                        job_id=job.id,
                        primary_employee_id=employee_ids[3 + (index % 4)],
                        status="assigned",
                        assignment_reason="Synthetic sales-demo assignment",
                        assigned_by_user_id=actor_id,
                        window_start_at=start,
                        window_end_at=start + timedelta(hours=2),
                        effective_at=now,
                    )
                )

        category = PriceBookCategory(
            id=_id(environment.id, generation, "price-category"),
            company_id=company_id,
            code="PLUMBING",
            name="Plumbing Services",
            description="Synthetic demo catalog",
            position=1,
            status="active",
            created_by_user_id=actor_id,
        )
        tax = PriceBookTaxClassification(
            id=_id(environment.id, generation, "tax"),
            company_id=company_id,
            code="DEMO-TAXABLE",
            name="Demo Taxable",
            taxable=True,
            status="active",
            created_by_user_id=actor_id,
        )
        session.add_all([category, tax])
        await session.flush()
        for index, (code, name, price) in enumerate(PRICE_BOOK, 1):
            item_id, version_id = (
                _id(environment.id, generation, "price-item", index),
                _id(environment.id, generation, "price-version", index),
            )
            item = PriceBookServiceItem(
                id=item_id,
                company_id=company_id,
                branch_id=None,
                category_id=category.id,
                code=code,
                name=name,
                customer_description=f"Demo {name.lower()} service",
                internal_description="Synthetic pricing; not ACP pricing",
                status="active",
                current_version_id=None,
                created_by_user_id=actor_id,
            )
            session.add(item)
            await session.flush()
            version = PriceBookPriceVersion(
                id=version_id,
                company_id=company_id,
                service_item_id=item_id,
                branch_id=None,
                tax_classification_id=tax.id,
                revision=1,
                currency="USD",
                unit_price=Decimal(price),
                effective_at=now - timedelta(days=180),
                status="active",
                activation_reason="Synthetic sales demonstration",
                created_by_user_id=actor_id,
                activated_by_user_id=actor_id,
                activated_at=now - timedelta(days=180),
            )
            session.add(version)
            await session.flush()
            item.current_version_id = version_id

        for index, (code, name) in enumerate(INVENTORY, 1):
            session.add(
                InventoryItem(
                    id=_id(environment.id, generation, "inventory", index),
                    company_id=company_id,
                    code=code,
                    name=name,
                    stocking_unit="each",
                    allow_fractional=False,
                    status="active",
                    created_by_user_id=actor_id,
                    updated_by_user_id=actor_id,
                )
            )

        for index in range(1, 7):
            session.add(
                Estimate(
                    id=_id(environment.id, generation, "estimate", index),
                    company_id=company_id,
                    branch_id=branch_id,
                    customer_id=customer_ids[index + 5],
                    service_location_id=location_ids[index + 5],
                    estimate_number=f"EST-{index:06d}",
                    status="approved"
                    if index in {1, 3}
                    else ("rejected" if index == 2 else "draft"),
                    acceptance_status="approved"
                    if index in {1, 3}
                    else ("rejected" if index == 2 else "not_requested"),
                    created_by_user_id=actor_id,
                    updated_by_user_id=actor_id,
                )
            )

        for index, job in enumerate([j for j in jobs if j.status == "completed"], 1):
            total = (
                Decimal("1295.00")
                if index == 1
                else Decimal("425.00") + Decimal(index * 75)
            )
            open_amount = (
                total
                if index == 1
                else (Decimal("250.00") if index == 2 else Decimal("0.00"))
            )
            session.add(
                Invoice(
                    id=_id(environment.id, generation, "invoice", index),
                    company_id=company_id,
                    branch_id=branch_id,
                    customer_id=job.customer_id,
                    service_location_id=job.service_location_id,
                    job_id=job.id,
                    invoice_number=f"INV-{index:06d}",
                    identity_origin="native",
                    status="issued"
                    if open_amount == total
                    else ("partially_paid" if open_amount else "paid"),
                    accounting_status="posted",
                    currency="USD",
                    issue_date=datetime.now(UTC).date()
                    - timedelta(days=45 if index == 1 else index * 4),
                    due_date=datetime.now(UTC).date() - timedelta(days=15)
                    if index == 1
                    else datetime.now(UTC).date() + timedelta(days=20),
                    terms="Demo Net 30",
                    subtotal_amount=total,
                    discount_amount=Decimal(0),
                    taxable_basis=total,
                    tax_amount=Decimal(0),
                    total_amount=total,
                    open_amount=open_amount,
                    calculation_digest=f"demo-{environment.id.hex}-{generation}-{index}".ljust(
                        64, "0"
                    )[:64],
                    legacy_evidence_missing=False,
                    issued_at=now - timedelta(days=45 if index == 1 else index * 4),
                    created_by_user_id=actor_id,
                    updated_by_user_id=actor_id,
                )
            )

        accounting_period_ids: list[UUID] = []
        for offset in range(3):
            period_start: date = (
                datetime.now(UTC).date().replace(day=1) - timedelta(days=offset * 31)
            ).replace(day=1)
            end = (period_start.replace(day=28) + timedelta(days=4)).replace(
                day=1
            ) - timedelta(days=1)
            period_id = _id(environment.id, generation, "period", offset)
            accounting_period_ids.append(period_id)
            session.add(
                AccountingPeriod(
                    id=period_id,
                    company_id=company_id,
                    name=period_start.strftime("%B %Y"),
                    start_date=period_start,
                    end_date=end,
                    status="open" if offset == 0 else "closed",
                    created_by_user_id=actor_id,
                )
            )
        await self._seed_accounting_history(
            session,
            actor_id=actor_id,
            environment=environment,
            company_id=company_id,
            branch_id=branch_id,
            generation=generation,
            period_id=accounting_period_ids[0],
            now=now,
        )

        for index, (name, vendor_total_text, open_amount_text) in enumerate(
            (
                ("Demo Plumbing Supply", "875.00", "875.00"),
                ("Synthetic Fleet Service", "420.00", "0.00"),
                ("Training Warehouse Rent", "1800.00", "1800.00"),
            ),
            1,
        ):
            vendor_id = _id(environment.id, generation, "vendor", index)
            session.add(
                AccountingVendor(
                    id=vendor_id,
                    company_id=company_id,
                    code=f"DEMO-V{index:03d}",
                    legal_name=name,
                    display_name=name,
                    status="active",
                    default_terms="Demo Net 30",
                    provenance="synthetic_demo",
                    created_by_user_id=actor_id,
                )
            )
            await session.flush()
            amount = Decimal(vendor_total_text)
            remaining = Decimal(open_amount_text)
            session.add(
                VendorBill(
                    id=_id(environment.id, generation, "vendor-bill", index),
                    company_id=company_id,
                    branch_id=branch_id,
                    vendor_id=vendor_id,
                    bill_number=f"BILL-{index:06d}",
                    vendor_document_number=f"DEMO-DOC-{generation}-{index}",
                    normalized_document_number=f"demo-doc-{generation}-{index}",
                    bill_date=datetime.now(UTC).date() - timedelta(days=index * 9),
                    received_date=datetime.now(UTC).date() - timedelta(days=index * 9),
                    due_date=datetime.now(UTC).date() + timedelta(days=30 - index * 9),
                    terms_snapshot="Demo Net 30",
                    currency="USD",
                    status="paid" if remaining == 0 else "posted",
                    accounting_status="posted",
                    total_amount=amount,
                    open_amount=remaining,
                    source_system="sales_demo",
                    source_identity=f"demo-bill:{environment.id}:{generation}:{index}",
                    source_digest=f"bill-{environment.id.hex}-{generation}-{index}".ljust(
                        64, "0"
                    )[:64],
                    evidence_reference="Synthetic sales demo; no external payment",
                    prepared_by_user_id=actor_id,
                    approved_by_user_id=actor_id,
                )
            )

        session.add_all(
            [
                AccountingOperation(
                    id=_id(environment.id, generation, "margin-operation"),
                    company_id=company_id,
                    kind="job_cost",
                    reference=f"demo-margin:{jobs[4].id}",
                    status="posted",
                    effective_date=datetime.now(UTC).date() - timedelta(days=4),
                    amount=Decimal("1680.00"),
                    currency="USD",
                    payload={
                        "job_id": str(jobs[4].id),
                        "revenue": "1350.00",
                        "labor_cost": "980.00",
                        "material_cost": "700.00",
                        "margin": "-330.00",
                    },
                    provenance={"classification": "synthetic_demo"},
                    created_by_user_id=actor_id,
                ),
                AccountingOperation(
                    id=_id(environment.id, generation, "inventory-shortage"),
                    company_id=company_id,
                    kind="inventory_usage",
                    reference=f"demo-shortage:{jobs[6].id}",
                    status="active",
                    effective_date=datetime.now(UTC).date() + timedelta(days=2),
                    amount=Decimal("3.00"),
                    currency="USD",
                    payload={
                        "job_id": str(jobs[6].id),
                        "inventory_code": "WH-ELEMENT",
                        "required_quantity": "3",
                        "available_quantity": "1",
                    },
                    provenance={"classification": "synthetic_demo"},
                    created_by_user_id=actor_id,
                ),
            ]
        )

        await self._seed_workforce_history(
            session,
            actor_id=actor_id,
            environment=environment,
            company_id=company_id,
            branch_id=branch_id,
            generation=generation,
            employee_ids=employee_ids,
            now=now,
        )
        scenarios = self._scenario_specs(environment, generation, jobs, customer_ids)
        session.add_all(
            [
                DemoScenario(
                    id=_id(environment.id, generation, "scenario", i),
                    environment_id=environment.id,
                    company_id=company_id,
                    code=spec[0],
                    title=spec[1],
                    position=i,
                    guided_steps=spec[2],
                    condition=spec[3],
                    record_refs=spec[4],
                )
                for i, spec in enumerate(scenarios, 1)
            ]
        )
        await session.flush()
        return await self.counts(session, company_id)

    async def _seed_accounting_history(
        self,
        session: AsyncSession,
        *,
        actor_id: UUID,
        environment: DemoEnvironment,
        company_id: UUID,
        branch_id: UUID,
        generation: int,
        period_id: UUID,
        now: datetime,
    ) -> None:
        chart_id = _id(environment.id, generation, "chart")
        session.add(
            ChartVersion(
                id=chart_id,
                company_id=company_id,
                version=1,
                name="Synthetic Demo Chart of Accounts",
                currency="USD",
                accounting_basis="accrual",
                source_checksum=f"demo-chart-{environment.id.hex}-{generation}".ljust(
                    64, "0"
                )[:64],
                effective_at=now - timedelta(days=365),
                is_active=True,
                approved_by_user_id=actor_id,
            )
        )
        # The account FK is composite and SQLAlchemy has no relationship here from
        # which to infer insert ordering, so make the chart durable first.
        await session.flush()
        definitions = (
            ("1000", "Demo Operating Cash", "asset", "debit"),
            ("1100", "Accounts Receivable", "asset", "debit"),
            ("2000", "Accounts Payable", "liability", "credit"),
            ("2100", "Payroll Liabilities", "liability", "credit"),
            ("4000", "Plumbing Service Revenue", "revenue", "credit"),
            ("5000", "Materials and Job Costs", "expense", "debit"),
            ("5100", "Payroll Expense", "expense", "debit"),
        )
        accounts: dict[str, UUID] = {}
        for index, (code, name, classification, normal_balance) in enumerate(
            definitions, 1
        ):
            account_id = _id(environment.id, generation, "account", index)
            accounts[code] = account_id
            session.add(
                Account(
                    id=account_id,
                    company_id=company_id,
                    chart_version_id=chart_id,
                    code=code,
                    name=name,
                    classification=classification,
                    normal_balance=normal_balance,
                    status="active",
                    effective_from=datetime.now(UTC).date() - timedelta(days=365),
                )
            )
        await session.flush()
        postings = (
            ("Demo invoiced service revenue", "1100", "4000", "8450.00"),
            ("Demo customer receipts", "1000", "1100", "6905.00"),
            ("Demo material and job cost", "5000", "2000", "2310.00"),
            ("Demo payroll accrual", "5100", "2100", "9064.13"),
            ("Demo vendor payments", "2000", "1000", "420.00"),
            ("Demo payroll liability payment", "2100", "1000", "6673.60"),
        )
        for index, (description, debit_code, credit_code, amount_text) in enumerate(
            postings, 1
        ):
            amount = Decimal(amount_text)
            journal_id = _id(environment.id, generation, "journal", index)
            journal = Journal(
                id=journal_id,
                company_id=company_id,
                period_id=period_id,
                journal_type="automated",
                status="draft",
                effective_date=datetime.now(UTC).date() - timedelta(days=index),
                currency="USD",
                description=description,
                total_debits=amount,
                total_credits=amount,
                source_system="sales_demo",
                source_type="synthetic_history",
                source_identity=f"demo-journal:{generation}:{index}",
                source_digest=f"demo-journal-{environment.id.hex}-{generation}-{index}".ljust(
                    64, "0"
                )[:64],
                posting_rule_version="sales-demo-v1",
                client_idempotency_key=f"demo-journal-{environment.id}-{generation}-{index}",
                prepared_by_user_id=actor_id,
                approved_by_user_id=None,
                posted_at=None,
            )
            session.add(journal)
            await session.flush()
            session.add_all(
                [
                    JournalLine(
                        id=_id(environment.id, generation, f"journal-{index}-line", 1),
                        company_id=company_id,
                        journal_id=journal_id,
                        ordinal=1,
                        account_id=accounts[debit_code],
                        branch_id=branch_id,
                        debit=amount,
                        credit=Decimal(0),
                        description=description,
                    ),
                    JournalLine(
                        id=_id(environment.id, generation, f"journal-{index}-line", 2),
                        company_id=company_id,
                        journal_id=journal_id,
                        ordinal=2,
                        account_id=accounts[credit_code],
                        branch_id=branch_id,
                        debit=Decimal(0),
                        credit=amount,
                        description=description,
                    ),
                ]
            )
            await session.flush()
            journal.status = "posted"
            journal.approved_by_user_id = actor_id
            journal.posted_at = now - timedelta(days=index)
            await session.flush()

    async def _seed_workforce_history(
        self,
        session: AsyncSession,
        *,
        actor_id: UUID,
        environment: DemoEnvironment,
        company_id: UUID,
        branch_id: UUID,
        generation: int,
        employee_ids: list[UUID],
        now: datetime,
    ) -> None:
        for index, display_name in enumerate(
            (
                "Demo Service Van 1",
                "Demo Service Van 2",
                "Sewer Camera Kit",
                "Hydro Jetting Trailer",
            ),
            1,
        ):
            session.add(
                Asset(
                    id=_id(environment.id, generation, "asset", index),
                    company_id=company_id,
                    branch_id=branch_id,
                    asset_number=f"DEMO-ASSET-{index:03d}",
                    asset_class="vehicle" if index < 3 else "equipment",
                    display_name=display_name,
                    lifecycle="active",
                    provenance={"classification": "synthetic_demo"},
                    identity_digest=f"asset-identity-{environment.id.hex}-{generation}-{index}".ljust(
                        64, "0"
                    )[:64],
                    request_digest=f"asset-request-{environment.id.hex}-{generation}-{index}".ljust(
                        64, "0"
                    )[:64],
                    idempotency_key=f"demo-asset-{environment.id}-{generation}-{index}",
                    created_by_user_id=actor_id,
                )
            )
        period_end = datetime.now(UTC).date() - timedelta(
            days=datetime.now(UTC).date().weekday() + 3
        )
        pay_period = PayPeriod(
            id=_id(environment.id, generation, "pay-period"),
            company_id=company_id,
            period_start=period_end - timedelta(days=13),
            period_end=period_end,
            processing_date=period_end + timedelta(days=2),
            payday=period_end + timedelta(days=4),
            timezone="America/New_York",
            schedule_definition_id="demo-biweekly",
            schedule_version=1,
            created_by_user_id=actor_id,
        )
        session.add(pay_period)
        await session.flush()
        for employee_index, employee_id in enumerate(employee_ids[3:], 1):
            for punch_index, (kind, hour) in enumerate(
                (("clock_in", 8), ("clock_out", 16)), 1
            ):
                occurred = now - timedelta(days=employee_index, hours=now.hour - hour)
                session.add(
                    WorkdayPunchEvent(
                        id=_id(
                            environment.id,
                            generation,
                            f"punch-{employee_index}",
                            punch_index,
                        ),
                        company_id=company_id,
                        branch_id=branch_id,
                        employee_id=employee_id,
                        kind=kind,
                        occurred_at=occurred,
                        timezone="America/New_York",
                        recorded_by_user_id=actor_id,
                        source_device_reference="synthetic-demo-device",
                        idempotency_key=f"demo-punch-{generation}-{employee_index}-{punch_index}",
                        request_digest=f"punch-request-{environment.id.hex}-{generation}-{employee_index}-{punch_index}".ljust(
                            64, "0"
                        )[:64],
                        event_digest=f"punch-event-{environment.id.hex}-{generation}-{employee_index}-{punch_index}".ljust(
                            64, "0"
                        )[:64],
                    )
                )
        session.add(
            PayrollRunRecord(
                id=_id(environment.id, generation, "payroll-run"),
                company_id=company_id,
                pay_period_id=pay_period.id,
                schedule_definition_id="demo-biweekly",
                schedule_version="1",
                assembly_version="sales-demo-v1",
                population_identity=f"demo-workforce-{generation}",
                population_digest=f"payroll-population-{environment.id.hex}-{generation}".ljust(
                    64, "0"
                )[:64],
                currency="USD",
                run_identity=f"DEMO-PAYROLL-{generation}",
                run_digest=f"payroll-run-{environment.id.hex}-{generation}".ljust(
                    64, "0"
                )[:64],
                aggregate_gross=Decimal("8420.00"),
                aggregate_employee_taxes=Decimal("1431.40"),
                aggregate_employee_deductions=Decimal("315.00"),
                aggregate_net_pay=Decimal("6673.60"),
                aggregate_employer_contributions=Decimal("644.13"),
                assembled_by_user_id=actor_id,
                assembled_at=now - timedelta(days=5),
                lifecycle="approved",
                review_state="accepted",
            )
        )

    @staticmethod
    def _scenario_specs(
        environment: DemoEnvironment,
        generation: int,
        jobs: list[Job],
        customers: list[UUID],
    ) -> list[
        tuple[str, str, list[dict[str, object]], dict[str, object], dict[str, object]]
    ]:
        def steps(*values: str) -> list[dict[str, object]]:
            return [{"order": i, "action": value} for i, value in enumerate(values, 1)]

        return [
            (
                "new_service_call",
                "New Service Call",
                steps(
                    "Create Customer", "Create Job", "Dispatch", "Complete", "Invoice"
                ),
                {"kind": "job_status", "expected": "draft"},
                {"job_id": str(jobs[11].id)},
            ),
            (
                "emergency_drain",
                "Emergency Drain",
                steps("Open urgent job", "Reassign technician", "Complete"),
                {"kind": "priority", "expected": "emergency"},
                {"job_id": str(jobs[1].id)},
            ),
            (
                "water_heater_estimate",
                "Water Heater Estimate",
                steps(
                    "Open customer",
                    "Build estimate",
                    "Approve",
                    "Convert",
                    "Review cost",
                ),
                {"kind": "estimate", "expected": "approved"},
                {
                    "customer_id": str(customers[6]),
                    "estimate_id": str(_id(environment.id, generation, "estimate", 1)),
                },
            ),
            (
                "dispatch_conflict",
                "Dispatch Conflict",
                steps("Open Dispatch", "Review overlap", "Move appointment"),
                {"kind": "overlapping_appointments", "expected": 2},
                {"job_ids": [str(jobs[0].id), str(jobs[1].id)]},
            ),
            (
                "overdue_ar",
                "Overdue AR",
                steps("Open Beacon", "Open overdue invoice", "Ask LIA"),
                {"kind": "overdue_invoice", "expected": 1},
                {
                    "customer_id": str(customers[3]),
                    "invoice_id": str(_id(environment.id, generation, "invoice", 1)),
                },
            ),
            (
                "margin_problem",
                "Margin Problem",
                steps("Open Luminary", "Review margin erosion", "Drill into job"),
                {"kind": "job_margin", "expected": "negative"},
                {"job_id": str(jobs[4].id)},
            ),
            (
                "inventory_shortage",
                "Inventory Shortage",
                steps("Open attention", "Review required material", "Open inventory"),
                {"kind": "inventory_below_requirement", "expected": True},
                {"job_id": str(jobs[6].id)},
            ),
            (
                "owner_morning_review",
                "Owner Morning Review",
                steps(
                    "Open Command Center",
                    "Review business pulse",
                    "Open attention",
                    "Ask LIA",
                ),
                {"kind": "business_pulse", "expected": "attention"},
                {},
            ),
        ]

    async def counts(self, session: AsyncSession, company_id: UUID) -> dict[str, int]:
        from sqlalchemy import func

        async def count(model, predicate):
            return int(
                await session.scalar(
                    select(func.count()).select_from(model).where(predicate)
                )
                or 0
            )

        location_count = int(
            await session.scalar(
                select(func.count())
                .select_from(ServiceLocation)
                .join(Customer, Customer.id == ServiceLocation.customer_id)
                .where(Customer.company_id == company_id)
            )
            or 0
        )
        return {
            "customers": await count(Customer, Customer.company_id == company_id),
            "locations": location_count,
            "employees": await count(Employee, Employee.company_id == company_id),
            "jobs": await count(Job, Job.company_id == company_id),
            "estimates": await count(Estimate, Estimate.company_id == company_id),
            "invoices": await count(Invoice, Invoice.company_id == company_id),
            "price_book_items": await count(
                PriceBookServiceItem, PriceBookServiceItem.company_id == company_id
            ),
            "inventory_items": await count(
                InventoryItem, InventoryItem.company_id == company_id
            ),
            "accounting_periods": await count(
                AccountingPeriod, AccountingPeriod.company_id == company_id
            ),
        }

    async def feedback(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        category: str,
        page: str,
        scenario_code: str | None,
        comment: str,
        app_sha: str,
    ) -> DemoFeedback:
        environment = await session.scalar(
            select(DemoEnvironment).where(
                DemoEnvironment.active_company_id == context.company.id,
                DemoEnvironment.status == "ready",
            )
        )
        if environment is None:
            raise OnboardingConflictError(
                "Feedback is limited to the caller's active Demo Company."
            )
        item = DemoFeedback(
            environment_id=environment.id,
            company_id=context.company.id,
            user_id=context.user.id,
            category=category,
            page=page,
            scenario_code=scenario_code,
            comment=comment.strip(),
            app_sha=app_sha,
        )
        if not item.comment:
            raise ValueError("Feedback comment is required.")
        session.add(item)
        await session.flush()
        return item


sales_demo_service = SalesDemoService()
