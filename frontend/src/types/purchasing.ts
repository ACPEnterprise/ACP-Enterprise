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
export interface PurchaseOrderDisposition {
  id: string;
  purchase_order_version: number;
  effective_revision: number;
  prior_status: string;
  disposition: "fully_satisfied" | "canceled_before_receipt" | "remainder_canceled";
  reason: string;
  quantity_evidence: readonly Record<string, unknown>[];
  evidence_digest: string;
  actor_user_id: string;
  occurred_at: string;
}
export interface PurchaseOrderReceiptLine {
  id: string;
  purchase_order_line_id: string;
  accepted_quantity: string;
  rejected_quantity: string;
  cumulative_accepted_quantity: string;
  outstanding_quantity: string;
  discrepancy_category: string | null;
  inventory_movement_id: string | null;
  unit_cost_snapshot: string | null;
  currency_snapshot: string | null;
}
export interface PurchaseOrderReceipt {
  id: string;
  receiving_event_identity: string;
  status: string;
  received_at: string;
  effective_date: string;
  receiving_location_id: string | null;
  inventory_application_state: "pending" | "applied" | "not_applicable";
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
  inventory_movement_id: string | null;
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
  disposition: PurchaseOrderDisposition | null;
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
export interface PurchaseOrderDispositionCommand {
  expected_po_version: number;
  expected_effective_revision: number;
  reason: string;
  confirm_terminal_action: boolean;
  idempotency_key: string;
}
export interface PurchasingWorkspace {
  vendors: readonly OperationalVendor[];
  purchase_orders: readonly PurchaseOrder[];
}
export interface ReplenishmentWorkbenchRequest {
  as_of: string;
  targets: readonly {
    branch_id: string;
    inventory_item_id: string;
    target_available_quantity: string;
  }[];
}
export interface ReplenishmentRecommendation {
  branch_id: string;
  inventory_item_id: string;
  item_code: string;
  item_name: string;
  stocking_unit: string;
  target_available_quantity: string;
  on_hand_quantity: string;
  reserved_quantity: string;
  available_quantity: string;
  open_purchase_order_quantity: string;
  recommended_order_quantity: string;
  recommendation_state: "recommend_order" | "no_action";
  provenance: readonly string[];
  evidence_digest: string;
}
export interface ReplenishmentWorkbench {
  schema_version: number;
  company_id: string;
  as_of: string;
  recommendations: readonly ReplenishmentRecommendation[];
  evidence_digest: string;
}
export interface ReplenishmentDecisionCommand {
  branch_id: string; inventory_item_id: string; recommendation_as_of: string;
  target_available_quantity: string; recommendation_digest: string;
  decision: "approved" | "rejected"; reason: string; approved_quantity?: string | null;
  vendor_id?: string | null; po_number?: string | null; currency?: string | null;
  unit_cost?: string | null; idempotency_key: string;
}
export interface ReplenishmentDecision {
  id: string; decision: "approved" | "rejected"; reason: string;
  purchase_order_id: string | null; approval_evidence_digest: string;
}
export interface BranchPurchasingPolicyRevision {
  version: number;
  target_available_quantity: string;
  status: "active" | "inactive";
  provenance_reference: string;
  reason: string;
  evidence_digest: string;
  actor_user_id: string;
  occurred_at: string;
}
export interface BranchPurchasingPolicy {
  id: string;
  company_id: string;
  branch_id: string;
  inventory_item_id: string;
  target_available_quantity: string;
  status: "active" | "inactive";
  provenance_reference: string;
  version: number;
  revisions: readonly BranchPurchasingPolicyRevision[];
}
export interface BranchPurchasingPolicyWrite {
  branch_id: string;
  inventory_item_id: string;
  target_available_quantity: string;
  status: "active" | "inactive";
  provenance_reference: string;
  reason: string;
  expected_version?: number | null;
  idempotency_key: string;
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
  receiving_location_id?: string | null;
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
