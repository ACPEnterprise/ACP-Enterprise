import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "../api/invoices";

export const invoiceKeys = {
  all: ["invoices"] as const,
  detail: (id: string) => ["invoices", id] as const,
};

export function useInvoices(enabled = true) {
  return useQuery({ queryKey: invoiceKeys.all, queryFn: api.listInvoices, enabled });
}

export function useInvoice(id: string) {
  return useQuery({
    queryKey: invoiceKeys.detail(id),
    queryFn: () => api.getInvoice(id),
    enabled: Boolean(id),
  });
}

export function useInvoiceMutations() {
  const client = useQueryClient();
  const update = (invoice: Awaited<ReturnType<typeof api.getInvoice>>) => {
    client.setQueryData(invoiceKeys.detail(invoice.id), invoice);
    void client.invalidateQueries({ queryKey: invoiceKeys.all });
  };
  return {
    create: useMutation({ mutationFn: api.createInvoice, onSuccess: update }),
    issue: useMutation({
      mutationFn: ({
        id,
        input,
      }: {
        id: string;
        input: Parameters<typeof api.issueInvoice>[1];
      }) => api.issueInvoice(id, input),
      onSuccess: update,
    }),
  };
}
