import { apiClient } from "./client";
import type {
  FinancialDetail,
  PaginatedFinancials,
  PaginatedPayments,
  Payment,
} from "../types/financials";

const PATH = "/api/v1/financials";

export type FinancialDocument = "estimates" | "invoices";

export async function listFinancials(
  kind: FinancialDocument,
  query: { searchText?: string; page: number; pageSize: number },
): Promise<PaginatedFinancials> {
  return (
    await apiClient.get<PaginatedFinancials>(`${PATH}/${kind}`, {
      params: {
        search_text: query.searchText || undefined,
        page: query.page,
        page_size: query.pageSize,
      },
    })
  ).data;
}

export async function getFinancial(
  kind: FinancialDocument,
  id: string,
): Promise<FinancialDetail> {
  return (await apiClient.get<FinancialDetail>(`${PATH}/${kind}/${id}`)).data;
}

export async function listPayments(query: {
  searchText?: string;
  page: number;
  pageSize: number;
}): Promise<PaginatedPayments> {
  return (
    await apiClient.get<PaginatedPayments>(`${PATH}/payments`, {
      params: {
        search_text: query.searchText || undefined,
        page: query.page,
        page_size: query.pageSize,
      },
    })
  ).data;
}

export async function getPayment(id: string): Promise<Payment> {
  return (await apiClient.get<Payment>(`${PATH}/payments/${id}`)).data;
}
