import { apiClient } from "./client";

export interface AuditRecord {
  id: string; action: string; outcome: string; actor_user_id: string | null;
  company_id: string; branch_id: string | null; resource_type: string;
  resource_id: string | null; reason_code: string | null; correlation_id: string;
  details: Record<string, unknown>; occurred_at: string;
}

export interface AuditFilters {
  branch_id?: string; actor_user_id?: string; resource_type?: string; action?: string;
  outcome?: string; correlation_id?: string; occurred_before?: string; before_id?: string; limit?: number;
}

export async function listAuditRecords(filters: AuditFilters): Promise<AuditRecord[]> {
  const response = await apiClient.get<AuditRecord[]>("/api/v1/platform/audit", { params: filters });
  return response.data;
}
