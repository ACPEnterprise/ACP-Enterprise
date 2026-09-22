import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "../api/invoices";

export const invoiceKeys = {
  all: ["invoices"] as const,
  detail: (id: string) => ["invoices", id] as const,
  workspace: (filters: import("../types/invoices").InvoiceWorkspaceFilters) =>
    ["invoices", "workspace", filters] as const,
  customerBalance: (customerId: string, asOf: string) =>
    ["invoices", "customer-balance", customerId, asOf] as const,
  officeDetail: (id: string, asOf: string) =>
    ["invoices", "office-detail", id, asOf] as const,
  manualPayments: (id: string) => ["invoices", id, "manual-payments"] as const,
  candidates: ["invoices", "candidates"] as const,
  receivablesSummary: (asOf: string, branchId?: string) =>
    ["invoices", "receivables-summary", asOf, branchId] as const,
};

export function useInvoices(enabled = true) {
  return useQuery({
    queryKey: invoiceKeys.all,
    queryFn: api.listInvoices,
    enabled,
  });
}

export function useInvoiceCandidates(enabled = true) {
  return useQuery({
    queryKey: invoiceKeys.candidates,
    queryFn: api.getInvoiceCandidates,
    enabled,
  });
}

export function useInvoiceWorkspace(
  filters: import("../types/invoices").InvoiceWorkspaceFilters,
  enabled = true,
) {
  return useQuery({
    queryKey: invoiceKeys.workspace(filters),
    queryFn: () => api.getInvoiceWorkspace(filters),
    enabled,
  });
}

export function useReceivablesSummary(
  asOf: string,
  branchId?: string,
  enabled = true,
) {
  return useQuery({
    queryKey: invoiceKeys.receivablesSummary(asOf, branchId),
    queryFn: () => api.getReceivablesSummary(asOf, branchId),
    enabled,
  });
}

export function useCustomerBalance(
  customerId: string,
  asOf: string,
  enabled = true,
) {
  return useQuery({
    queryKey: invoiceKeys.customerBalance(customerId, asOf),
    queryFn: () => api.getCustomerBalance(customerId, asOf),
    enabled: enabled && Boolean(customerId),
  });
}

export function useInvoiceOfficeDetail(
  id: string,
  asOf: string,
  enabled = true,
) {
  return useQuery({
    queryKey: invoiceKeys.officeDetail(id, asOf),
    queryFn: () => api.getInvoiceOfficeDetail(id, asOf),
    enabled: enabled && Boolean(id),
  });
}

export function useInvoice(id: string, enabled = true) {
  return useQuery({
    queryKey: invoiceKeys.detail(id),
    queryFn: () => api.getInvoice(id),
    enabled: enabled && Boolean(id),
  });
}

export function useManualPaymentHistory(id: string, enabled = true) {
  return useQuery({
    queryKey: invoiceKeys.manualPayments(id),
    queryFn: () => api.getManualPaymentHistory(id),
    enabled: enabled && Boolean(id),
  });
}

export function useInvoiceMutations() {
  const client = useQueryClient();
  const update = (invoice: Awaited<ReturnType<typeof api.getInvoice>>) => {
    client.setQueryData(invoiceKeys.detail(invoice.id), invoice);
    void client.invalidateQueries({ queryKey: invoiceKeys.all });
    void client.invalidateQueries({ queryKey: invoiceKeys.candidates });
    // Invoice mutations also change the office detail, Customer balance, and
    // AR workspace projections. Refresh those views so operators never see a
    // stale balance or status after issuing, crediting, voiding, or writing off.
    void client.invalidateQueries({
      queryKey: ["invoices", "office-detail", invoice.id],
    });
    void client.invalidateQueries({
      queryKey: ["invoices", "customer-balance", invoice.customer_id],
    });
    void client.invalidateQueries({ queryKey: ["invoices", "workspace"] });
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
      mutationFn: ({
        id,
        input,
      }: {
        id: string;
        input: Parameters<typeof api.creditInvoice>[1];
      }) => api.creditInvoice(id, input),
      onSuccess: update,
    }),
    writeOff: useMutation({
      mutationFn: ({
        id,
        input,
      }: {
        id: string;
        input: Parameters<typeof api.writeOffInvoice>[1];
      }) => api.writeOffInvoice(id, input),
      onSuccess: update,
    }),
    void: useMutation({
      mutationFn: ({
        id,
        input,
      }: {
        id: string;
        input: Parameters<typeof api.voidInvoice>[1];
      }) => api.voidInvoice(id, input),
      onSuccess: update,
    }),
    manualPayment: useMutation({
      mutationFn: ({
        id,
        input,
      }: {
        id: string;
        input: Parameters<typeof api.recordManualPayment>[1];
      }) => api.recordManualPayment(id, input),
      onSuccess: (result) => {
        update(result.invoice);
        void client.invalidateQueries({
          queryKey: invoiceKeys.manualPayments(result.invoice.id),
        });
        void client.invalidateQueries({
          queryKey: ["invoices", "customer-balance"],
        });
        void client.invalidateQueries({ queryKey: ["invoices", "workspace"] });
      },
    }),
  };
}
