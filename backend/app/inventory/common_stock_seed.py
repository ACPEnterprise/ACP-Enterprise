from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from numbers_parser import Document  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.inventory.models import InventoryItem, MaterialCatalogAdmission
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.permissions.authorization import AuthorizationContext
from app.purchasing.models import (
    OperationalVendor,
    VendorItemCrossReference,
    VendorPurchaseCostEvidence,
)

REQUIRED_COLUMNS = ("description", "part_number", "cost", "unit_of_measure")


@dataclass(frozen=True, slots=True)
class CommonStockRow:
    source_row_number: int
    description: str
    vendor_sku: str
    purchase_cost: Decimal
    unit: str
    row_digest: str
    source_payload: dict[str, object]
    disposition: str = "admitted"
    hold_reason: str | None = None

    @property
    def acp_sku(self) -> str:
        identity = f"{normalize(self.description)}|{normalize(self.unit)}"
        return f"ACP-MAT-{hashlib.sha256(identity.encode()).hexdigest()[:12].upper()}"


@dataclass(frozen=True, slots=True)
class CommonStockWorkbook:
    source_path: Path
    source_digest: str
    columns: tuple[str, ...]
    rows: tuple[CommonStockRow, ...]

    @property
    def proposed_count(self) -> int:
        return sum(row.disposition == "admitted" for row in self.rows)

    @property
    def held_count(self) -> int:
        return sum(row.disposition == "held" for row in self.rows)


@dataclass(frozen=True, slots=True)
class PlanningCostCandidate:
    amount: Decimal | None
    currency: str
    policy: str = "highest_current_qualified_vendor_purchase_cost"
    authority_state: str = "owner_approval_required"


def planning_cost_candidate(costs: tuple[Decimal, ...]) -> PlanningCostCandidate:
    return PlanningCostCandidate(amount=max(costs) if costs else None, currency="USD")


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).upper()


