import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addPurchaseOrderLine,
  createOperationalVendor,
  createPurchaseOrder,
  getPurchasingWorkspace,
  transitionPurchaseOrder,
  updateOperationalVendor,
  updatePurchaseOrder,
  updatePurchaseOrderLine,
  recordPurchaseOrderReceipt,
  resolvePurchaseOrderDiscrepancy,
  createPurchaseReturn,
  transitionPurchaseReturn,
  requestPurchaseOrderChange,
  decidePurchaseOrderChange,
  dispositionPurchaseOrder,
  getReplenishmentWorkbench,
  decideReplenishment,
  getBranchPurchasingPolicies,
  configureBranchPurchasingPolicy,
  configureSupplyChainPolicy,
  createPurchaseRequisition,
  transitionPurchaseRequisition,
} from "../api/purchasing";
import type {
  PurchaseOrderLineCreate,
  PurchaseOrderLineUpdate,
  PurchaseOrderUpdate,
  PurchasingTransition,
  VendorUpdate,
  RecordPurchaseOrderReceipt,
  ResolvePurchaseOrderDiscrepancy,
  CreatePurchaseReturn,
  TransitionPurchaseReturn,
  RequestPurchaseOrderChange,
  DecidePurchaseOrderChange,
  PurchaseOrderDispositionCommand,
  BranchPurchasingPolicyWrite,
  PurchaseRequisitionCreate,
  PurchaseRequisitionTransition,
  SupplyChainPolicyWrite,
} from "../types/purchasing";

const keys = {
  all: ["purchasing"] as const,
  workspace: (search?: string) => ["purchasing", "workspace", search] as const,
  policies: ["purchasing", "branch-policies"] as const,
};
export const usePurchasing = (search?: string, enabled = true) =>
  useQuery({
    queryKey: keys.workspace(search),
    queryFn: () => getPurchasingWorkspace(search),
    enabled,
  });
export const useBranchPurchasingPolicies = (enabled = true) =>
  useQuery({
    queryKey: keys.policies,
    queryFn: getBranchPurchasingPolicies,
    enabled,
  });
export function usePurchasingMutations() {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: keys.all });
  return {
    replenishmentWorkbench: useMutation({ mutationFn: getReplenishmentWorkbench }),
    decideReplenishment: useMutation({ mutationFn: decideReplenishment, onSuccess: refresh }),
    configureBranchPolicy: useMutation({
      mutationFn: (input: BranchPurchasingPolicyWrite) =>
        configureBranchPurchasingPolicy(input),
      onSuccess: refresh,
    }),
    createRequisition: useMutation({
      mutationFn: (input: PurchaseRequisitionCreate) => createPurchaseRequisition(input),
      onSuccess: refresh,
    }),
    transitionRequisition: useMutation({
      mutationFn: ({ id, action, input }: { id: string; action: "submit" | "approve" | "reject" | "convert" | "cancel"; input: PurchaseRequisitionTransition }) =>
        transitionPurchaseRequisition(id, action, input),
      onSuccess: refresh,
      onError: refresh,
    }),
    configureSupplyChainPolicy: useMutation({
      mutationFn: (input: SupplyChainPolicyWrite) => configureSupplyChainPolicy(input),
      onSuccess: refresh,
    }),
    createVendor: useMutation({
      mutationFn: createOperationalVendor,
      onSuccess: refresh,
    }),
    updateVendor: useMutation({
      mutationFn: ({ id, input }: { id: string; input: VendorUpdate }) =>
        updateOperationalVendor(id, input),
      onSuccess: refresh,
    }),
    createOrder: useMutation({
      mutationFn: createPurchaseOrder,
      onSuccess: refresh,
    }),
    updateOrder: useMutation({
      mutationFn: ({ id, input }: { id: string; input: PurchaseOrderUpdate }) =>
        updatePurchaseOrder(id, input),
      onSuccess: refresh,
    }),
    addLine: useMutation({
      mutationFn: ({
        id,
        input,
      }: {
        id: string;
        input: PurchaseOrderLineCreate;
      }) => addPurchaseOrderLine(id, input),
      onSuccess: refresh,
    }),
    updateLine: useMutation({
      mutationFn: ({
        id,
        lineId,
        input,
      }: {
        id: string;
        lineId: string;
        input: PurchaseOrderLineUpdate;
      }) => updatePurchaseOrderLine(id, lineId, input),
      onSuccess: refresh,
    }),
    transition: useMutation({
      mutationFn: ({
        id,
        action,
        input,
      }: {
        id: string;
        action: "submit" | "approve" | "issue" | "cancel" | "close";
        input: PurchasingTransition;
      }) => transitionPurchaseOrder(id, action, input),
      onSuccess: refresh,
    }),
    recordReceipt: useMutation({
      mutationFn: ({
        id,
        input,
      }: {
        id: string;
        input: RecordPurchaseOrderReceipt;
      }) => recordPurchaseOrderReceipt(id, input),
      onSuccess: refresh,
    }),
    resolveDiscrepancy: useMutation({
      mutationFn: ({
        id,
        discrepancyId,
        input,
      }: {
        id: string;
        discrepancyId: string;
        input: ResolvePurchaseOrderDiscrepancy;
      }) => resolvePurchaseOrderDiscrepancy(id, discrepancyId, input),
      onSuccess: refresh,
    }),
    createReturn: useMutation({
      mutationFn: ({ id, input }: { id: string; input: CreatePurchaseReturn }) =>
        createPurchaseReturn(id, input),
      onSuccess: refresh,
    }),
    transitionReturn: useMutation({
      mutationFn: ({
        id,
        returnId,
        action,
        input,
      }: {
        id: string;
        returnId: string;
        action:
          | "request-authorization"
          | "authorize"
          | "deny"
          | "ready"
          | "returned"
          | "vendor-received"
          | "close"
          | "cancel";
        input: TransitionPurchaseReturn;
      }) => transitionPurchaseReturn(id, returnId, action, input),
      onSuccess: refresh,
    }),
    requestChange: useMutation({
      mutationFn: ({ id, input }: { id: string; input: RequestPurchaseOrderChange }) =>
        requestPurchaseOrderChange(id, input),
      onSuccess: refresh,
      onError: refresh,
    }),
    decideChange: useMutation({
      mutationFn: ({ id, changeId, action, input }: { id: string; changeId: string; action: "approve" | "reject"; input: DecidePurchaseOrderChange }) =>
        decidePurchaseOrderChange(id, changeId, action, input),
      onSuccess: refresh,
      onError: refresh,
    }),
    dispositionOrder: useMutation({
      mutationFn: ({ id, action, input }: { id: string; action: "complete" | "cancel"; input: PurchaseOrderDispositionCommand }) =>
        dispositionPurchaseOrder(id, action, input),
      onSuccess: refresh,
      onError: refresh,
    }),
  };
}
