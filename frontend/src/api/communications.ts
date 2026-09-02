import { apiClient } from "./client";

export interface CommunicationHistoryItem {
  id: string;
  communication_type: string;
  channel: "email" | "sms" | "protected_link" | "print" | "in_app";
  customer_id: string;
  contact_id: string;
  recipient_display: string;
  state:
    | "prepared"
    | "pending"
    | "claimed"
    | "retry_scheduled"
    | "accepted"
    | "delivered"
    | "deferred"
    | "bounced"
    | "rejected"
    | "failed"
    | "uncertain"
    | "canceled"
    | "suppressed";
  retry_count: number;
  terminal_failure: boolean;
  scheduled_at: string;
  sent_at: string | null;
  failed_at: string | null;
  error_code: string | null;
  error_category: string | null;
  created_at: string;
}

export interface OperationalMessageCatalogItem {
  message_class: string;
  owner_domain: string;
  allowed_channels: string[];
  template_version: string;
  purpose: "account_security" | "transactional" | "operational" | "marketing_outreach" | "internal";
  policy_required: boolean;
}

export interface CommunicationsReadiness {
  email: string;
  sms: string;
  webhook: string;
  overall: "READY" | "DEGRADED";
  synthetic_only: boolean;
  catalog_fingerprint: string;
}

export interface CommunicationOperationsSummary {
  pending: number;
  accepted_pending_delivery: number;
  delivered: number;
  needs_attention: number;
  suppressed: number;
  oldest_pending_at: string | null;
}

export async function getCommunicationOperationsSummary(): Promise<CommunicationOperationsSummary> {
  const response = await apiClient.get<CommunicationOperationsSummary>(
    "/api/v1/communications/summary",
  );
  return response.data;
}

export async function getCommunicationsReadiness(): Promise<CommunicationsReadiness> {
  const response = await apiClient.get<CommunicationsReadiness>(
    "/api/v1/communications/readiness",
  );
  return response.data;
}

export async function listOperationalMessageCatalog(): Promise<
  OperationalMessageCatalogItem[]
> {
  const response = await apiClient.get<OperationalMessageCatalogItem[]>(
    "/api/v1/communications/catalog",
  );
  return response.data;
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