def _text(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip() if value is not None else ""


def read_common_stock_workbook(path: Path) -> CommonStockWorkbook:
    payload = path.read_bytes()
    source_digest = hashlib.sha256(payload).hexdigest()
    document = Document(str(path))
    tables = [table for sheet in document.sheets for table in sheet.tables]
    if len(tables) != 1:
        raise ValueError("common_stock_source_requires_one_table")
    values = tables[0].rows(values_only=True)
    if not values:
        raise ValueError("common_stock_source_empty")
    columns = tuple(_text(value) for value in values[0])
    missing = set(REQUIRED_COLUMNS) - set(columns)
    if missing:
        raise ValueError("common_stock_source_columns_missing")
    index = {name: offset for offset, name in enumerate(columns)}
    seen_vendor_skus: set[str] = set()
    rows: list[CommonStockRow] = []
    for row_number, values_row in enumerate(values[1:], start=2):
        description = _text(values_row[index["description"]])
        vendor_sku = _text(values_row[index["part_number"]])
        unit = _text(values_row[index["unit_of_measure"]])
        try:
            cost = Decimal(str(values_row[index["cost"]]))
        except Exception as error:
            raise ValueError(f"common_stock_cost_invalid:{row_number}") from error
        source_payload: dict[str, object] = {
            column: _text(values_row[offset])
            for offset, column in enumerate(columns)
            if values_row[offset] is not None
        }
        canonical = {
            "description": description,
            "vendor_sku": vendor_sku,
            "purchase_cost": str(cost),
            "unit": unit,
        }
        row_digest = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        reason = None
        if not description or not vendor_sku or not unit or cost < 0:
            reason = "required_material_evidence_invalid"
        elif normalize(vendor_sku) in seen_vendor_skus:
            reason = "duplicate_vendor_sku_in_source"
        else:
            seen_vendor_skus.add(normalize(vendor_sku))
        rows.append(
            CommonStockRow(
                source_row_number=row_number,
                description=description,
                vendor_sku=vendor_sku,
                purchase_cost=cost,
                unit=unit,
                row_digest=row_digest,
                source_payload=source_payload,
                disposition="held" if reason else "admitted",
                hold_reason=reason,
            )
        )
    return CommonStockWorkbook(path, source_digest, columns, tuple(rows))


class CommonStockAdmissionService:
    async def admit_authorized(
        self,
        session: AsyncSession,
        *,
        workbook: CommonStockWorkbook,
        context: AuthorizationContext,
        reason: str,
    ) -> tuple[int, int]:
        async with session.begin():
            admitted, held = await self.admit(
                session,
                workbook=workbook,
                company_id=context.company.id,
                actor_user_id=context.user.id,
            )
            audit_service.stage(
                session,
                AuditEntry(
                    action="inventory.common_stock_seed.admit",
                    resource_type="inventory_material_catalog_admission",
                    actor_user_id=context.user.id,
                    company_id=context.company.id,
                    reason_code="owner_common_stock_seed",
                    details={
                        "source_digest": workbook.source_digest,
                        "source_rows": len(workbook.rows),
                        "records_admitted": admitted,
                        "records_held": held,
                        "reason": reason,
                    },
                ),
            )
            BusinessEventService.stage(
                session,
                BusinessEventCreate(
                    event_type=EventType.INVENTORY_COMMON_STOCK_SEED_ADMITTED,
                    entity_type="inventory_material_catalog",
                    company_id=context.company.id,
                    user_id=context.user.id,
                    payload={
                        "source_digest": workbook.source_digest,
                        "source_rows": len(workbook.rows),
                        "records_admitted": admitted,
                        "records_held": held,
                        "opening_inventory_state": "not_historically_reconstructed",
                    },
                ),
            )
        return admitted, held

    async def admit(
        self,
        session: AsyncSession,
        *,
        workbook: CommonStockWorkbook,
        company_id: UUID,
        actor_user_id: UUID,
        vendor_code: str = "HUGHES_SUPPLY",
        vendor_name: str = "Hughes Supply",
    ) -> tuple[int, int]:
        existing_rows = set(
            await session.scalars(
                select(MaterialCatalogAdmission.source_row_number).where(
                    MaterialCatalogAdmission.company_id == company_id,
                    MaterialCatalogAdmission.source_digest == workbook.source_digest,
                )
            )
        )
        vendor = await session.scalar(
            select(OperationalVendor).where(
                OperationalVendor.company_id == company_id,
                OperationalVendor.code == vendor_code,
            )
        )
        if vendor is None:
            vendor = OperationalVendor(
                company_id=company_id,
                code=vendor_code,
                display_name=vendor_name,
                status="active",
                provenance_type="owner_seed",
                provenance_reference=workbook.source_digest,
                created_by_user_id=actor_user_id,
            )
            session.add(vendor)
            await session.flush()
        admitted = held = 0
        observed_at = datetime.now(timezone.utc)
        for row in workbook.rows:
            if row.source_row_number in existing_rows:
                continue
            item: InventoryItem | None = None
            disposition, reason = row.disposition, row.hold_reason
            if disposition == "admitted":
                item = await session.scalar(
                    select(InventoryItem).where(
                        InventoryItem.company_id == company_id,
                        InventoryItem.code == row.acp_sku,
                    )
                )
                if item is None:
                    item = InventoryItem(
                        company_id=company_id,
                        code=row.acp_sku,
                        name=row.description,
                        stocking_unit=row.unit,
                        allow_fractional=False,
                        status="active",
                        created_by_user_id=actor_user_id,
                        updated_by_user_id=actor_user_id,
                    )
                    session.add(item)
                    await session.flush()
                elif normalize(item.name) != normalize(row.description):
                    disposition, reason, item = (
                        "held",
                        "acp_sku_identity_conflict",
                        None,
                    )
            admission = MaterialCatalogAdmission(
                company_id=company_id,
                inventory_item_id=item.id if item else None,
                source_filename=workbook.source_path.name,
                source_digest=workbook.source_digest,
                source_row_number=row.source_row_number,
                row_digest=row.row_digest,
                source_payload=row.source_payload,
                disposition=disposition,
                hold_reason=reason,
                opening_inventory_state="not_historically_reconstructed",
                admitted_by_user_id=actor_user_id,
            )
            session.add(admission)
            if item is None:
                held += 1
                continue
            xref = await session.scalar(
                select(VendorItemCrossReference).where(
                    VendorItemCrossReference.company_id == company_id,
                    VendorItemCrossReference.vendor_id == vendor.id,
                    VendorItemCrossReference.vendor_sku == row.vendor_sku,
                )
            )
            if xref is not None and xref.inventory_item_id != item.id:
                admission.inventory_item_id = None
                admission.disposition = "held"
                admission.hold_reason = "vendor_sku_mapping_conflict"
                held += 1
                continue
            if xref is None:
                xref = VendorItemCrossReference(
                    company_id=company_id,
                    vendor_id=vendor.id,
                    inventory_item_id=item.id,
                    vendor_sku=row.vendor_sku,
                    match_state="certified",
                    certified_by_user_id=actor_user_id,
                    certified_at=observed_at,
                )
                session.add(xref)
                await session.flush()
            evidence_digest = hashlib.sha256(
                f"{workbook.source_digest}|{row.source_row_number}|{row.vendor_sku}|{row.purchase_cost}".encode()
            ).hexdigest()
            session.add(
                VendorPurchaseCostEvidence(
                    company_id=company_id,
                    vendor_item_cross_reference_id=xref.id,
                    purchase_cost=row.purchase_cost,
                    currency="USD",
                    observed_at=observed_at,
                    source_digest=workbook.source_digest,
                    source_row_number=row.source_row_number,
                    evidence_digest=evidence_digest,
                    recorded_by_user_id=actor_user_id,
                )
            )
            admitted += 1
        return admitted, held


common_stock_admission_service = CommonStockAdmissionService()
