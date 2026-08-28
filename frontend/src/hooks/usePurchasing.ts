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
} from "../api/purchasing";
import type {
  PurchaseOrderLineCreate,
  PurchaseOrderLineUpdate,
  PurchaseOrderUpdate,
  PurchasingTransition,
  VendorUpdate,
} from "../types/purchasing";

const keys = {
  all: ["purchasing"] as const,
  workspace: (search?: string) => ["purchasing", "workspace", search] as const,
};
export const usePurchasing = (search?: string, enabled = true) =>
  useQuery({
    queryKey: keys.workspace(search),
    queryFn: () => getPurchasingWorkspace(search),
    enabled,
  });
export function usePurchasingMutations() {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: keys.all });
  return {
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
  };
}
