import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createAccountingJournal,
  createAccountingOperation,
  getAccountingAccounts,
  getAccountingDashboard,
  getAccountingJournals,
  getAccountingOperations,
  getAccountingPeriods,
  updateAccountingAccountStatus,
} from "../api/accountingOperations";

export const useAccountingDashboard = () =>
  useQuery({
    queryKey: ["accounting", "dashboard"],
    queryFn: getAccountingDashboard,
  });
export const useAccountingAccounts = () =>
  useQuery({
    queryKey: ["accounting", "accounts"],
    queryFn: getAccountingAccounts,
  });
export const useAccountingPeriods = () =>
  useQuery({
    queryKey: ["accounting", "periods"],
    queryFn: getAccountingPeriods,
  });
export const useAccountingJournals = () =>
  useQuery({
    queryKey: ["accounting", "journals"],
    queryFn: getAccountingJournals,
  });
export const useAccountingOperations = () =>
  useQuery({
    queryKey: ["accounting", "operations"],
    queryFn: getAccountingOperations,
  });
export function useAccountingMutations() {
  const client = useQueryClient(),
    refresh = () => client.invalidateQueries({ queryKey: ["accounting"] });
  return {
    createJournal: useMutation({
      mutationFn: createAccountingJournal,
      onSuccess: refresh,
    }),
    createOperation: useMutation({
      mutationFn: createAccountingOperation,
      onSuccess: refresh,
    }),
    status: useMutation({
      mutationFn: ({
        id,
        status,
      }: {
        id: string;
        status: "active" | "archived";
      }) => updateAccountingAccountStatus(id, status),
      onSuccess: refresh,
    }),
  };
}
