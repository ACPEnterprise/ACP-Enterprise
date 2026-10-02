import { z } from "zod";
import type { ApiClient } from "./client";

const amountSchema = z.object({ amount: z.string().nullable(), currency: z.string().nullable(), state: z.enum(["available", "partial", "stale", "refreshing", "unavailable"]) });
const accountSchema = z.object({ source_id: z.string(), name: z.string(), account_type: z.string(), account_subtype: z.string().nullable(), balance: amountSchema });
const reportSchema = z.object({ report_key: z.string(), label: z.string(), basis: z.enum(["cash", "accrual"]).nullable(), as_of: z.string().nullable(), state: z.enum(["available", "partial", "stale", "refreshing", "unavailable"]), limitation: z.string().nullable() });
const conflictSchema = z.object({ conflict_id: z.string(), subject_label: z.string(), fact_name: z.string(), state: z.enum(["conflicting", "unresolved"]), source_assertions: z.array(z.object({ source: z.enum(["qbo", "hcp", "acp"]), value: z.string().nullable(), source_date: z.string().nullable() })), limitation: z.string() });
export const qboEvidenceSchema = z.object({
  contract_version: z.string(), source: z.literal("quickbooks_online"), mode: z.enum(["live", "historical", "blocked"]), provider_environment: z.enum(["production", "historical_control"]),
  company_identity_sha256: z.string().nullable(), company_info_verified_at: z.string().nullable(), source_manifest_sha256: z.string().nullable(), completeness: z.enum(["complete", "partial", "unavailable"]), accounting_basis: z.enum(["cash", "accrual"]), as_of: z.string().nullable(), acquired_at: z.string().nullable(), refresh_state: z.enum(["available", "partial", "stale", "refreshing", "unavailable"]), snapshot_id: z.string().nullable(), snapshot_digest: z.string().nullable(), limitations: z.array(z.string()), accounts: z.array(accountSchema), invoices: z.array(z.unknown()), bills: z.array(z.unknown()), ar: z.record(z.string(), z.unknown()), payments: z.array(z.unknown()), reports: z.array(reportSchema), conflicts: z.array(conflictSchema), mutation_authority: z.literal("none"),
});
export type QboEvidence = z.infer<typeof qboEvidenceSchema>;
export interface QboEvidenceService { cash(): Promise<QboEvidence>; }
export function createQboEvidenceService(client: ApiClient): QboEvidenceService { return { cash: () => client.request("/api/v1/accounting/source-evidence/qbo?basis=cash", qboEvidenceSchema) }; }
