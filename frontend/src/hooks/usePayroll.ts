import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getPayrollOperationsSummary,
  listComplianceSchemas,
  listPayrollOperatingRegisters,
  listPayrollReports,
  getPayrollPeriodOperations,
  getPayrollEmployeeReadiness, getPayrollEmployeeSetup, draftPayrollCompensation,
  approvePayrollCompensation, approvePayrollInput,
  type CompensationDraft,
  calculatePayrollRun, closePayrollRun,
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

export function usePayrollRunActions() {
  const client = useQueryClient();
  const refresh = () => { void client.invalidateQueries({ queryKey: ["payroll"] }); };
  return {
    calculate: useMutation({ mutationFn: ({ runId, idempotencyKey }: { runId: string; idempotencyKey: string }) => calculatePayrollRun(runId, idempotencyKey), onSuccess: refresh }),
    close: useMutation({ mutationFn: ({ runId, reason, idempotencyKey }: { runId: string; reason: string; idempotencyKey: string }) => closePayrollRun(runId, reason, idempotencyKey), onSuccess: refresh }),
  };
}

export function usePayrollEmployeeSetup(employeeId: string | null, payPeriodId: string | null, enabled = true) {
  const client = useQueryClient();
  const key = ["payroll", "employee-setup", employeeId];
  const readinessKey = ["payroll", "employee-readiness", employeeId, payPeriodId];
  const refresh = () => { void client.invalidateQueries({ queryKey: key }); void client.invalidateQueries({ queryKey: readinessKey }); void client.invalidateQueries({ queryKey: ["payroll"] }); };
  return {
    query: useQuery({ queryKey: key, queryFn: () => getPayrollEmployeeSetup(employeeId!), enabled: enabled && Boolean(employeeId) }),
    readiness: useQuery({ queryKey: readinessKey, queryFn: () => getPayrollEmployeeReadiness(employeeId!, payPeriodId!), enabled: enabled && Boolean(employeeId) && Boolean(payPeriodId) }),
    draftCompensation: useMutation({ mutationFn: (body: CompensationDraft) => draftPayrollCompensation(employeeId!, body), onSuccess: refresh }),
    approveCompensation: useMutation({ mutationFn: approvePayrollCompensation, onSuccess: refresh }),
    approveInput: useMutation({ mutationFn: approvePayrollInput, onSuccess: refresh }),
  };
}
