export interface FinancialListItem {
  id: string;
  number: string;
  status: string;
  job_id: string;
  job_number: string;
  customer_id: string;
  customer_display_name: string;
  currency: string;
  total_amount: string;
  created_at: string;
}

export interface FinancialLineItem {
  id: string;
  position: number;
  description: string;
  quantity: string;
  unit_price: string;
  total_amount: string;
}

export interface Payment {
  id: string;
  invoice_id: string;
  customer_id: string;
  amount: string;
  currency: string;
  status: string;
  paid_at: string | null;
  method: string | null;
  reference: string | null;
  created_at: string;
}

export interface FinancialDetail extends FinancialListItem {
  branch_id: string;
  service_location_id: string;
  subtotal_amount: string;
  tax_amount: string;
  issued_at: string | null;
  due_on: string | null;
  presented_at: string | null;
  expires_on: string | null;
  line_items: FinancialLineItem[];
  payments: Payment[];
}

export interface PaginatedFinancials {
  items: FinancialListItem[];
  page: number;
  page_size: number;
  total_count: number;
  total_pages: number;
}

export interface PaginatedPayments {
  items: Payment[];
  page: number;
  page_size: number;
  total_count: number;
  total_pages: number;
}
