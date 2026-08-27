import { useQuery } from "@tanstack/react-query";

import {
  getFinancialReport,
  type ReportRequest,
} from "../api/financialReporting";

export const useFinancialReport = (request: ReportRequest) =>
  useQuery({
    queryKey: ["financial-reporting", request],
    queryFn: () => getFinancialReport(request),
  });
