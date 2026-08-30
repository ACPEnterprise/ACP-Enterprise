export type LiaClassification =
  | "KNOWN"
  | "DERIVED"
  | "INCOMPLETE"
  | "STALE"
  | "CONFLICTING"
  | "UNAVAILABLE"
  | "UNAUTHORIZED"
  | "POLICY_REQUIRED"
  | "EXTERNAL_GATE";

export interface LiaEvidence {
  domain: string;
  label: string;
  authority: string;
  observed_at: string;
  freshness: string;
  entity_id: string | null;
  evidence_digest: string;
  count: number | null;
  state: string | null;
}

export interface LiaResponse {
  request_id: string;
  conversation_id: string;
  classification: LiaClassification;
  answer: string;
  evidence: LiaEvidence[];
  limitations: string[];
  navigation: { label: string; internal_path: string }[];
  proposals: { proposal_id: string; action: string; state: string }[];
  completeness: string;
  freshness: string;
  provider: string;
  provider_version: string;
  policy_version: string;
  evidence_digest: string;
  authorization_version: number;
  generated_at: string;
}

export interface LiaReadiness {
  state: string;
  provider_state: string;
  policy_state: string;
  deterministic_capabilities: string[];
  generative_capabilities: string[];
  policy_version: string;
  retention_state: string;
}

export interface LiaFoundationReadiness {
  foundation_version: string;
  release_profile: string;
  provider_state: "NOT_CONFIGURED" | "AVAILABLE" | "TEMPORARILY_UNAVAILABLE" | "RATE_LIMITED" | "TIMEOUT" | "UNCERTAIN" | "FAILED";
  provider_configured: boolean;
  autonomous_mutation: boolean;
  production_mutation: boolean;
  source_states: Record<string, "READY" | "PARTIAL" | "BLOCKED">;
  tool_count: number;
  executable_tool_count: number;
  permission_propagation: string;
  conversation_retention: string;
  evaluation_status: string;
  blockers: string[];
}
