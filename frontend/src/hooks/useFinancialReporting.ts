import { useQuery } from "@tanstack/react-query";

import {
  getFinancialReport,
  type ReportRequest,
} from "../api/financialReporting";

export const useFinancialReport = (request: ReportRequest, enabled = true) =>
  useQuery({
    queryKey: ["financial-reporting", request],
    queryFn: () => getFinancialReport(request),
    enabled,
  });
