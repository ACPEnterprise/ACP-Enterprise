export type CustomerType = "individual" | "business";
export type PreferredContactMethod = "phone" | "sms" | "email";
export type CustomerStatus = "active" | "inactive" | "do_not_service";
export type PropertyType =
  | "single_family"
  | "multi_family"
  | "commercial"
  | "condo"
  | "townhome"
  | "mobile_home"
  | "other";
export type SewerSeptic = "sewer" | "septic" | "unknown";

export interface CustomerInput {
  customer_type: CustomerType;
  first_name: string | null;
  last_name: string | null;
  business_name: string | null;
  primary_phone: string;
  secondary_phone: string | null;
  email: string | null;
  preferred_contact_method: PreferredContactMethod;
  status: CustomerStatus;
  source: string;
  is_vip: boolean;
  internal_notes: string | null;
}
export interface CustomerSummary extends CustomerInput {
  id: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface CustomerPropertyInput {
  address_line_1: string;
  address_line_2: string | null;
  city: string;
  state: string;
  postal_code: string;
  property_type: PropertyType;
  gate_access_instructions: string | null;
  water_shutoff_location: string | null;
  sewer_septic: SewerSeptic | null;
  property_notes: string | null;
  is_primary: boolean;
}

export interface CustomerProperty extends CustomerPropertyInput {
  id: string;
  customer_id: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface CustomerContactInput {
  first_name: string;
  last_name: string | null;
  relationship_or_role: string | null;
  phone: string | null;
  email: string | null;
  is_preferred: boolean;
  can_approve_work: boolean;
}

export interface CustomerContact extends CustomerContactInput {
  id: string;
  customer_id: string;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export interface CustomerNote {
  id: string;
  customer_id: string;
  author_user_id: string | null;
  body: string;
  created_at: string;
}

export interface CustomerDetail extends CustomerSummary {
  properties: CustomerProperty[];
  contacts: CustomerContact[];
  notes: CustomerNote[];
}

export interface DuplicateMatch extends CustomerSummary {
  reasons: string[];
}

export interface CustomerListResponse {
  items: CustomerSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface CustomerCreateResponse {
  customer: CustomerDetail;
  duplicate_warnings: DuplicateMatch[];
}

export interface DuplicateCheckInput {
  first_name?: string | null;
  last_name?: string | null;
  business_name?: string | null;
  phone?: string | null;
  email?: string | null;
  address_line_1?: string | null;
  address_line_2?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
}
