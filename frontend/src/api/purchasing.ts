import { apiClient } from "./client";
import type {
  OperationalVendor,
  PurchaseOrder,
  PurchaseOrderCreate,
  PurchaseOrderUpdate,
  PurchaseOrderLine,
  PurchaseOrderLineCreate,
  PurchaseOrderLineUpdate,
  PurchasingTransition,
  PurchasingWorkspace,
  VendorCreate,
  VendorUpdate,
  RecordPurchaseOrderReceipt,
  ResolvePurchaseOrderDiscrepancy,
  PurchaseOrderReceipt,
  PurchaseOrderDiscrepancy,
  PurchaseReturn,
  CreatePurchaseReturn,
  TransitionPurchaseReturn,
  PurchaseOrderChange,
  RequestPurchaseOrderChange,
  DecidePurchaseOrderChange,
  PurchaseOrderDisposition,
  PurchaseOrderDispositionCommand,
  ReplenishmentWorkbench,
  ReplenishmentWorkbenchRequest,
  ReplenishmentDecision,
  ReplenishmentDecisionCommand,
  BranchPurchasingPolicy,
  BranchPurchasingPolicyWrite,
} from "../types/purchasing";

const root = "/api/v1/purchasing";
export const getPurchasingWorkspace = async (
  search?: string,
): Promise<PurchasingWorkspace> =>
  (await apiClient.get<PurchasingWorkspace>(root, { params: { search } })).data;
export const getReplenishmentWorkbench = async (
  input: ReplenishmentWorkbenchRequest,
): Promise<ReplenishmentWorkbench> =>
  (await apiClient.post<ReplenishmentWorkbench>(`${root}/replenishment/workbench`, input)).data;
export const decideReplenishment = async (input: ReplenishmentDecisionCommand): Promise<ReplenishmentDecision> =>
  (await apiClient.post<ReplenishmentDecision>(`${root}/replenishment/decisions`, input)).data;
export const getBranchPurchasingPolicies = async (): Promise<readonly BranchPurchasingPolicy[]> =>
  (await apiClient.get<readonly BranchPurchasingPolicy[]>(`${root}/branch-policies`)).data;
export const configureBranchPurchasingPolicy = async (
  input: BranchPurchasingPolicyWrite,
): Promise<BranchPurchasingPolicy> =>
  (await apiClient.put<BranchPurchasingPolicy>(`${root}/branch-policies`, input)).data;
export const createOperationalVendor = async (
  input: VendorCreate,
): Promise<OperationalVendor> =>
  (await apiClient.post<OperationalVendor>(`${root}/vendors`, input)).data;
export const updateOperationalVendor = async (
  id: string,
  input: VendorUpdate,
): Promise<OperationalVendor> =>
  (await apiClient.put<OperationalVendor>(`${root}/vendors/${id}`, input)).data;
export const createPurchaseOrder = async (
  input: PurchaseOrderCreate,
): Promise<PurchaseOrder> =>
  (await apiClient.post<PurchaseOrder>(`${root}/purchase-orders`, input)).data;
export const updatePurchaseOrder = async (
  id: string,
  input: PurchaseOrderUpdate,
): Promise<PurchaseOrder> =>
  (await apiClient.put<PurchaseOrder>(`${root}/purchase-orders/${id}`, input))
    .data;
export const addPurchaseOrderLine = async (
  id: string,
  input: PurchaseOrderLineCreate,
): Promise<PurchaseOrderLine> =>
  (
    await apiClient.post<PurchaseOrderLine>(
      `${root}/purchase-orders/${id}/lines`,
      input,
    )
  ).data;
export const updatePurchaseOrderLine = async (
  id: string,
  lineId: string,
  input: PurchaseOrderLineUpdate,
): Promise<PurchaseOrderLine> =>
  (
    await apiClient.put<PurchaseOrderLine>(
      `${root}/purchase-orders/${id}/lines/${lineId}`,
      input,
    )
  ).data;
export const transitionPurchaseOrder = async (
  id: string,
  action: "submit" | "approve" | "issue" | "cancel" | "close",
  input: PurchasingTransition,
): Promise<PurchaseOrder> =>
  (
    await apiClient.post<PurchaseOrder>(
      `${root}/purchase-orders/${id}/${action}`,
      input,
    )
  ).data;
export const recordPurchaseOrderReceipt = async (
  id: string,
  input: RecordPurchaseOrderReceipt,
): Promise<PurchaseOrderReceipt> =>
  (
    await apiClient.post<PurchaseOrderReceipt>(
      `${root}/purchase-orders/${id}/receipts`,
      input,
    )
  ).data;
export const resolvePurchaseOrderDiscrepancy = async (
  id: string,
  discrepancyId: string,
  input: ResolvePurchaseOrderDiscrepancy,
): Promise<PurchaseOrderDiscrepancy> =>
  (
    await apiClient.post<PurchaseOrderDiscrepancy>(
      `${root}/purchase-orders/${id}/discrepancies/${discrepancyId}/resolve`,
      input,
    )
  ).data;
export const createPurchaseReturn = async (
  id: string,
  input: CreatePurchaseReturn,
): Promise<PurchaseReturn> =>
  (
    await apiClient.post<PurchaseReturn>(
      `${root}/purchase-orders/${id}/returns`,
      input,
    )
  ).data;
export const transitionPurchaseReturn = async (
  id: string,
  returnId: string,
  action:
    | "request-authorization"
    | "authorize"
    | "deny"
    | "ready"
    | "returned"
    | "vendor-received"
    | "close"
    | "cancel",
  input: TransitionPurchaseReturn,
): Promise<PurchaseReturn> =>
  (
    await apiClient.post<PurchaseReturn>(
      `${root}/purchase-orders/${id}/returns/${returnId}/${action}`,
      input,
    )
  ).data;
export const requestPurchaseOrderChange = async (
  id: string,
  input: RequestPurchaseOrderChange,
): Promise<PurchaseOrderChange> =>
  (
    await apiClient.post<PurchaseOrderChange>(
      `${root}/purchase-orders/${id}/changes`,
      input,
    )
  ).data;
export const decidePurchaseOrderChange = async (
  id: string,
  changeId: string,
  action: "approve" | "reject",
  input: DecidePurchaseOrderChange,
): Promise<PurchaseOrderChange> =>
  (
    await apiClient.post<PurchaseOrderChange>(
      `${root}/purchase-orders/${id}/changes/${changeId}/${action}`,
      input,
    )
  ).data;
export const dispositionPurchaseOrder = async (
  id: string,
  action: "complete" | "cancel",
  input: PurchaseOrderDispositionCommand,
): Promise<PurchaseOrderDisposition> =>
  (
    await apiClient.post<PurchaseOrderDisposition>(
      `${root}/purchase-orders/${id}/dispositions/${action}`,
      input,
    )
  ).data;
