import { apiClient } from "./client";
import type { HcpCustomerSourceHistory, HcpHistoricalCustomerSearch } from "../types/hcpSourceHistory";

export async function getHcpCustomerSourceHistory(customerId: string) {
  return (
    await apiClient.get<HcpCustomerSourceHistory>(
      `/api/v1/migration/source-history/customers/${encodeURIComponent(customerId)}`,
    )
  ).data;
}

export async function searchHcpHistoricalCustomers(query: string) {
  return (
    await apiClient.get<HcpHistoricalCustomerSearch>(
      "/api/v1/migration/source-history/customers",
      { params: { query, limit: 20 } },
    )
  ).data;
}

export async function getHcpCustomerSourceHistoryBySource(sourceCustomerId: string) {
  return (
    await apiClient.get<HcpCustomerSourceHistory>(
      `/api/v1/migration/source-history/customers/by-source/${encodeURIComponent(sourceCustomerId)}`,
    )
  ).data;
}
