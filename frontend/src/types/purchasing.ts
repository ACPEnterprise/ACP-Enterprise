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
  cumulative_accepted_quantity: string;
  outstanding_quantity: string;
  is_cancelled: boolean;
}
export type PurchaseOrderChangeOperationName =
  | "set_quantity"
  | "set_unit_cost"
  | "cancel_line"
  | "add_line"
  | "set_expected_date";
export interface PurchaseOrderChangeOperation {
  operation: PurchaseOrderChangeOperationName;
  line_id?: string | null;
  inventory_item_id?: string | null;
  description?: string | null;
  quantity?: string | null;
  unit?: string | null;
  unit_cost?: string | null;
  expected_date?: string | null;
}
export interface PurchaseOrderChange {
  id: string;
  change_identity: string;
  base_revision: number;
  proposed_changes: readonly PurchaseOrderChangeOperation[];
  reason: string;
  status: "requested" | "approved" | "rejected";
  requested_by_user_id: string;
  requested_at: string;
  decided_by_user_id: string | null;
  decided_at: string | null;
  effective_revision: number | null;
  evidence_digest: string;
  downstream_reconciliation_required: boolean;
}
export interface PurchaseOrderRevision {
  id: string;
  revision_number: number;
  predecessor_revision: number | null;
  change_order_id: string | null;
  effective_snapshot: Record<string, unknown>;
  evidence_digest: string;
  effective_by_user_id: string;
  effective_at: string;
}
export interface PurchaseOrderReceiptLine {
  id: string;
  purchase_order_line_id: string;
  accepted_quantity: string;
  rejected_quantity: string;
  cumulative_accepted_quantity: string;
  outstanding_quantity: string;
  discrepancy_category: string | null;
}
export interface PurchaseOrderReceipt {
  id: string;
  receiving_event_identity: string;
  status: string;
  received_at: string;
  effective_date: string;
  lines: readonly PurchaseOrderReceiptLine[];
}
export interface PurchaseOrderDiscrepancy {
  id: string;
  purchase_order_line_id: string;
  category: string;
  status: string;
  observed_condition: string;
  version: number;
}
export interface PurchaseReturn {
  id: string;
  receipt_id: string;
  receipt_line_id: string;
  return_identity: string;
  item_identity_snapshot: string;
  accepted_quantity_snapshot: string;
  quantity: string;
  remaining_returnable_quantity: string;
  reason: string;
  reason_note: string | null;
  status: string;
  authorization_status: string;
  vendor_authorization_reference: string | null;
  vendor_instructions: string | null;
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
  effective_revision: number;
  lines: readonly PurchaseOrderLine[];
  issuance_digest: string | null;
  receiving_status: string;
  receipts: readonly PurchaseOrderReceipt[];
  discrepancies: readonly PurchaseOrderDiscrepancy[];
  returns: readonly PurchaseReturn[];
  change_orders: readonly PurchaseOrderChange[];
  revisions: readonly PurchaseOrderRevision[];
}
export interface RequestPurchaseOrderChange {
  expected_po_version: number;
  base_revision: number;
  change_identity: string;
  reason: string;
  changes: readonly PurchaseOrderChangeOperation[];
  idempotency_key: string;
}
export interface DecidePurchaseOrderChange {
  expected_po_version: number;
  expected_base_revision: number;
  reason?: string | null;
  idempotency_key: string;
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
export interface RecordPurchaseOrderReceipt {
  expected_po_version: number;
  receiving_event_identity: string;
  received_at: string;
  effective_date: string;
  source_reference?: string | null;
  idempotency_key: string;
  lines: readonly {
    purchase_order_line_id: string;
    accepted_quantity: string;
    rejected_quantity: string;
    discrepancy_category?: string | null;
    observed_condition?: string | null;
  }[];
}
export interface ResolvePurchaseOrderDiscrepancy {
  expected_po_version: number;
  expected_discrepancy_version: number;
  resolution: "resolved_accepted" | "resolved_rejected";
  note: string;
  idempotency_key: string;
}
export interface CreatePurchaseReturn {
  expected_po_version: number;
  return_identity: string;
  receipt_id: string;
  receipt_line_id: string;
  quantity: string;
  reason: string;
  reason_note?: string | null;
  authorization_required: boolean;
  effective_date: string;
  source_reference?: string | null;
  idempotency_key: string;
}
export interface TransitionPurchaseReturn {
  expected_po_version: number;
  expected_return_version: number;
  vendor_authorization_reference?: string | null;
  note?: string | null;
  occurred_at: string;
  idempotency_key: string;
}
