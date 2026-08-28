from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OperationalVendorReference:
    """Public reference AP may map without acquiring Purchasing ownership."""

    company_id: UUID
    operational_vendor_id: UUID
    operational_vendor_version: int
    stable_code: str


@dataclass(frozen=True, slots=True)
class PurchaseOrderReference:
    company_id: UUID
    branch_id: UUID
    purchase_order_id: UUID
    purchase_order_version: int
    issuance_digest: str | None
