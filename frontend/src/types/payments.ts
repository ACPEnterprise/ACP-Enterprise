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

export type MoneyEvidenceState =
  | "AVAILABLE"
  | "MEASURED_ZERO"
  | "INCOMPLETE"
  | "CONFLICTING"
  | "UNAVAILABLE";

export interface MoneyAmount {
  amount: string | null;
  currency: string | null;
  evidence_state: MoneyEvidenceState;
  limitation: string | null;
}

export interface MoneyPosition {
  company_id: string;
  branch_id: string | null;
  period_start: string;
  period_end: string;
  as_of: string;
  generated_at: string;
  bank_balance: MoneyAmount & {
    connection_state: "NOT_CONNECTED" | "CONNECTED";
    provider_as_of: string | null;
    last_sync_at: string | null;
  };
  accounts_receivable_due_today: MoneyAmount & {
    invoice_count: number;
    drilldown_path: string;
  };
  cod_expected_today: MoneyAmount;
  expected_collections_today: MoneyAmount;
  card_processing: {
    transaction_count: number;
    amount_charged: MoneyAmount;
    refund_amount: MoneyAmount;
    chargeback_amount: MoneyAmount;
    fees_paid: MoneyAmount;
    effective_fee_rate: string | null;
    limitation: string;
  };
  collection_state: {
    collected: MoneyAmount;
    settled_gross: MoneyAmount;
    settled_net: MoneyAmount;
    deposited: MoneyAmount;
  };
}
