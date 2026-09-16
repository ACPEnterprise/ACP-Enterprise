import { apiClient } from "./client";
import type { HcpCustomerSourceHistory } from "../types/hcpSourceHistory";

export async function getHcpCustomerSourceHistory(customerId: string) {
  return (
    await apiClient.get<HcpCustomerSourceHistory>(
      `/api/v1/migration/source-history/customers/${encodeURIComponent(customerId)}`,
    )
  ).data;
}
