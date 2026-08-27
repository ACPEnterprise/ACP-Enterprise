export interface InventoryItem {
  id: string;
  company_id: string;
  code: string;
  name: string;
  stocking_unit: string;
  allow_fractional: boolean;
  status: string;
  version: number;
}
export interface InventoryLocation {
  id: string;
  company_id: string;
  branch_id: string;
  code: string;
  name: string;
  location_type: string;
  status: string;
  external_entity_type: string | null;
  external_entity_id: string | null;
  version: number;
}
export interface InventoryQuantity {
  item_id: string;
  location_id: string;
  company_id: string;
  branch_id: string;
  on_hand: string;
  reserved: string;
  available: string;
  version: number;
  updated_at: string;
}
export interface InventoryReservation {
  id: string;
  company_id: string;
  branch_id: string;
  item_id: string;
  location_id: string;
  quantity: string;
  allocated_quantity: string;
  issued_quantity: string;
  stocking_unit: string;
  demand_type: string;
  demand_id: string;
  status: string;
  expires_at: string | null;
  idempotency_key: string;
  version: number;
  created_at: string;
  updated_at: string;
}
export interface InventoryOverview {
  items: readonly InventoryItem[];
  locations: readonly InventoryLocation[];
  quantities: readonly InventoryQuantity[];
  reservations: readonly InventoryReservation[];
}
export interface InventoryTransfer {
  branch_id: string;
  item_id: string;
  source_location_id: string;
  destination_location_id: string;
  quantity: string;
  occurred_at: string;
  idempotency_key: string;
}
export interface InventoryLocationCreate {
  branch_id: string;
  code: string;
  name: string;
  location_type: string;
  external_entity_type?: string | null;
  external_entity_id?: string | null;
}
export interface InventoryReservationCreate {
  branch_id: string;
  item_id: string;
  location_id: string;
  quantity: string;
  demand_type: string;
  demand_id: string;
  idempotency_key: string;
  expires_at?: string | null;
}
export interface InventoryReservationAllocate {
  quantity?: string | null;
  allow_partial: boolean;
  expected_version: number;
  idempotency_key: string;
}
export interface InventoryAllocation {
  id: string;
  reservation_id: string;
  item_id: string;
  location_id: string;
  quantity: string;
  requested_quantity: string;
  partial_allowed: boolean;
  reservation_version: number;
  allocated_at: string;
}
