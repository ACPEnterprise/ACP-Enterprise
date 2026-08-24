import { apiClient } from "./client";
import type { ApplyPaymentInput, CollectPaymentInput, PaymentIntent, PaymentReceipt, RefundPaymentInput } from "../types/payments";

const root = "/api/v1/payments";
export const listPaymentReceipts = async (): Promise<PaymentReceipt[]> => (await apiClient.get<PaymentReceipt[]>(`${root}/receipts`)).data;
export const getPaymentReceipt = async (id: string): Promise<PaymentReceipt> => (await apiClient.get<PaymentReceipt>(`${root}/receipts/${id}`)).data;
export const collectPayment = async (input: CollectPaymentInput): Promise<PaymentIntent> => (await apiClient.post<PaymentIntent>(`${root}/intents`, input)).data;
export const applyPayment = async (id: string, input: ApplyPaymentInput): Promise<PaymentReceipt> => (await apiClient.post<PaymentReceipt>(`${root}/receipts/${id}/applications`, input)).data;
export const refundPayment = async (id: string, input: RefundPaymentInput): Promise<void> => { await apiClient.post(`${root}/receipts/${id}/refunds`, input); };
