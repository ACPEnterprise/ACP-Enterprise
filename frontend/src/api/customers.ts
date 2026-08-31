import { apiClient } from "./client";
import type {
  CustomerContact,
  CustomerContactInput,
  CustomerConsent,
  CustomerConsentInput,
  CustomerCreateResponse,
  CustomerDetail,
  CustomerInput,
  CustomerListResponse,
  CustomerNote,
  CustomerProperty,
  CustomerPropertyInput,
  CustomerSummary,
  CustomerTimelineResponse,
  DuplicateCheckInput,
  DuplicateMatch,
} from "../types/customers";
import { normalizeCustomerSource } from "../types/customers";

type CustomerResponseRecord = Record<string, unknown>;
type CustomerSummaryResponse = CustomerResponseRecord;
type CustomerDetailResponse = CustomerResponseRecord;
type DuplicateMatchResponse = CustomerResponseRecord;

function stringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function optionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function recordValue(value: unknown): CustomerResponseRecord | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as CustomerResponseRecord)
    : null;
}

function recordArray(value: unknown): CustomerResponseRecord[] {
  return Array.isArray(value)
    ? value.flatMap((item) => {
        const record = recordValue(item);
        return record ? [record] : [];
      })
    : [];
}

function preferredContact(
  customer: CustomerResponseRecord,
): CustomerResponseRecord | null {
  const explicit = recordValue(customer.preferred_contact);
  if (explicit) return explicit;
  const contacts = recordArray(customer.contacts);
  return (
    contacts.find((contact) => contact.is_preferred === true) ??
    contacts[0] ??
    null
  );
}

function customerDisplayName(customer: CustomerResponseRecord): string {
  const current = optionalString(customer.display_name);
  if (current) return current;
  const business = optionalString(customer.business_name);
  if (business) return business;
  return [optionalString(customer.first_name), optionalString(customer.last_name)]
    .filter(Boolean)
    .join(" ");
}

function normalizeContact(contact: CustomerResponseRecord): CustomerContact {
  return {
    id: stringValue(contact.id),
    customer_id: stringValue(contact.customer_id),
    first_name: stringValue(contact.first_name, "Unknown"),
    last_name: optionalString(contact.last_name),
    relationship_or_role: optionalString(
      contact.relationship_or_role ?? contact.title,
    ),
    phone: optionalString(
      contact.phone ?? contact.mobile_phone ?? contact.office_phone,
    ),
    email: optionalString(contact.email),
    is_preferred: contact.is_preferred === true,
    can_approve_work: contact.can_approve_work === true,
    created_at: stringValue(contact.created_at),
    updated_at: stringValue(contact.updated_at),
    archived_at: optionalString(contact.archived_at),
  };
}

function normalizeProperty(property: CustomerResponseRecord): CustomerProperty {
  const propertyType = normalizeCustomerSource(property.property_type);
  return {
    id: stringValue(property.id),
    customer_id: stringValue(property.customer_id),
    address_line_1: stringValue(property.address_line_1 ?? property.address),
    address_line_2: optionalString(property.address_line_2),
    city: stringValue(property.city),
    state: stringValue(property.state),
    postal_code: stringValue(property.postal_code),
    property_type: propertyType as CustomerProperty["property_type"],
    gate_access_instructions: optionalString(
      property.gate_access_instructions ?? property.gate_code,
    ),
    water_shutoff_location: optionalString(property.water_shutoff_location),
    sewer_septic:
      property.sewer_septic === "sewer" || property.sewer_septic === "septic"
        ? property.sewer_septic
        : "unknown",
    property_notes: optionalString(property.property_notes),
    is_primary: property.is_primary === true,
    created_at: stringValue(property.created_at),
    updated_at: stringValue(property.updated_at),
    archived_at: optionalString(property.archived_at),
  };
}

function normalizeCustomerSummary(
  customer: CustomerSummaryResponse,
): CustomerSummary {
  const contact = preferredContact(customer);
  const name = customerDisplayName(customer);
  return {
    id: stringValue(customer.id),
    customer_type: stringValue(
      customer.customer_type,
      "residential",
    ) as CustomerSummary["customer_type"],
    first_name: optionalString(customer.first_name),
    last_name: optionalString(customer.last_name),
    business_name: optionalString(customer.business_name) ?? (name || null),
    primary_phone: stringValue(
      customer.primary_phone ?? contact?.mobile_phone ?? contact?.office_phone,
    ),
    secondary_phone: optionalString(customer.secondary_phone),
    email: optionalString(customer.email ?? contact?.email),
    preferred_contact_method: stringValue(
      customer.preferred_contact_method,
      "phone",
    ) as CustomerSummary["preferred_contact_method"],
    status: stringValue(customer.status, "inactive") as CustomerSummary["status"],
    source: normalizeCustomerSource(customer.source ?? customer.marketing_source),
    is_vip: customer.is_vip === true,
    internal_notes: optionalString(customer.internal_notes ?? customer.notes),
    created_at: stringValue(customer.created_at),
    updated_at: stringValue(customer.updated_at),
    archived_at: optionalString(customer.archived_at),
  };
}

