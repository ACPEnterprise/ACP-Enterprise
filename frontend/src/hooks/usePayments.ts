import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "../api/payments";
import { shouldRetryApiQuery } from "../api/errors";

export const paymentKeys = { all: ["payments"] as const, list: (customerId?: string) => ["payments", "list", customerId ?? "all"] as const, detail: (id: string) => ["payments", id] as const, moneyPosition: (periodStart: string, periodEnd: string, asOf: string, branchId?: string) => ["payments", "money-position", periodStart, periodEnd, asOf, branchId ?? "all"] as const };
export const usePayments = (enabled = true, customerId?: string) => useQuery({ queryKey: paymentKeys.list(customerId), queryFn: () => api.listPaymentReceipts(customerId), enabled, retry: shouldRetryApiQuery });
export const usePayment = (id: string, enabled = true) => useQuery({ queryKey: paymentKeys.detail(id), queryFn: () => api.getPaymentReceipt(id), enabled: enabled && Boolean(id), retry: shouldRetryApiQuery });
export const useMoneyPosition = (periodStart: string, periodEnd: string, asOf: string, branchId?: string, enabled = true) => useQuery({ queryKey: paymentKeys.moneyPosition(periodStart, periodEnd, asOf, branchId), queryFn: () => api.getMoneyPosition(periodStart, periodEnd, asOf, branchId), enabled, retry: shouldRetryApiQuery });
export function usePaymentMutations() {
  const client = useQueryClient();
  const refresh = () => {
    void client.invalidateQueries({ queryKey: paymentKeys.all });
    // Applying or refunding a receipt changes Invoice allocation and the
    // Customer AR projection. Keep those connected office views truthful too.
    void client.invalidateQueries({ queryKey: ["invoices"] });
  };
  return {
    collect: useMutation({ mutationFn: api.collectPayment, onSuccess: refresh }),
    apply: useMutation({ mutationFn: ({ id, input }: { id: string; input: Parameters<typeof api.applyPayment>[1] }) => api.applyPayment(id, input), onSuccess: refresh }),
    refund: useMutation({ mutationFn: ({ id, input }: { id: string; input: Parameters<typeof api.refundPayment>[1] }) => api.refundPayment(id, input), onSuccess: refresh }),
  };
}
