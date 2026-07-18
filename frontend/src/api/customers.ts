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
  DuplicateCheckInput,
  DuplicateMatch,
} from "../types/customers";

export async function listCustomers(
  search: string,
  limit: number,
  offset: number,
): Promise<CustomerListResponse> {
  const response = await apiClient.get<CustomerListResponse>(
    "/api/v1/customers",
    { params: { search: search || undefined, limit, offset } },
  );
  return response.data;
}
export async function getCustomer(customerId: string): Promise<CustomerDetail> {
  const response = await apiClient.get<CustomerDetail>(
    `/api/v1/customers/${customerId}`,
  );
  return response.data;
}

export async function createCustomer(
  input: CustomerInput,
): Promise<CustomerCreateResponse> {
  const response = await apiClient.post<CustomerCreateResponse>(
    "/api/v1/customers",
    input,
  );
  return response.data;
}

export async function updateCustomer(
  customerId: string,
  input: Partial<CustomerInput>,
): Promise<CustomerDetail> {
  const response = await apiClient.patch<CustomerDetail>(
    `/api/v1/customers/${customerId}`,
    input,
  );
  return response.data;
}

export async function archiveCustomer(customerId: string): Promise<CustomerDetail> {
  const response = await apiClient.post<CustomerDetail>(
    `/api/v1/customers/${customerId}/archive`,
  );
  return response.data;
}

export async function checkCustomerDuplicates(
  input: DuplicateCheckInput,
): Promise<DuplicateMatch[]> {
  const response = await apiClient.post<{ matches: DuplicateMatch[] }>(
    "/api/v1/customers/duplicate-check",
    input,
  );
  return response.data.matches;
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
