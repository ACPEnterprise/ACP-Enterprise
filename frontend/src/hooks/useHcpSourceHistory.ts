import { useQuery } from "@tanstack/react-query";

import { getHcpCustomerSourceHistory, getHcpCustomerSourceHistoryBySource, searchHcpHistoricalCustomers } from "../api/hcpSourceHistory";

export function useHcpCustomerSourceHistory(customerId: string, enabled = true) {
  return useQuery({
    queryKey: ["hcp-source-history", "customer", customerId],
    queryFn: () => getHcpCustomerSourceHistory(customerId),
    enabled,
    retry: false,
  });
}

export function useHcpHistoricalCustomerSearch(query: string, offset = 0) {
  return useQuery({
    queryKey: ["hcp-source-history", "historical-customer-search", query, offset],
    queryFn: () => searchHcpHistoricalCustomers(query, offset),
    enabled: query.trim().length === 0 || query.trim().length >= 2,
    retry: false,
  });
}

export function useHcpCustomerSourceHistoryBySource(sourceCustomerId: string | null) {
  return useQuery({
    queryKey: ["hcp-source-history", "source-customer", sourceCustomerId],
    queryFn: () => getHcpCustomerSourceHistoryBySource(sourceCustomerId ?? ""),
    enabled: Boolean(sourceCustomerId),
    retry: false,
  });
}
