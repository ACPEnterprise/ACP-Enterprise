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
export type BeaconSignalSource = "scheduling" | "jobs" | "invoices";
export type BeaconPriorityBand =
  | "critical"
  | "immediate"
  | "important"
  | "monitor";
export type BeaconLifecycleAction = "acknowledge" | "review" | "snooze";

export interface BeaconLifecycleEvent {
  id: string;
  condition_key: string;
  signal_id: string;
  rule_code: string;
  signal_source: BeaconSignalSource;
  evidence_digest: string;
  action: BeaconLifecycleAction;
  actor_membership_id: string;
  action_at: string;
  snooze_until: string | null;
  created_at: string;
}

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
  condition_key: string;
  evidence_digest: string;
  rule_code: string;
  source: BeaconSignalSource;
  title: string;
  category: BeaconCategory;
  severity: BeaconSeverity;
  priority: {
    band: BeaconPriorityBand;
    score: number;
    rank: number;
    ranking_factors: Array<{
      name: string;
      value: string | number | boolean | null;
      unit: string | null;
      availability: "measured" | "not_applicable";
      contribution: number;
      explanation: string;
    }>;
    explanation: string;
    evaluated_at: string;
    tie_break_semantics: string;
  };
  lifecycle: {
    status: "active" | "acknowledged" | "reviewed" | "snoozed";
    latest_event: BeaconLifecycleEvent | null;
    temporarily_suppressed: boolean;
  };
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
  snoozed_items: BeaconSignal[];
  evaluated_at: string;
  expires_at: string;
  lifecycle_commands_available: boolean;
}

export async function getBeaconSignals(): Promise<BeaconSignalPage> {
  return (await apiClient.get<BeaconSignalPage>("/api/v1/beacon/signals")).data;
}

export async function recordBeaconLifecycleAction(
  signal: Pick<BeaconSignal, "id" | "evidence_digest">,
  action: BeaconLifecycleAction,
  snoozeUntil?: string,
): Promise<BeaconLifecycleEvent> {
  const payload = {
    evidence_digest: signal.evidence_digest,
    ...(action === "snooze" ? { snooze_until: snoozeUntil } : {}),
  };
  return (
    await apiClient.post<BeaconLifecycleEvent>(
      `/api/v1/beacon/signals/${signal.id}/${action}`,
      payload,
    )
  ).data;
}

export async function getBeaconLifecycleHistory(
  conditionKey: string,
): Promise<BeaconLifecycleEvent[]> {
  return (
    await apiClient.get<{ items: BeaconLifecycleEvent[] }>(
      "/api/v1/beacon/lifecycle-events",
      { params: { condition_key: conditionKey } },
    )
  ).data.items;
}