function normalizeCustomerDetail(
  customer: CustomerDetailResponse,
): CustomerDetail {
  const summary = normalizeCustomerSummary(customer);
  const locations = Array.isArray(customer.properties)
    ? recordArray(customer.properties)
    : recordArray(customer.locations);
  const notes = Array.isArray(customer.note_history)
    ? recordArray(customer.note_history)
    : Array.isArray(customer.notes)
      ? recordArray(customer.notes)
      : [];
  return {
    ...summary,
    properties: locations.map(normalizeProperty),
    contacts: recordArray(customer.contacts).map(normalizeContact),
    notes: notes.map((note) => ({
      id: stringValue(note.id),
      customer_id: stringValue(note.customer_id, summary.id),
      author_user_id: optionalString(note.author_user_id),
      body: stringValue(note.body),
      created_at: stringValue(note.created_at),
    })),
  };
}

function authoritativeCustomerType(value: CustomerInput["customer_type"]): string {
  if (value === "individual") return "residential";
  if (value === "business") return "commercial";
  return value;
}

function customerUpdatePayload(
  input: Partial<CustomerInput>,
): CustomerResponseRecord {
  const payload: CustomerResponseRecord = {};
  if (input.customer_type !== undefined) {
    payload.customer_type = authoritativeCustomerType(input.customer_type);
  }
  if (
    input.business_name !== undefined ||
    input.first_name !== undefined ||
    input.last_name !== undefined
  ) {
    const displayName =
      optionalString(input.business_name) ??
      [optionalString(input.first_name), optionalString(input.last_name)]
        .filter(Boolean)
        .join(" ");
    if (displayName) payload.display_name = displayName;
  }
  if (input.preferred_contact_method !== undefined) {
    payload.preferred_contact_method = input.preferred_contact_method;
  }
  if (input.source !== undefined) payload.marketing_source = normalizeCustomerSource(input.source);
  if (input.internal_notes !== undefined) payload.notes = input.internal_notes;
  if (input.first_name !== undefined) payload.first_name = input.first_name;
  if (input.last_name !== undefined) payload.last_name = input.last_name;
  if (input.business_name !== undefined) payload.business_name = input.business_name;
  if (input.primary_phone !== undefined) payload.primary_phone = input.primary_phone;
  if (input.secondary_phone !== undefined) payload.secondary_phone = input.secondary_phone;
  if (input.email !== undefined) payload.email = input.email;
  if (input.is_vip !== undefined) payload.is_vip = input.is_vip;
  if (
    input.status === "prospect" ||
    input.status === "active" ||
    input.status === "inactive"
  ) {
    payload.status = input.status;
  }
  return payload;
}

function normalizeDuplicateMatch(
  customer: DuplicateMatchResponse,
): DuplicateMatch {
  return {
    ...normalizeCustomerSummary(customer),
    reasons: Array.isArray(customer.reasons)
      ? customer.reasons.filter(
          (reason): reason is string => typeof reason === "string",
        )
      : [],
  };
}

export async function listCustomers(
  search: string,
  limit: number,
  offset: number,
): Promise<CustomerListResponse> {
  const response = await apiClient.get<
    Omit<CustomerListResponse, "items"> & { items: CustomerSummaryResponse[] }
  >(
    "/api/v1/customers",
    { params: { search: search || undefined, limit, offset } },
  );
  return {
    ...response.data,
    items: response.data.items.map(normalizeCustomerSummary),
  };
}
export async function getCustomer(customerId: string): Promise<CustomerDetail> {
  const response = await apiClient.get<CustomerDetailResponse>(
    `/api/v1/customers/${customerId}`,
  );
  return normalizeCustomerDetail(response.data);
}

export async function createCustomer(
  input: CustomerInput,
): Promise<CustomerCreateResponse> {
  const response = await apiClient.post<{
    customer: CustomerDetailResponse;
    duplicate_warnings: DuplicateMatchResponse[];
  }>(
    "/api/v1/customers/intake",
    input,
  );
  return {
    customer: normalizeCustomerDetail(response.data.customer),
    duplicate_warnings: response.data.duplicate_warnings.map(
      normalizeDuplicateMatch,
    ),
  };
}

export async function updateCustomer(
  customerId: string,
  input: Partial<CustomerInput>,
): Promise<CustomerDetail> {
  const response = await apiClient.patch<CustomerDetailResponse>(
    `/api/v1/customers/${customerId}`,
    customerUpdatePayload(input),
  );
  return normalizeCustomerDetail(response.data);
}

export async function archiveCustomer(customerId: string): Promise<void> {
  await apiClient.post(`/api/v1/customers/${customerId}/archive`);
}

