import { z } from "zod";
import type { ApiClient } from "./client";

const evidenceSchema = z.object({
  domain: z.string(), label: z.string(), authority: z.string(), observed_at: z.string(),
  freshness: z.string(), entity_id: z.string().uuid().nullable().optional(), evidence_digest: z.string(),
  count: z.number().nullable().optional(), state: z.string().nullable().optional(),
  source_contract_version: z.string().nullable().optional(), company_id: z.string().uuid().nullable().optional(),
  branch_ids: z.array(z.string().uuid()).optional().default([]), authorization_version: z.number().nullable().optional(),
  limitations: z.array(z.string()).optional().default([]), period_start: z.string().nullable().optional(),
  period_end: z.string().nullable().optional(), period_label: z.string().nullable().optional(), timezone: z.string().nullable().optional(),
});
const navigationSchema = z.object({ label: z.string(), internal_path: z.string() });
export const liaResponseSchema = z.object({
  request_id: z.string().uuid(), conversation_id: z.string().uuid(),
  response_mode: z.enum(["BRIEF", "NORMAL", "DETAILED", "EVIDENCE"]).default("NORMAL"),
  classification: z.enum(["KNOWN", "DERIVED", "INCOMPLETE", "STALE", "CONFLICTING", "UNAVAILABLE", "UNAUTHORIZED", "POLICY_REQUIRED", "EXTERNAL_GATE"]),
  authority: z.enum(["ACP_AUTHORITATIVE", "SOURCE_BACKED", "PARTIAL", "INSUFFICIENT_EVIDENCE"]),
  response_mode: z.enum(["BRIEF", "NORMAL", "DETAILED", "EVIDENCE"]),
  answer: z.string(), evidence: z.array(evidenceSchema).default([]), limitations: z.array(z.string()).default([]),
  navigation: z.array(navigationSchema).default([]), completeness: z.string(), freshness: z.string(),
  provider: z.string(), provider_version: z.string(), policy_version: z.string(), evidence_digest: z.string(),
  authorization_version: z.number(), company_id: z.string().uuid(), branch_ids: z.array(z.string().uuid()).default([]),
  subject_domain: z.string().nullable().optional(), subject_id: z.string().uuid().nullable().optional(),
  source_systems: z.array(z.string()).default([]), missing_evidence: z.array(z.string()).default([]),
  safe_next_action: z.string().nullable().optional(), as_of: z.string(), generated_at: z.string(), temporal: z.unknown().nullable().optional(),
});
export type LiaResponse = z.infer<typeof liaResponseSchema>;
export type LiaContext = { domain?: string; entity_id?: string; authorization_version?: number; evidence_digest?: string };
export interface LiaService { ask(question: string, conversationId?: string, context?: LiaContext): Promise<LiaResponse>; }
export function createLiaService(client: ApiClient): LiaService {
  return { ask: (question, conversationId, context) => client.request("/api/v1/lia/employee/ask", liaResponseSchema, { method: "POST", body: JSON.stringify({ question, ...(conversationId ? { conversation_id: conversationId } : {}), ...(context ? { context } : {}) }) }) };
}
