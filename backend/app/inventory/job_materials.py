from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.estimates.models import (
    EstimateCommercialSnapshotReference,
    EstimateJobConversion,
)
from app.inventory.errors import InventoryNotFound
from app.inventory.models import (
    InventoryItem,
    InventoryQuantity,
    InventoryReservation,
    MaterialIssue,
)
from app.inventory.schemas import JobMaterialRequirementResponse, JobMaterialsResponse
from app.jobs.models import Job
from app.platform.permissions.authorization import AuthorizationContext
from app.price_book.models import PriceBookCommercialSnapshot


@dataclass(frozen=True)
class ExpectedMaterial:
    code: str | None
    label: str
    quantity: Decimal
    snapshot_ids: tuple[UUID, ...]
    snapshot_digests: tuple[str, ...]


def extract_expected_materials(
    snapshots: tuple[PriceBookCommercialSnapshot, ...],
    digest_by_id: dict[UUID, str],
) -> tuple[ExpectedMaterial, ...]:
    """Extract version-pinned material expectations without inventing item bindings."""
    entries: dict[str, ExpectedMaterial] = {}
    for snapshot in snapshots:
        components = snapshot.snapshot_data.get("components", [])
        if not isinstance(components, list):
            continue
        service_quantity = Decimal(
            str(snapshot.snapshot_data.get("quantity", snapshot.quantity))
        )
        for position, raw in enumerate(components):
            if not isinstance(raw, dict) or raw.get("type") != "material":
                continue
            code = str(raw["code"]).strip().upper() if raw.get("code") else None
            key = code or f"snapshot:{snapshot.id}:{position}"
            existing = entries.get(key)
            quantity = Decimal(str(raw.get("quantity", "0"))) * service_quantity
            entries[key] = ExpectedMaterial(
                code=code,
                label=str(raw.get("label") or "Material"),
                quantity=quantity + (existing.quantity if existing else Decimal(0)),
                snapshot_ids=(existing.snapshot_ids if existing else ())
                + (snapshot.id,),
                snapshot_digests=(existing.snapshot_digests if existing else ())
                + (digest_by_id[snapshot.id],),
            )
    return tuple(entries.values())


