export interface OperationalVendor {
  id: string;
  company_id: string;
  code: string;
  display_name: string;
  legal_name: string | null;
  contact_reference: string | null;
  status: string;
  version: number;
}
export interface PurchaseOrderLine {
  id: string;
  line_number: number;
  inventory_item_id: string | null;
  description: string;
  quantity: string;
  unit: string;
  unit_cost: string;
  extended_cost: string;
  version: number;
}
export interface PurchaseOrder {
  id: string;
  branch_id: string;
  vendor_id: string;
  po_number: string;
  status: string;
  currency: string;
  expected_date: string | null;
  version: number;
  lines: readonly PurchaseOrderLine[];
  issuance_digest: string | null;
}
export interface PurchasingWorkspace {
  vendors: readonly OperationalVendor[];
  purchase_orders: readonly PurchaseOrder[];
}
export interface VendorCreate {
  code: string;
  display_name: string;
  legal_name?: string | null;
  contact_reference?: string | null;
  idempotency_key: string;
}
export interface VendorUpdate {
  expected_version: number;
  display_name: string;
  legal_name?: string | null;
  contact_reference?: string | null;
  status: string;
  idempotency_key: string;
}
export interface PurchaseOrderCreate {
  branch_id: string;
  vendor_id: string;
  po_number: string;
  currency: string;
  expected_date?: string | null;
  idempotency_key: string;
}
export interface PurchaseOrderUpdate {
  expected_version: number;
  vendor_id: string;
  expected_date?: string | null;
  idempotency_key: string;
}
export interface PurchaseOrderLineCreate {
  expected_po_version: number;
  inventory_item_id?: string | null;
  description: string;
  quantity: string;
  unit: string;
  unit_cost: string;
  expected_date?: string | null;
  idempotency_key: string;
}
export interface PurchaseOrderLineUpdate extends PurchaseOrderLineCreate {
  expected_line_version: number;
}
export interface PurchasingTransition {
  expected_version: number;
  reason?: string | null;
  idempotency_key: string;
}
