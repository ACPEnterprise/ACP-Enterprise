import type {
  CustomerContact,
  CustomerDetail,
  CustomerListResponse,
  CustomerProperty,
  CustomerSummary,
} from "../types/customers";

type JsonRecord = Record<string, unknown>;

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" ? value as JsonRecord : {};
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function customerSummary(value: unknown): CustomerSummary {
  const item = record(value);
  const displayName = text(item.display_name) ?? "Customer";
  const type = item.customer_type === "commercial" ? "business" : "individual";
  return {
    id: String(item.id ?? ""),
    display_name: displayName,
    customer_type: type,
    first_name: text(item.first_name),
    last_name: text(item.last_name),
    business_name: text(item.business_name) ?? text(item.legal_name),
    primary_phone: text(item.primary_phone) ?? "",
    secondary_phone: text(item.secondary_phone),
    email: text(item.email),
    preferred_contact_method: item.preferred_contact_method === "sms" || item.preferred_contact_method === "email" ? item.preferred_contact_method : "phone",
    status: item.status === "inactive" ? "inactive" : "active",
    source: text(item.source) ?? text(item.marketing_source),
    internal_notes: text(item.internal_notes) ?? text(item.notes),
    created_at: String(item.created_at ?? ""),
    updated_at: String(item.updated_at ?? ""),
    archived_at: text(item.archived_at),
  };
}

function contact(value: unknown): CustomerContact {
  const item = record(value);
  return {
    id: String(item.id ?? ""), customer_id: String(item.customer_id ?? ""),
    first_name: text(item.first_name) ?? "Contact", last_name: text(item.last_name),
    relationship_or_role: text(item.relationship_or_role) ?? text(item.title),
    phone: text(item.phone) ?? text(item.mobile_phone) ?? text(item.office_phone),
    email: text(item.email), is_preferred: item.is_preferred === true,
    can_approve_work: item.can_approve_work === true,
    created_at: String(item.created_at ?? ""), updated_at: String(item.updated_at ?? ""),
    archived_at: text(item.archived_at),
  };
}

function property(value: unknown): CustomerProperty {
  const item = record(value);
  return {
    id: String(item.id ?? ""), customer_id: String(item.customer_id ?? ""),
    address_line_1: text(item.address_line_1) ?? text(item.address) ?? "",
    address_line_2: text(item.address_line_2), city: text(item.city) ?? "",
    state: text(item.state) ?? "", postal_code: text(item.postal_code) ?? "",
    property_type: text(item.property_type) as CustomerProperty["property_type"],
    gate_access_instructions: text(item.gate_access_instructions) ?? text(item.gate_code),
    water_shutoff_location: text(item.water_shutoff_location),
    sewer_septic: text(item.sewer_septic) as CustomerProperty["sewer_septic"],
    property_notes: text(item.property_notes), is_primary: item.is_primary === true,
    created_at: String(item.created_at ?? ""), updated_at: String(item.updated_at ?? ""),
    archived_at: text(item.archived_at),
  };
}

export function normalizeCustomerList(value: unknown): CustomerListResponse {
  const payload = record(value);
  const items = Array.isArray(payload.items) ? payload.items.map(customerSummary) : [];
  return { items, total: Number(payload.total ?? items.length), limit: Number(payload.limit ?? items.length), offset: Number(payload.offset ?? 0) };
}

export function normalizeCustomerDetail(value: unknown): CustomerDetail {
  const payload = record(value);
  const contacts = Array.isArray(payload.contacts) ? payload.contacts.map(contact) : [];
  const locations = Array.isArray(payload.properties) ? payload.properties : Array.isArray(payload.locations) ? payload.locations : [];
  return { ...customerSummary(payload), contacts, properties: locations.map(property), notes: [] };
}
