import { apiClient } from "./client";
import type { ApplyPaymentInput, CollectPaymentInput, MoneyPosition, PaymentIntent, PaymentReceipt, RefundPaymentInput } from "../types/payments";

const root = "/api/v1/payments";
export const listPaymentReceipts = async (customerId?: string): Promise<PaymentReceipt[]> => (await apiClient.get<PaymentReceipt[]>(`${root}/receipts`, { params: { customer_id: customerId } })).data;
export const getPaymentReceipt = async (id: string): Promise<PaymentReceipt> => (await apiClient.get<PaymentReceipt>(`${root}/receipts/${id}`)).data;
export const collectPayment = async (input: CollectPaymentInput): Promise<PaymentIntent> => (await apiClient.post<PaymentIntent>(`${root}/intents`, input)).data;
export const applyPayment = async (id: string, input: ApplyPaymentInput): Promise<PaymentReceipt> => (await apiClient.post<PaymentReceipt>(`${root}/receipts/${id}/applications`, input)).data;
export const refundPayment = async (id: string, input: RefundPaymentInput): Promise<void> => { await apiClient.post(`${root}/receipts/${id}/refunds`, input); };
export const getMoneyPosition = async (
  periodStart: string,
  periodEnd: string,
  asOf: string,
  branchId?: string,
): Promise<MoneyPosition> => (
  await apiClient.get<MoneyPosition>(`${root}/money-position`, {
    params: {
      period_start: periodStart,
      period_end: periodEnd,
      as_of: asOf,
      branch_id: branchId || undefined,
    },
  })
).data;
