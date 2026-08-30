import { apiClient } from "./client";

export interface LuminaryObservation { metric: string; value_minor: number | null; currency: string | null; unit: string; change_minor?: number | null }
export interface LuminaryEvidence { source_domain: string; record_type: string; record_id: string; digest: string }
export interface LuminaryFinding {
  id: string; finding_class: string; finding_type: string; title: string; summary: string;
  observations: LuminaryObservation[]; confidence_percent: number; completeness: string;
  freshness: string; explanation: string; limitations: string[]; investigate_next: string[];
  evidence: LuminaryEvidence[]; finding_digest: string; supersedes_finding_id: string | null;
}
export interface LuminaryBriefing {
  id: string; company_id: string; branch_id: string | null; period: { start: string; end: string };
  summary: string; completeness: string; sections: Array<{ name: string; finding_ids: string[] }>;
  briefing_digest: string; evidence_package_digest: string; supersedes_briefing_id: string | null;
  generated_at: string; findings: LuminaryFinding[];
}
export async function getLuminaryBriefing(start: string, end: string) {
  return (await apiClient.get<LuminaryBriefing>("/api/v1/luminary/briefing", { params: { start, end } })).data;
}
export async function analyzeLuminary(start: string, end: string) {
  return (await apiClient.post<LuminaryBriefing>("/api/v1/luminary/analyses", undefined, { params: { start, end } })).data;
}
