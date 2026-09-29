import { apiClient } from "./client";

export interface QboSourceFamilyAvailability {
  source_family: string;
  total_source: number;
}

export interface QboSourceEvidenceReadiness {
  available: boolean;
  reason: string | null;
  source_run_id?: string;
  source_manifest_sha256?: string;
  acquired_at?: string;
  total_source_records?: number;
  source_families?: QboSourceFamilyAvailability[];
}

export interface QboFamilyDisposition {
  source_family: string;
  total_source: number;
  applied: number;
  bound: number;
  quarantined: number;
  provider_unavailable: number;
  unsupported: number;
  rejected: number;
  unexplained: number;
  safe_majority_applied_percentage: number;
}

export interface QboApplicationLedger {
  source_evidence: QboSourceEvidenceReadiness;
  families: QboFamilyDisposition[];
  last_execution: { total_dispositions: number; last_applied_at: string | null };
  qbo_write_performed: false;
  accounting_posting_performed: false;
}

export interface QboReviewItem {
  id: string;
  source_family: string;
  provider_record_id: string;
  reference_number: string | null;
  source_date: string | null;
  source_amount: string | null;
  source_entity_names: string[];
  candidate_native_ids: string[];
  conflicting_fields: string[];
  exact_conflict: string;
  affected_dependents: string[];
  provider_version: string | null;
  allowed_actions: { action: string; required_authority: "OWNER" | "ACCOUNTANT" | "SYSTEM" | "EXTERNAL_EVIDENCE_REQUIRED" }[];
  current_decision: { id: string; action: string; authority_class: string; reason: string; decided_at: string } | null;
  unlocks: number;
  state: string;
}

export interface QboApplicationReceipt {
  classification: string;
  source_run_id: string | null;
  source_manifest_sha256: string;
  processed: number;
  created: number;
  replayed: number;
  families: QboFamilyDisposition[];
  qbo_write_performed: false;
  accounting_posting_performed: false;
}

const root = "/api/v1/accounting/source-evidence/qbo/native-application";

export const getQboApplicationLedger = async (): Promise<QboApplicationLedger> =>
  (await apiClient.get<QboApplicationLedger>(root)).data;

export const getQboReviewQueue = async (): Promise<QboReviewItem[]> =>
  (await apiClient.get<{ items: QboReviewItem[] }>(`${root}/review-queue`)).data.items;

export const applyQboSafeMajority = async (): Promise<QboApplicationReceipt> =>
  (await apiClient.post<QboApplicationReceipt>(root)).data;

export interface QboReviewDecisionInput {
  action: string;
  reason: string;
  target_native_id?: string;
  evidence_reference?: string;
  supersedes_decision_id?: string;
}

export const decideQboReview = async (
  reviewItemId: string,
  input: QboReviewDecisionInput,
): Promise<{ decision_id: string; authority_class: string }> =>
  (await apiClient.post(`${root}/review-queue/${reviewItemId}/decisions`, input)).data;
