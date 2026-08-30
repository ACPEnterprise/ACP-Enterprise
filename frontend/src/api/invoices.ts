import { apiClient } from "./client";
import type {
  CreateInvoiceInput,
  Invoice,
  InvoiceMutationInput,
} from "../types/invoices";

const root = "/api/v1/invoices";

export async function listInvoices(): Promise<Invoice[]> {
  return (await apiClient.get<Invoice[]>(root)).data;
}

export async function getInvoice(id: string): Promise<Invoice> {
  return (await apiClient.get<Invoice>(`${root}/${id}`)).data;
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
