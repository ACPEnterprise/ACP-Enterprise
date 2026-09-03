import { apiClient } from "./client";
import type {
  CreateInvoiceInput,
  Invoice,
  InvoiceMutationInput,
  InvoiceWorkspaceFilters,
  InvoiceWorkspaceItem,
  CustomerBalance,
} from "../types/invoices";

const root = "/api/v1/invoices";

export async function listInvoices(): Promise<Invoice[]> {
  return (await apiClient.get<Invoice[]>(root)).data;
}

export async function getInvoice(id: string): Promise<Invoice> {
  return (await apiClient.get<Invoice>(`${root}/${id}`)).data;
}

export async function getInvoiceWorkspace(filters: InvoiceWorkspaceFilters): Promise<InvoiceWorkspaceItem[]> {
  return (await apiClient.get<InvoiceWorkspaceItem[]>(`${root}/workspace`, { params: {
    as_of: filters.asOf,
    state: filters.state,
    query: filters.query || undefined,
    customer_id: filters.customerId || undefined,
    branch_id: filters.branchId || undefined,
    limit: filters.limit ?? 100,
    offset: filters.offset ?? 0,
  } })).data;
}

export async function getCustomerBalance(customerId: string, asOf: string): Promise<CustomerBalance> {
  return (await apiClient.get<CustomerBalance>(`${root}/customers/${customerId}/balance`, { params: { as_of: asOf } })).data;
}

export async function getInvoiceOfficeDetail(id: string, asOf: string): Promise<InvoiceWorkspaceItem> {
  return (await apiClient.get<InvoiceWorkspaceItem>(`${root}/${id}/office-detail`, { params: { as_of: asOf } })).data;
}

export async function createInvoice(
  input: CreateInvoiceInput,
): Promise<Invoice> {
  return (await apiClient.post<Invoice>(root, input)).data;
}

export async function issueInvoice(
  id: string,
  input: InvoiceMutationInput,
): Promise<Invoice> {
  return (await apiClient.post<Invoice>(`${root}/${id}/issue`, input)).data;
}

export interface InvoiceAmountMutationInput extends InvoiceMutationInput {
  amount: string;
  reason_code: string;
}

export async function creditInvoice(id: string, input: InvoiceAmountMutationInput): Promise<Invoice> {
  return (await apiClient.post<Invoice>(`${root}/${id}/credits`, input)).data;
}

export async function writeOffInvoice(id: string, input: InvoiceAmountMutationInput): Promise<Invoice> {
  return (await apiClient.post<Invoice>(`${root}/${id}/write-offs`, input)).data;
}

export async function voidInvoice(id: string, input: InvoiceMutationInput): Promise<Invoice> {
  return (await apiClient.post<Invoice>(`${root}/${id}/void`, input)).data;
}
