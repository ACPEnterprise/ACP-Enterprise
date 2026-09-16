import { useQuery } from "@tanstack/react-query";

import { getHcpCustomerSourceHistory } from "../api/hcpSourceHistory";

export function useHcpCustomerSourceHistory(customerId: string, enabled = true) {
  return useQuery({
    queryKey: ["hcp-source-history", "customer", customerId],
    queryFn: () => getHcpCustomerSourceHistory(customerId),
    enabled,
    retry: false,
  });
}
