import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getPayrollOperationsSummary,
  listComplianceSchemas,
  listPayrollOperatingRegisters,
  listPayrollReports,
  getPayrollPeriodOperations,
  getPayrollEmployeeSetup, draftPayrollCompensation, draftPayrollInput,
  approvePayrollCompensation, approvePayrollInput,
  type CompensationDraft, type PayrollInputDraft,
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

export function usePayrollEmployeeSetup(employeeId: string | null, enabled = true) {
  const client = useQueryClient();
  const key = ["payroll", "employee-setup", employeeId];
  const refresh = () => { void client.invalidateQueries({ queryKey: key }); void client.invalidateQueries({ queryKey: ["payroll"] }); };
  return {
    query: useQuery({ queryKey: key, queryFn: () => getPayrollEmployeeSetup(employeeId!), enabled: enabled && Boolean(employeeId) }),
    draftCompensation: useMutation({ mutationFn: (body: CompensationDraft) => draftPayrollCompensation(employeeId!, body), onSuccess: refresh }),
    draftInput: useMutation({ mutationFn: (body: PayrollInputDraft) => draftPayrollInput(employeeId!, body), onSuccess: refresh }),
    approveCompensation: useMutation({ mutationFn: approvePayrollCompensation, onSuccess: refresh }),
    approveInput: useMutation({ mutationFn: approvePayrollInput, onSuccess: refresh }),
  };
}
