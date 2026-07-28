import { apiClient } from "./client";

export type BeaconCategory =
  | "operations"
  | "revenue"
  | "customer"
  | "scheduling"
  | "workforce";
export type BeaconSeverity =
  | "information"
  | "attention"
  | "important"
  | "critical";
export type BeaconConfidenceLevel = "high" | "medium" | "low";

export interface BeaconSupportingFact {
  name: string;
  value: string | number | boolean;
  source: string;
  measured_at: string;
  evidence: Array<{
    entity_type: string;
    entity_id: string;
    event_id: string | null;
    event_type: string | null;
    occurred_at: string | null;
  }>;
  unit: string | null;
}

export interface BeaconSignal {
  id: string;
  rule_code: string;
  title: string;
  category: BeaconCategory;
  severity: BeaconSeverity;
  confidence: {
    level: BeaconConfidenceLevel;
    basis: string;
  };
  supporting_facts: BeaconSupportingFact[];
  recommended_action: string;
  created_at: string;
  expires_at: string;
  expiration_policy: "replace_on_next_evaluation";
}

export interface BeaconSignalPage {
  items: BeaconSignal[];
  evaluated_at: string;
  expires_at: string;
}

export async function getBeaconSignals(): Promise<BeaconSignalPage> {
  return (await apiClient.get<BeaconSignalPage>("/api/v1/beacon/signals")).data;
}
