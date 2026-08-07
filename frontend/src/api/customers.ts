import { apiClient } from "./client";
import type {
  CustomerContact,
  CustomerContactInput,
  CustomerCreateResponse,
  CustomerDetail,
  CustomerInput,
  CustomerListResponse,
  CustomerNote,
  CustomerProperty,
  CustomerPropertyInput,
  CustomerSummary,
  DuplicateCheckInput,
  DuplicateMatch,
} from "../types/customers";
import { normalizeCustomerSource } from "../types/customers";

type CustomerSummaryResponse = Omit<CustomerSummary, "source"> & {
  source?: unknown;
};
type CustomerDetailResponse = Omit<CustomerDetail, "source"> & {
  source?: unknown;
};
type DuplicateMatchResponse = Omit<DuplicateMatch, "source"> & {
  source?: unknown;
};

function normalizeCustomerSummary(
  customer: CustomerSummaryResponse,
): CustomerSummary {
  return { ...customer, source: normalizeCustomerSource(customer.source) };
}

function normalizeCustomerDetail(
  customer: CustomerDetailResponse,
): CustomerDetail {
  return { ...customer, source: normalizeCustomerSource(customer.source) };
}

function normalizeDuplicateMatch(
  customer: DuplicateMatchResponse,
): DuplicateMatch {
  return { ...customer, source: normalizeCustomerSource(customer.source) };
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
    "/api/v1/customers",
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
    input,
  );
  return normalizeCustomerDetail(response.data);
}

export async function archiveCustomer(customerId: string): Promise<CustomerDetail> {
  const response = await apiClient.post<CustomerDetailResponse>(
    `/api/v1/customers/${customerId}/archive`,
  );
  return normalizeCustomerDetail(response.data);
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
  const response = await apiClient.post<CustomerProperty>(
    `/api/v1/customers/${customerId}/properties`,
    input,
  );
  return response.data;
}

export async function updateCustomerProperty(
  customerId: string,
  propertyId: string,
  input: Partial<CustomerPropertyInput>,
): Promise<CustomerProperty> {
  const response = await apiClient.patch<CustomerProperty>(
    `/api/v1/customers/${customerId}/properties/${propertyId}`,
    input,
  );
  return response.data;
}

export async function addCustomerContact(
  customerId: string,
  input: CustomerContactInput,
): Promise<CustomerContact> {
  const response = await apiClient.post<CustomerContact>(
    `/api/v1/customers/${customerId}/contacts`,
    input,
  );
  return response.data;
}

export async function updateCustomerContact(
  customerId: string,
  contactId: string,
  input: Partial<CustomerContactInput>,
): Promise<CustomerContact> {
  const response = await apiClient.patch<CustomerContact>(
    `/api/v1/customers/${customerId}/contacts/${contactId}`,
    input,
  );
  return response.data;
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
