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
