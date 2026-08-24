export interface PaymentIntent {
  id: string; branch_id: string; customer_id: string; invoice_id: string | null;
  amount: string; currency: string; status: string; version: number;
}
export interface PaymentReceipt {
  id: string; branch_id: string; customer_id: string; intent_id: string;
  currency: string; status: string; captured_amount: string; available_amount: string;
  applied_amount: string; refunded_amount: string; disputed_amount: string;
  version: number; captured_at: string;
}
export interface CollectPaymentInput {
  branch_id: string; customer_id: string; invoice_id?: string; amount: string;
  currency: string; opaque_payment_method: string; idempotency_key: string;
}
export interface ApplyPaymentInput {
  branch_id: string; invoice_id: string; amount: string; expected_invoice_version: number;
  idempotency_key: string; occurred_at: string;
}
export interface RefundPaymentInput {
  branch_id: string; amount: string; reason: string; expected_version: number; idempotency_key: string;
}
