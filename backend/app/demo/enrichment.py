"""Idempotent enrichment for the preserved Sales Forward Demo tenant.

This module is deliberately narrower than Demo provisioning.  It never creates a
company, membership, or user and it refuses to run for a non-demo company.  The
records it creates are deterministic, synthetic, and source-labelled so a replay
can safely resume after an interrupted transaction.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.business_economics.models import EconomicsProfitabilityResultRecord
from app.customers.models import Customer, ServiceLocation
from app.demo.models import DemoEnvironment
from app.estimates.models import (
    Estimate as EstimateProposal,
    EstimateCommercialSnapshotReference,
    EstimateLifecycleHistory,
    EstimateLineItem as EstimateProposalLine,
    EstimateRevision,
)
from app.jobs.models import Job, JobAppointmentLink
from app.invoicing.models import Invoice
from app.platform.branch.models import Branch
from app.platform.company.models import Company
from app.platform.employees.models import Employee
from app.price_book.models import (
    PriceBookCategory,
    PriceBookCommercialSnapshot,
    PriceBookPriceVersion,
    PriceBookServiceItem,
    PriceBookTaxClassification,
)
from app.scheduling.models import Appointment
from app.dispatch.models import DispatchAssignment


DEMO_COMPANY_ID = UUID("c36895cf-8a6f-5c31-a2ed-474dee8d0fc4")
ENRICHMENT_VERSION = "twelvehats.sales-demo.v2"
PERIOD_START = date(2025, 12, 1)
PERIOD_END = date(2026, 11, 30)


def _id(company_id: UUID, kind: str, index: int = 0) -> UUID:
    return uuid5(NAMESPACE_URL, f"twelvehats.sales-demo.v2:{company_id}:{kind}:{index}")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class DemoEnrichmentResult:
    company_id: UUID
    version: str
    created: dict[str, int]
    existing: dict[str, int]


PRICE_ITEMS = (
    ("WH-ELECTRIC-50", "50-gallon Electric Water Heater", "Water Heaters", Decimal("1895.00"), Decimal("520.00"), Decimal("360.00")),
    ("WH-ELECTRIC-50-PREM", "50-gallon Electric Water Heater · Premium", "Water Heaters", Decimal("2595.00"), Decimal("760.00"), Decimal("460.00")),
    ("WH-ELECTRIC-50-PLUS", "50-gallon Electric Water Heater · Plus", "Water Heaters", Decimal("3295.00"), Decimal("1040.00"), Decimal("560.00")),
    ("WH-EXPANSION-TANK", "Thermal Expansion Tank", "Water Heaters", Decimal("425.00"), Decimal("96.00"), Decimal("84.00")),
    ("DRAIN-SNAKE-3IN", "3-inch Main Drain Clearing", "Drain & Sewer", Decimal("495.00"), Decimal("88.00"), Decimal("180.00")),
    ("SEWER-CAMERA-INSPECT", "Sewer Camera Inspection", "Drain & Sewer", Decimal("425.00"), Decimal("35.00"), Decimal("210.00")),
    ("HYDRO-JET-RES", "Residential Hydro Jetting", "Drain & Sewer", Decimal("895.00"), Decimal("180.00"), Decimal("310.00")),
    ("TOILET-ELITE", "High-efficiency Toilet Installation", "Fixtures", Decimal("895.00"), Decimal("285.00"), Decimal("220.00")),
    ("FAUCET-KITCHEN", "Kitchen Faucet Replacement", "Fixtures", Decimal("625.00"), Decimal("180.00"), Decimal("160.00")),
    ("EMERGENCY-RESPONSE", "Emergency Plumbing Response", "Emergency", Decimal("295.00"), Decimal("25.00"), Decimal("145.00")),
    ("LEAK-LOCATE", "Electronic Leak Detection", "Diagnostics", Decimal("375.00"), Decimal("30.00"), Decimal("190.00")),
    ("WATER-SHUTOFF", "Whole-home Water Shutoff Replacement", "Repairs", Decimal("685.00"), Decimal("145.00"), Decimal("210.00")),
)


class DemoEnrichmentService:
    async def enrich(
        self,
        session: AsyncSession,
        *,
        company_id: UUID = DEMO_COMPANY_ID,
        actor_id: UUID | None = None,
    ) -> DemoEnrichmentResult:
        if company_id != DEMO_COMPANY_ID:
            raise ValueError("Sales Demo enrichment is restricted to the approved Demo company.")
        company = await session.get(Company, company_id)
        if company is None or company.status != "active":
            raise ValueError("The approved Demo company is not active.")
        environment = await session.scalar(
            select(DemoEnvironment).where(
                DemoEnvironment.active_company_id == company_id,
                DemoEnvironment.status == "ready",
            )
        )
        if environment is None:
            raise ValueError("The approved Demo environment is not ready.")
        actor_id = actor_id or environment.owner_user_id
        branch = await session.scalar(
            select(Branch).where(Branch.company_id == company_id, Branch.is_primary.is_(True))
        )
        if branch is None:
            raise ValueError("The approved Demo branch is unavailable.")
        created: dict[str, int] = {}
        existing: dict[str, int] = {}

        def count(bucket: dict[str, int], key: str) -> None:
            bucket[key] = bucket.get(key, 0) + 1

        customers = list((await session.scalars(select(Customer).where(Customer.company_id == company_id).order_by(Customer.created_at, Customer.id))).all())
        locations = list(
            (
                await session.scalars(
                    select(ServiceLocation).where(
                        ServiceLocation.customer_id.in_([c.id for c in customers])
                    )
                )
            ).all()
        )
        locations_by_customer: dict[UUID, ServiceLocation] = {}
        for location in locations:
            locations_by_customer.setdefault(location.customer_id, location)
        employees = list(
            (
                await session.scalars(
                    select(Employee)
                    .where(Employee.company_id == company_id, Employee.status == "active")
                    .order_by(Employee.created_at, Employee.id)
                )
            ).all()
        )
        if not customers or not locations_by_customer or len(employees) < 2:
            raise ValueError("Demo enrichment requires the preserved base customers, locations, and employees.")

        categories: dict[str, PriceBookCategory] = {}
        for position, category_name in enumerate(sorted({row[2] for row in PRICE_ITEMS}), 2):
            code = f"DEMO-{category_name.upper().replace(' ', '-').replace('&', 'AND')}"
            category = await session.scalar(select(PriceBookCategory).where(PriceBookCategory.company_id == company_id, PriceBookCategory.code == code))
            if category is None:
                category = PriceBookCategory(id=_id(company_id, "category", position), company_id=company_id, code=code, name=category_name, description="Synthetic Sales Forward demonstration category.", position=position, status="active", created_by_user_id=actor_id)
                session.add(category)
                count(created, "categories")
            else:
                count(existing, "categories")
            categories[category_name] = category
        tax = await session.scalar(select(PriceBookTaxClassification).where(PriceBookTaxClassification.company_id == company_id, PriceBookTaxClassification.code == "DEMO-TAXABLE"))
        if tax is None:
            tax = PriceBookTaxClassification(id=_id(company_id, "tax"), company_id=company_id, code="DEMO-TAXABLE", name="Synthetic demo taxable", taxable=False, status="active", created_by_user_id=actor_id)
            session.add(tax)
        await session.flush()

        snapshots: list[PriceBookCommercialSnapshot] = []
        items_by_code: dict[str, PriceBookServiceItem] = {}
        for index, (code, name, category_name, price, material, labor) in enumerate(PRICE_ITEMS, 1):
            item = await session.scalar(select(PriceBookServiceItem).where(PriceBookServiceItem.company_id == company_id, PriceBookServiceItem.code == code))
            if item is None:
                item = PriceBookServiceItem(id=_id(company_id, "price-item", index), company_id=company_id, branch_id=None, category_id=categories[category_name].id, code=code, name=name, customer_description=f"Synthetic demo scope for {name.lower()}.", internal_description="DEMO — SYNTHETIC BUSINESS DATA; not All County pricing.", status="active", created_by_user_id=actor_id)
                session.add(item)
                count(created, "price_book_items")
                await session.flush()
                version = PriceBookPriceVersion(id=_id(company_id, "price-version", index), company_id=company_id, service_item_id=item.id, branch_id=None, tax_classification_id=tax.id, revision=1, currency="USD", unit_price=price, effective_at=datetime(2025, 12, 1, tzinfo=UTC), status="active", activation_reason="Synthetic Sales Forward demonstration", created_by_user_id=actor_id, activated_by_user_id=actor_id, activated_at=datetime(2025, 12, 1, tzinfo=UTC))
                session.add(version)
                await session.flush()
                item.current_version_id = version.id
            else:
                count(existing, "price_book_items")
            items_by_code[code] = item
            version = await session.scalar(select(PriceBookPriceVersion).where(PriceBookPriceVersion.company_id == company_id, PriceBookPriceVersion.service_item_id == item.id, PriceBookPriceVersion.status == "active").order_by(PriceBookPriceVersion.revision.desc()))
            if version is None:
                continue
            snapshot_key = f"sales-demo-v2:{company_id}:{code}"
            snapshot = await session.scalar(select(PriceBookCommercialSnapshot).where(PriceBookCommercialSnapshot.company_id == company_id, PriceBookCommercialSnapshot.idempotency_key == snapshot_key))
            if snapshot is None:
                data = {"classification": "synthetic_demo", "item_code": code, "description": item.customer_description, "material_cost": str(material), "labor_cost": str(labor), "equipment_cost": "75.00", "allocated_overhead": "120.00", "target_margin_percent": "45", "source": "sales_demo_price_book_v2"}
                snapshot = PriceBookCommercialSnapshot(id=_id(company_id, "snapshot", index), company_id=company_id, branch_id=branch.id, service_item_id=item.id, price_version_id=version.id, quantity=Decimal("1"), unit_price=version.unit_price, extended_amount=version.unit_price, currency="USD", effective_at=version.effective_at, snapshot_data=data, digest=_digest(data), idempotency_key=snapshot_key, created_by_user_id=actor_id)
                session.add(snapshot)
                count(created, "price_snapshots")
            else:
                count(existing, "price_snapshots")
            snapshots.append(snapshot)
        await session.flush()

        historical_jobs: list[Job] = []
        for index in range(1, 25):
            job = await session.get(Job, _id(company_id, "historical-job", index))
            customer = customers[(index - 1) % len(customers)]
            location = locations_by_customer[customer.id]
            completed = index % 5 != 0
            created_at = datetime(2025, 12, 10, tzinfo=UTC) + timedelta(days=index * 14)
            if job is None:
                job = Job(id=_id(company_id, "historical-job", index), company_id=company_id, branch_id=branch.id, job_number=f"JOB-{100000 + index:06d}", customer_id=customer.id, service_location_id=location.id, status="completed" if completed else ("in_progress" if index % 2 else "ready"), job_type_code=("water_heater_replacement" if index % 4 == 0 else "plumbing_service"), priority="high" if index % 7 == 0 else "normal", customer_reported_problem=("50-gallon electric water heater replacement" if index % 4 == 0 else "Synthetic residential plumbing service"), internal_description="DEMO — SYNTHETIC BUSINESS DATA", activated_at=created_at, started_at=created_at + timedelta(hours=1), completed_at=created_at + timedelta(hours=3) if completed else None, completed_by_user_id=actor_id if completed else None, created_at=created_at, created_by_user_id=actor_id, updated_at=created_at + timedelta(hours=3), updated_by_user_id=actor_id)
                session.add(job)
                count(created, "jobs")
            else:
                count(existing, "jobs")
            historical_jobs.append(job)
        await session.flush()

        for index, job in enumerate(historical_jobs, 1):
            appointment = await session.get(Appointment, _id(company_id, "historical-appointment", index))
            start = job.created_at + timedelta(hours=1)
            if appointment is None:
                appointment = Appointment(id=_id(company_id, "historical-appointment", index), company_id=company_id, branch_id=branch.id, appointment_number=f"APT-{100000 + index:06d}", customer_id=job.customer_id, service_location_id=job.service_location_id, status="completed" if job.status == "completed" else "scheduled", arrival_window_start_at=start, arrival_window_end_at=start + timedelta(hours=2), expected_duration_minutes=120, capacity_state="reserved", scheduling_timezone="America/New_York", created_by_user_id=actor_id, updated_by_user_id=actor_id, created_at=job.created_at, updated_at=job.updated_at)
                session.add(appointment)
                # The dispatch-assignment table has a composite FK to the
                # appointment row.  Flush the parent before adding its links so
                # SQLAlchemy cannot order a new assignment ahead of it.
                await session.flush()
                session.add(JobAppointmentLink(id=_id(company_id, "historical-job-appointment", index), company_id=company_id, branch_id=branch.id, job_id=job.id, appointment_id=appointment.id, visit_sequence=1, linked_by_user_id=actor_id))
                if index % 6 != 0:
                    session.add(DispatchAssignment(id=_id(company_id, "historical-dispatch", index), company_id=company_id, branch_id=branch.id, appointment_id=appointment.id, job_id=job.id, primary_employee_id=employees[index % len(employees)].id, status="assigned", assignment_reason="Synthetic historical dispatch evidence", assigned_by_user_id=actor_id, window_start_at=start, window_end_at=start + timedelta(hours=2), effective_at=job.created_at))
                count(created, "appointments")

        await session.flush()
        for index, job in enumerate(historical_jobs, 1):
            if job.status != "completed":
                continue
            invoice = await session.scalar(select(Invoice).where(Invoice.company_id == company_id, Invoice.invoice_number == f"INV-{100000 + index:06d}"))
            if invoice is None:
                revenue = Decimal("1895.00") if job.job_type_code == "water_heater_replacement" else Decimal(str(325 + (index % 4) * 125))
                invoice = Invoice(id=_id(company_id, "historical-invoice", index), company_id=company_id, branch_id=branch.id, customer_id=job.customer_id, service_location_id=job.service_location_id, job_id=job.id, invoice_number=f"INV-{100000 + index:06d}", identity_origin="native", status="paid" if index % 3 else "partially_paid", currency="USD", subtotal_amount=revenue, tax_amount=Decimal("0"), total_amount=revenue, accounting_status="posted", issue_date=job.completed_at.date(), due_date=job.completed_at.date() + timedelta(days=30), terms="Synthetic Demo Net 30", discount_amount=Decimal("0"), open_amount=Decimal("0") if index % 3 else revenue / 2, calculation_digest=_digest({"invoice": index, "revenue": str(revenue), "synthetic_demo": True}), legacy_evidence_missing=False, issued_at=job.completed_at, due_on=job.completed_at.date() + timedelta(days=30), created_by_user_id=actor_id, created_at=job.created_at, updated_by_user_id=actor_id, updated_at=job.updated_at)
                session.add(invoice)
                count(created, "invoices")
        await session.flush()

        for index, job in enumerate(historical_jobs, 1):
            if job.status != "completed":
                continue
            identity = f"sales-demo-v2:profitability:{job.id}"
            record = await session.scalar(select(EconomicsProfitabilityResultRecord).where(EconomicsProfitabilityResultRecord.company_id == company_id, EconomicsProfitabilityResultRecord.result_identity == identity))
            if record is not None:
                count(existing, "economics")
                continue
            revenue = 189500 if job.job_type_code == "water_heater_replacement" else 32500 + (index % 4) * 12500
            labor = 36000 + (index % 3) * 8000
            materials = 52000 if job.job_type_code == "water_heater_replacement" else 8500 + (index % 3) * 3500
            equipment = 7500 if index % 5 == 0 else 0
            truck = 2500
            overhead = 12000
            gross_profit = revenue - labor - materials - equipment - truck
            net_profit = gross_profit - overhead
            components = {name: {"state": "available", "amount_minor": amount, "currency": "USD", "confidence_percent": 100, "explanation": "Synthetic Demo evidence", "evidence": [{"owner": "TwelveHats Demo Services", "source_system": "sales_demo", "record_type": "synthetic_job_cost", "record_id": str(job.id), "source_version": ENRICHMENT_VERSION, "content_digest": _digest([str(job.id), name, amount])}], "allocation_digests": []} for name, amount in (("revenue", revenue), ("labor", labor), ("materials", materials), ("equipment", equipment), ("truck", truck), ("overhead", overhead), ("gross_profit", gross_profit), ("net_profit", net_profit))}
            package = {"company_id": str(company_id), "job_id": str(job.id), "source": "sales_demo", "version": ENRICHMENT_VERSION}
            package_digest = _digest(package)
            result_digest = _digest({"identity": identity, "components": components})
            record = EconomicsProfitabilityResultRecord(id=_id(company_id, "economics", index), company_id=company_id, branch_id=branch.id, subject_id=job.id, subject_kind="job", scope="job", basis="actual", period_start=PERIOD_START, period_end=PERIOD_END, currency="USD", admission_id=f"sales-demo-v2:{job.id}", admission_digest=_digest({"admission": str(job.id)}), package_id=f"sales-demo-package:{job.id}", package_digest=package_digest, computation_digest=_digest(components), result_identity=identity, result_digest=result_digest, metrics={"contribution_margin_minor": gross_profit, "gross_margin_basis_points": gross_profit * 10000 // revenue, "net_margin_basis_points": net_profit * 10000 // revenue, "allocated_cost_minor": overhead, "fully_burdened_cost_minor": labor + materials + equipment + truck + overhead, "confidence_percent": 100, "completeness_percent": 100, "freshness_status": "current"}, components=components, quality={"confidence_percent": 100, "completeness_percent": 100, "freshness_status": "current", "fresh_as_of": datetime.now(UTC).isoformat(), "missing_categories": [], "explanation": "Synthetic evidence is complete for demonstration purposes."}, explanation={"answer": "Synthetic job-cost evidence for Sales Forward demonstration.", "findings": [], "limitations": ["Synthetic demonstration data; not All County history."], "lineage_digest": package_digest}, acquisition_digests=[package_digest], allocation_digests=[], explanation_ids=[f"sales-demo-explanation:{job.id}"], lifecycle="admitted", created_by_user_id=actor_id)
            session.add(record)
            count(created, "economics")

        await session.flush()
        await self._seed_estimate_proposals(session, company_id=company_id, branch=branch, actor_id=actor_id, customers=customers, locations_by_customer=locations_by_customer, snapshots=snapshots, jobs=historical_jobs, created=created, existing=existing)
        environment.seed_version = ENRICHMENT_VERSION
        await session.flush()
        return DemoEnrichmentResult(company_id=company_id, version=ENRICHMENT_VERSION, created=created, existing=existing)

    async def _seed_estimate_proposals(self, session: AsyncSession, *, company_id: UUID, branch: Branch, actor_id: UUID, customers: list[Customer], locations_by_customer: dict[UUID, ServiceLocation], snapshots: list[PriceBookCommercialSnapshot], jobs: list[Job], created: dict[str, int], existing: dict[str, int]) -> None:
        if not snapshots:
            return
        for index in range(1, 7):
            estimate_id = _id(company_id, "estimate-proposal", index)
            proposal = await session.get(EstimateProposal, estimate_id)
            if proposal is not None:
                existing["estimates"] = existing.get("estimates", 0) + 1
                continue
            customer = customers[(index + 4) % len(customers)]
            location = locations_by_customer[customer.id]
            job = jobs[index - 1]
            snapshot = snapshots[(index - 1) % len(snapshots)]
            now = datetime(2026, 1, 10, tzinfo=UTC) + timedelta(days=index * 35)
            proposal = EstimateProposal(id=estimate_id, company_id=company_id, branch_id=branch.id, customer_id=customer.id, service_location_id=location.id, estimate_number=f"EST-{100000 + index:06d}", status="approved" if index in {1, 3} else "draft", acceptance_status="approved" if index in {1, 3} else "not_requested", version=1, created_by_user_id=actor_id, updated_by_user_id=actor_id, created_at=now, updated_at=now)
            session.add(proposal)
            await session.flush()
            total = snapshot.extended_amount
            revision = EstimateRevision(id=_id(company_id, "estimate-revision", index), company_id=company_id, estimate_id=estimate_id, parent_revision_id=None, revision_number=1, status="issued" if index in {1, 3} else "draft", proposal_title="Synthetic water heater replacement proposal" if index == 1 else "Synthetic plumbing service proposal", customer_message="DEMO — SYNTHETIC BUSINESS DATA. No external communication will be sent.", terms="Synthetic Demo terms; presentation only.", currency="USD", subtotal_amount=total, discount_type=None, discount_value=None, discount_amount=Decimal("0"), taxable_basis=Decimal("0"), tax_amount=Decimal("0"), total_amount=total, calculation_evidence={"classification": "synthetic_demo", "source_snapshot_id": str(snapshot.id), "source_version": ENRICHMENT_VERSION}, issued_at=now if index in {1, 3} else None, expires_at=now + timedelta(days=30), created_by_user_id=actor_id, created_at=now)
            session.add(revision)
            await session.flush()
            proposal.current_revision_id = revision.id
            line = EstimateProposalLine(id=_id(company_id, "estimate-line", index), company_id=company_id, revision_id=revision.id, position=1, title=str(snapshot.snapshot_data.get("description", "Synthetic plumbing service")), description="Synthetic demo estimate line backed by an immutable Price Book snapshot.", quantity=snapshot.quantity, unit_price=snapshot.unit_price, line_total=total, discount_allocation=Decimal("0"), discounted_basis=total, tax_amount=Decimal("0"), taxable=False, currency="USD", created_at=now)
            session.add(line)
            session.add(EstimateCommercialSnapshotReference(id=_id(company_id, "estimate-snapshot-ref", index), company_id=company_id, revision_id=revision.id, line_item_id=line.id, snapshot_id=snapshot.id, snapshot_digest=snapshot.digest, created_at=now))
            session.add(EstimateLifecycleHistory(id=_id(company_id, "estimate-history", index), company_id=company_id, branch_id=branch.id, estimate_id=estimate_id, from_status=None, to_status=proposal.status, from_acceptance_status=None, to_acceptance_status=proposal.acceptance_status, reason="Synthetic Sales Forward seeded proposal", actor_user_id=actor_id, version=1, occurred_at=now))
            created["estimates"] = created.get("estimates", 0) + 1
            await session.flush()


demo_enrichment_service = DemoEnrichmentService()
