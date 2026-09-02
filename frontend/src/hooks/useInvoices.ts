import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "../api/invoices";

export const invoiceKeys = {
  all: ["invoices"] as const,
  detail: (id: string) => ["invoices", id] as const,
  workspace: (filters: import("../types/invoices").InvoiceWorkspaceFilters) => ["invoices", "workspace", filters] as const,
  customerBalance: (customerId: string, asOf: string) => ["invoices", "customer-balance", customerId, asOf] as const,
  officeDetail: (id: string, asOf: string) => ["invoices", "office-detail", id, asOf] as const,
};

export function useInvoices(enabled = true) {
  return useQuery({ queryKey: invoiceKeys.all, queryFn: api.listInvoices, enabled });
}

export function useInvoiceWorkspace(filters: import("../types/invoices").InvoiceWorkspaceFilters, enabled = true) {
  return useQuery({ queryKey: invoiceKeys.workspace(filters), queryFn: () => api.getInvoiceWorkspace(filters), enabled });
}

export function useCustomerBalance(customerId: string, asOf: string, enabled = true) {
  return useQuery({ queryKey: invoiceKeys.customerBalance(customerId, asOf), queryFn: () => api.getCustomerBalance(customerId, asOf), enabled: enabled && Boolean(customerId) });
}

export function useInvoiceOfficeDetail(id: string, asOf: string, enabled = true) {
  return useQuery({ queryKey: invoiceKeys.officeDetail(id, asOf), queryFn: () => api.getInvoiceOfficeDetail(id, asOf), enabled: enabled && Boolean(id) });
}

export function useInvoice(id: string, enabled = true) {
  return useQuery({
    queryKey: invoiceKeys.detail(id),
    queryFn: () => api.getInvoice(id),
    enabled: enabled && Boolean(id),
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
    credit: useMutation({
      mutationFn: ({ id, input }: { id: string; input: Parameters<typeof api.creditInvoice>[1] }) => api.creditInvoice(id, input),
      onSuccess: update,
    }),
    writeOff: useMutation({
      mutationFn: ({ id, input }: { id: string; input: Parameters<typeof api.writeOffInvoice>[1] }) => api.writeOffInvoice(id, input),
      onSuccess: update,
    }),
    void: useMutation({
      mutationFn: ({ id, input }: { id: string; input: Parameters<typeof api.voidInvoice>[1] }) => api.voidInvoice(id, input),
      onSuccess: update,
    }),
  };
}
