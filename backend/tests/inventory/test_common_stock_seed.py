from decimal import Decimal
from inspect import getsource
from pathlib import Path

import pytest
from app.inventory.common_stock_seed import (
    CommonStockAdmissionService,
    CommonStockRow,
    planning_cost_candidate,
)
from app.inventory.errors import InventoryValidation
from app.inventory.models import InventoryQuantity, MaterialCatalogAdmission
from app.inventory.router import (
    MAX_COMMON_STOCK_WORKBOOK_BYTES,
    _read_common_stock_upload,
    admit_common_stock_seed,
    preview_common_stock_seed,
)
from app.price_book.models import PriceBookComponent
from app.purchasing.models import VendorItemCrossReference, VendorPurchaseCostEvidence


def row(
    *, vendor_sku: str = "H-100", description: str = "1/2 IN COPPER ELBOW"
) -> CommonStockRow:
    return CommonStockRow(
        source_row_number=2,
        description=description,
        vendor_sku=vendor_sku,
        purchase_cost=Decimal("1.25000000"),
        unit="Each",
        row_digest="a" * 64,
        source_payload={"description": description},
    )


def test_acp_sku_is_deterministic_and_not_vendor_identity() -> None:
    first = row(vendor_sku="HUGHES-1")
    second = row(vendor_sku="FERGUSON-999")
    assert first.acp_sku == second.acp_sku
    assert first.acp_sku.startswith("ACP-MAT-")
    assert "HUGHES" not in first.acp_sku


def test_vendor_cross_reference_supports_many_vendors_per_material() -> None:
    constraints = {
        constraint.name for constraint in VendorItemCrossReference.__table__.constraints
    }
    assert "uq_vendor_item_xref_vendor_sku" in constraints
    assert "inventory_item_id" in VendorItemCrossReference.__table__.c
    assert "vendor_sku" not in MaterialCatalogAdmission.__table__.c


def test_vendor_cost_is_distinct_from_receipt_valuation_and_price_book() -> None:
    columns = VendorPurchaseCostEvidence.__table__.c
    assert columns.purchase_cost.type.scale == 8
    assert "cost_basis" in columns
    assert "selling_price" not in columns
    assert PriceBookComponent.__table__.name not in getsource(
        CommonStockAdmissionService
    )


def test_planning_cost_candidate_requires_owner_approval() -> None:
    result = planning_cost_candidate(
        (Decimal("4.10"), Decimal("5.25"), Decimal("4.90"))
    )
    assert result.amount == Decimal("5.25")
    assert result.policy == "highest_current_qualified_vendor_purchase_cost"
    assert result.authority_state == "owner_approval_required"


def test_seed_does_not_create_quantity_or_opening_movement() -> None:
    source = getsource(CommonStockAdmissionService)
    assert InventoryQuantity.__table__.name not in source
    assert "StockMovement" not in source
    assert "not_historically_reconstructed" in source


def test_migration_is_single_head_and_append_only() -> None:
    migration = Path(
        "alembic/versions/ti9k1m3o5q7s_common_stock_seed_catalog.py"
    ).read_text()
    assert 'down_revision: str | Sequence[str] | None = "sh8d0f2g4j6l8"' in migration
    assert "reject_material_seed_evidence_mutation" in migration


def test_normal_api_is_managed_two_step_and_atomic() -> None:
    preview_source = getsource(preview_common_stock_seed)
    admit_source = getsource(admit_common_stock_seed)
    service_source = getsource(CommonStockAdmissionService.admit_authorized)
    assert "context: ManageContext" in preview_source
    assert "context: ManageContext" in admit_source
    assert "expected_source_digest" in admit_source
    assert "session.begin()" in service_source
    assert "audit_service.stage" in service_source
    assert "BusinessEventService.stage" in service_source


def test_upload_boundary_rejects_unbounded_or_wrong_source() -> None:
    with pytest.raises(InventoryValidation):
        _read_common_stock_upload(b"not-numbers", "catalog.xlsx")
    with pytest.raises(InventoryValidation):
        _read_common_stock_upload(
            b"x" * (MAX_COMMON_STOCK_WORKBOOK_BYTES + 1), "catalog.numbers"
        )
