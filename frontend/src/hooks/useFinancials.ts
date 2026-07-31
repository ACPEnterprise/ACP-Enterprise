import { useQuery } from "@tanstack/react-query";

import * as api from "../api/financials";
import { shouldRetryApiQuery } from "../api/errors";

export function useFinancials(
  kind: api.FinancialDocument,
  query: { searchText?: string; page: number; pageSize: number },
) {
  return useQuery({
    queryKey: ["financials", kind, query],
    queryFn: () => api.listFinancials(kind, query),
    retry: shouldRetryApiQuery,
  });
}

export function useFinancial(kind: api.FinancialDocument, id: string | undefined) {
  return useQuery({
    queryKey: ["financials", kind, id],
    queryFn: () => api.getFinancial(kind, id as string),
    enabled: Boolean(id),
    retry: shouldRetryApiQuery,
  });
}

export function usePayments(query: {
  searchText?: string;
  page: number;
  pageSize: number;
}) {
  return useQuery({
    queryKey: ["financials", "payments", query],
    queryFn: () => api.listPayments(query),
    retry: shouldRetryApiQuery,
  });
}

export function usePayment(id: string | undefined) {
  return useQuery({
    queryKey: ["financials", "payments", id],
    queryFn: () => api.getPayment(id as string),
    enabled: Boolean(id),
    retry: shouldRetryApiQuery,
  });
}
