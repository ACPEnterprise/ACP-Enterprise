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
} from "../types/purchasing";

const root = "/api/v1/purchasing";
export const getPurchasingWorkspace = async (
  search?: string,
): Promise<PurchasingWorkspace> =>
  (await apiClient.get<PurchasingWorkspace>(root, { params: { search } })).data;
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
