import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "../api/payments";

export const paymentKeys = { all: ["payments"] as const, detail: (id: string) => ["payments", id] as const };
export const usePayments = (enabled = true) => useQuery({ queryKey: paymentKeys.all, queryFn: api.listPaymentReceipts, enabled });
export const usePayment = (id: string, enabled = true) => useQuery({ queryKey: paymentKeys.detail(id), queryFn: () => api.getPaymentReceipt(id), enabled: enabled && Boolean(id) });
export function usePaymentMutations() {
  const client = useQueryClient();
  const refresh = () => void client.invalidateQueries({ queryKey: paymentKeys.all });
  return {
    collect: useMutation({ mutationFn: api.collectPayment, onSuccess: refresh }),
    apply: useMutation({ mutationFn: ({ id, input }: { id: string; input: Parameters<typeof api.applyPayment>[1] }) => api.applyPayment(id, input), onSuccess: refresh }),
    refund: useMutation({ mutationFn: ({ id, input }: { id: string; input: Parameters<typeof api.refundPayment>[1] }) => api.refundPayment(id, input), onSuccess: refresh }),
  };
}
