import { useQuery } from "@tanstack/react-query";

import {
  getPayrollOperationsSummary,
  listComplianceSchemas,
  listPayrollReports,
} from "../api/payroll";

export const usePayrollOperationsSummary = () =>
  useQuery({ queryKey: ["payroll", "operations"], queryFn: getPayrollOperationsSummary });

export const usePayrollReports = () =>
  useQuery({ queryKey: ["payroll", "reporting"], queryFn: listPayrollReports });

export const useComplianceSchemas = () =>
  useQuery({ queryKey: ["payroll", "compliance-schemas"], queryFn: listComplianceSchemas });
