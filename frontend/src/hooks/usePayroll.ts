import { useQuery } from "@tanstack/react-query";

import {
  getPayrollOperationsSummary,
  listComplianceSchemas,
  listPayrollOperatingRegisters,
  listPayrollReports,
  getPayrollPeriodOperations,
} from "../api/payroll";

export const usePayrollOperationsSummary = (enabled = true) =>
  useQuery({ queryKey: ["payroll", "operations"], queryFn: getPayrollOperationsSummary, enabled });

export const usePayrollReports = (enabled = true) =>
  useQuery({ queryKey: ["payroll", "reporting"], queryFn: listPayrollReports, enabled });

export const useComplianceSchemas = (enabled = true) =>
  useQuery({ queryKey: ["payroll", "compliance-schemas"], queryFn: listComplianceSchemas, enabled });

export const usePayrollPeriodOperations = (payPeriodId: string | null, enabled = true) =>
  useQuery({
    queryKey: ["payroll", "period-operations", payPeriodId],
    queryFn: () => getPayrollPeriodOperations(payPeriodId!),
    enabled: enabled && Boolean(payPeriodId),
  });
export const usePayrollOperatingRegisters = (enabled = true) =>
  useQuery({ queryKey: ["payroll", "operating-registers"], queryFn: listPayrollOperatingRegisters, enabled });
