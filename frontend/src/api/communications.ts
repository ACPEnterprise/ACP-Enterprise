import { apiClient } from "./client";

export interface CommunicationHistoryItem {
  id: string;
  communication_type: string;
  channel: "email" | "sms";
  customer_id: string;
  contact_id: string;
  recipient: string;
  state: "pending" | "claimed" | "retry_scheduled" | "sent" | "failed";
  retry_count: number;
  terminal_failure: boolean;
  scheduled_at: string;
  sent_at: string | null;
  failed_at: string | null;
  error_code: string | null;
  error_category: string | null;
  created_at: string;
}

export async function listCustomerCommunicationHistory(
  customerId: string,
): Promise<CommunicationHistoryItem[]> {
  const response = await apiClient.get<{ items: CommunicationHistoryItem[] }>(
    "/api/v1/communications/history",
    { params: { customer_id: customerId, limit: 50 } },
  );
  return response.data.items;
}
