import { useQuery } from "@tanstack/react-query";

import { getAccountingPeriods } from "../api/accountingClose";

export const useAccountingPeriods = (enabled = true) =>
  useQuery({
    queryKey: ["accounting", "periods"],
    queryFn: getAccountingPeriods,
    enabled,
  });
