import { apiClient } from "./client";

export interface QualityIssue {
  rule_id: string; domain: string; state: string; severity: string;
  launch_impact: string; safe_record_identity: string; explanation: string;
  missing_or_conflicting_evidence: string[]; repair_owner: string;
  evidence_digest: string; blocks_new_operation: boolean;
}
export interface QualitySummary {
  catalog_version: string; catalog_digest: string; company_id: string;
  branch_scope: string[]; scanned_rules: number; total_issues: number;
  blocks_new_operation: number; historical_only: number; owner_review: number;
  issues: QualityIssue[]; limit: number; offset: number;
}

export async function getDataQualitySummary(limit = 100, offset = 0): Promise<QualitySummary> {
  const response = await apiClient.get<QualitySummary>("/api/v1/data-quality/summary", { params: { limit, offset } });
  return response.data;
}
