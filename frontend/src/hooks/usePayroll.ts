import { useQuery } from "@tanstack/react-query";

import {
  getPayrollOperationsSummary,
  listComplianceSchemas,
  listPayrollReports,
} from "../api/payroll";

export const usePayrollOperationsSummary = (enabled = true) =>
  useQuery({ queryKey: ["payroll", "operations"], queryFn: getPayrollOperationsSummary, enabled });

export const usePayrollReports = (enabled = true) =>
  useQuery({ queryKey: ["payroll", "reporting"], queryFn: listPayrollReports, enabled });

export const useComplianceSchemas = (enabled = true) =>
  useQuery({ queryKey: ["payroll", "compliance-schemas"], queryFn: listComplianceSchemas, enabled });