export async function restoreCustomer(customerId: string): Promise<void> {
  await apiClient.post(`/api/v1/customers/${customerId}/restore`);
}

export async function getCustomerTimeline(
  customerId: string,
  page = 1,
  pageSize = 50,
): Promise<CustomerTimelineResponse> {
  const response = await apiClient.get<CustomerTimelineResponse>(
    `/api/v1/customers/${customerId}/timeline`,
    { params: { page, page_size: pageSize } },
  );
  return response.data;
}

export async function checkCustomerDuplicates(
  input: DuplicateCheckInput,
): Promise<DuplicateMatch[]> {
  const response = await apiClient.post<{ matches: DuplicateMatchResponse[] }>(
    "/api/v1/customers/duplicate-check",
    input,
  );
  return response.data.matches.map(normalizeDuplicateMatch);
}

export async function addCustomerProperty(
  customerId: string,
  input: CustomerPropertyInput,
): Promise<CustomerProperty> {
  const response = await apiClient.post<CustomerResponseRecord>(
    `/api/v1/customers/${customerId}/locations`,
    propertyPayload(input),
  );
  return normalizeProperty(response.data);
}

export async function updateCustomerProperty(
  customerId: string,
  propertyId: string,
  input: Partial<CustomerPropertyInput>,
): Promise<CustomerProperty> {
  const response = await apiClient.patch<CustomerResponseRecord>(
    `/api/v1/customers/${customerId}/locations/${propertyId}`,
    propertyPayload(input),
  );
  return normalizeProperty(response.data);
}

export async function addCustomerContact(
  customerId: string,
  input: CustomerContactInput,
): Promise<CustomerContact> {
  const response = await apiClient.post<CustomerResponseRecord>(
    `/api/v1/customers/${customerId}/contacts`,
    contactPayload(input),
  );
  return normalizeContact(response.data);
}

export async function updateCustomerContact(
  customerId: string,
  contactId: string,
  input: Partial<CustomerContactInput>,
): Promise<CustomerContact> {
  const response = await apiClient.patch<CustomerResponseRecord>(
    `/api/v1/customers/${customerId}/contacts/${contactId}`,
    contactPayload(input),
  );
  return normalizeContact(response.data);
}

export async function addCustomerNote(
  customerId: string,
  body: string,
): Promise<CustomerNote> {
  const response = await apiClient.post<CustomerNote>(
    `/api/v1/customers/${customerId}/notes`,
    { body },
  );
  return response.data;
}

function contactPayload(
  input: Partial<CustomerContactInput>,
): CustomerResponseRecord {
  const payload: CustomerResponseRecord = {};
  if (input.first_name !== undefined) payload.first_name = input.first_name;
  if (input.last_name !== undefined) payload.last_name = input.last_name ?? "Contact";
  if (input.relationship_or_role !== undefined) {
    payload.relationship_or_role = input.relationship_or_role;
  }
  if (input.phone !== undefined) payload.mobile_phone = input.phone;
  if (input.email !== undefined) payload.email = input.email;
  if (input.is_preferred !== undefined) payload.is_preferred = input.is_preferred;
  if (input.can_approve_work !== undefined) {
    payload.can_approve_work = input.can_approve_work;
  }
  return payload;
}

function propertyPayload(
  input: Partial<CustomerPropertyInput>,
): CustomerResponseRecord {
  const payload: CustomerResponseRecord = {};
  if (input.address_line_1 !== undefined) payload.address = input.address_line_1;
  if (input.address_line_2 !== undefined) payload.address_line_2 = input.address_line_2;
  if (input.city !== undefined) payload.city = input.city;
  if (input.state !== undefined) payload.state = input.state;
  if (input.postal_code !== undefined) payload.postal_code = input.postal_code;
  if (input.gate_access_instructions !== undefined) {
    payload.gate_access_instructions = input.gate_access_instructions;
  }
  if (input.property_notes !== undefined) payload.property_notes = input.property_notes;
  if (input.property_type !== undefined) payload.property_type = input.property_type;
  if (input.water_shutoff_location !== undefined) payload.water_shutoff_location = input.water_shutoff_location;
  if (input.sewer_septic !== undefined) payload.sewer_septic = input.sewer_septic;
  if (input.is_primary !== undefined) payload.is_primary = input.is_primary;
  return payload;
}

export async function listCustomerConsents(
  customerId: string,
): Promise<CustomerConsent[]> {
  const response = await apiClient.get<CustomerConsent[]>(
    `/api/v1/customers/${customerId}/consents`,
  );
  return response.data;
}

export async function recordCustomerConsent(
  customerId: string,
  input: CustomerConsentInput,
): Promise<CustomerConsent> {
  const response = await apiClient.post<CustomerConsent>(
    `/api/v1/customers/${customerId}/consents`,
    input,
  );
  return response.data;
}