class JobMaterialsService:
    async def projection(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
    ) -> JobMaterialsResponse:
        job = await session.scalar(
            select(Job).where(Job.company_id == context.company.id, Job.id == job_id)
        )
        if job is None or not context.can_access_branch(job.branch_id):
            raise InventoryNotFound("Job materials were not found")
        conversion = await session.scalar(
            select(EstimateJobConversion).where(
                EstimateJobConversion.company_id == context.company.id,
                EstimateJobConversion.job_id == job.id,
            )
        )
        if conversion is None:
            return JobMaterialsResponse(
                job_id=job.id,
                branch_id=job.branch_id,
                requirements=(),
                readiness_state="SOURCE_REQUIRED",
                blockers=("APPROVED_ESTIMATE_LINEAGE_REQUIRED",),
            )
        refs = tuple(
            (
                await session.scalars(
                    select(EstimateCommercialSnapshotReference).where(
                        EstimateCommercialSnapshotReference.company_id
                        == context.company.id,
                        EstimateCommercialSnapshotReference.revision_id
                        == conversion.estimate_revision_id,
                    )
                )
            ).all()
        )
        snapshots = (
            tuple(
                (
                    await session.scalars(
                        select(PriceBookCommercialSnapshot).where(
                            PriceBookCommercialSnapshot.company_id
                            == context.company.id,
                            PriceBookCommercialSnapshot.id.in_(
                                [reference.snapshot_id for reference in refs]
                            ),
                        )
                    )
                ).all()
            )
            if refs
            else ()
        )
        expected = extract_expected_materials(
            snapshots,
            {reference.snapshot_id: reference.snapshot_digest for reference in refs},
        )
        codes = [entry.code for entry in expected if entry.code]
        items = (
            tuple(
                (
                    await session.scalars(
                        select(InventoryItem).where(
                            InventoryItem.company_id == context.company.id,
                            InventoryItem.code.in_(codes),
                        )
                    )
                ).all()
            )
            if codes
            else ()
        )
        item_by_code = {item.code: item for item in items}
        requirements: list[JobMaterialRequirementResponse] = []
        overall_blockers: set[str] = set()
        for entry in expected:
            item = item_by_code.get(entry.code) if entry.code else None
            blockers: tuple[str, ...]
            if item is None:
                blockers = ("INVENTORY_ITEM_BINDING_REQUIRED",)
                state = "SOURCE_REQUIRED"
                on_hand = reserved = available = consumed = None
            else:
                on_hand, available = (
                    await session.execute(
                        select(
                            func.coalesce(func.sum(InventoryQuantity.on_hand), 0),
                            func.coalesce(
                                func.sum(
                                    InventoryQuantity.on_hand
                                    - InventoryQuantity.reserved
                                ),
                                0,
                            ),
                        ).where(
                            InventoryQuantity.company_id == context.company.id,
                            InventoryQuantity.branch_id == job.branch_id,
                            InventoryQuantity.item_id == item.id,
                        )
                    )
                ).one()
                reserved = await session.scalar(
                    select(
                        func.coalesce(
                            func.sum(InventoryReservation.allocated_quantity), 0
                        )
                    ).where(
                        InventoryReservation.company_id == context.company.id,
                        InventoryReservation.branch_id == job.branch_id,
                        InventoryReservation.item_id == item.id,
                        InventoryReservation.demand_type == "job",
                        InventoryReservation.demand_id == job.id,
                        InventoryReservation.status.in_(
                            ("allocated", "partially_allocated")
                        ),
                    )
                )
                issued, reversed_quantity = (
                    await session.execute(
                        select(
                            func.coalesce(
                                func.sum(MaterialIssue.quantity).filter(
                                    MaterialIssue.issue_type == "issue"
                                ),
                                0,
                            ),
                            func.coalesce(
                                func.sum(MaterialIssue.quantity).filter(
                                    MaterialIssue.issue_type == "reversal"
                                ),
                                0,
                            ),
                        )
                        .join(
                            InventoryReservation,
                            InventoryReservation.id == MaterialIssue.reservation_id,
                        )
                        .where(
                            MaterialIssue.company_id == context.company.id,
                            InventoryReservation.demand_type == "job",
                            InventoryReservation.demand_id == job.id,
                            MaterialIssue.item_id == item.id,
                        )
                    )
                ).one()
                consumed = Decimal(issued) - Decimal(reversed_quantity)
                if Decimal(reserved or 0) >= entry.quantity:
                    state, blockers = "RESERVED", ()
                elif Decimal(available or 0) + Decimal(reserved or 0) >= entry.quantity:
                    state, blockers = "READY_TO_RESERVE", ("RESERVATION_REQUIRED",)
                else:
                    state, blockers = "SHORTAGE", ("INSUFFICIENT_AVAILABLE_STOCK",)
            overall_blockers.update(blockers)
            requirements.append(
                JobMaterialRequirementResponse(
                    component_code=entry.code,
                    label=entry.label,
                    requirement_type="required",
                    expected_quantity=entry.quantity,
                    inventory_item_id=item.id if item else None,
                    stocking_unit=item.stocking_unit if item else None,
                    on_hand_quantity=on_hand,
                    reserved_quantity=reserved,
                    available_quantity=available,
                    consumed_quantity=consumed,
                    readiness_state=state,
                    blockers=blockers,
                    source_snapshot_ids=entry.snapshot_ids,
                    source_snapshot_digests=entry.snapshot_digests,
                )
            )
        if not requirements:
            overall_blockers.add("EXPECTED_MATERIALS_NOT_DEFINED")
        return JobMaterialsResponse(
            job_id=job.id,
            branch_id=job.branch_id,
            requirements=tuple(requirements),
            readiness_state=(
                "READY" if requirements and not overall_blockers else "NEEDS_ATTENTION"
            ),
            blockers=tuple(sorted(overall_blockers)),
        )


job_materials_service = JobMaterialsService()
