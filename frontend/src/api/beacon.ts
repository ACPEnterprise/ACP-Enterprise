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
export type BeaconWorkflowAction =
  | "acknowledge"
  | "claim"
  | "assign"
  | "transfer"
  | "release";

export interface BeaconWorkflowState {
  company_id: string;
  branch_id: string | null;
  condition_key: string;
  signal_id: string;
  definition_id: string;
  definition_version: number;
  evidence_digest: string;
  workflow_version: number;
  acknowledged: boolean;
  acknowledged_by_user_id: string | null;
  acknowledged_at: string | null;
  owner_user_id: string | null;
  owned_since: string | null;
  last_action: BeaconWorkflowAction | null;
  last_actor_user_id: string | null;
  updated_at: string | null;
}

export interface BeaconWorkflowEvent {
  id: string;
  state: BeaconWorkflowState;
  action: BeaconWorkflowAction;
  actor_user_id: string;
  previous_owner_user_id: string | null;
  request_id: string;
  occurred_at: string;
}

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
  definition_id: string;
  definition_version: number;
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
  workflow?: BeaconWorkflowState | null;
  escalation: {
    state: "normal" | "escalated";
    eligibility:
      | "escalation_ready"
      | "policy_missing"
      | "not_evaluable"
      | "not_applicable";
    escalated_at: string | null;
    reason: string;
  } | null;
}

export interface BeaconSignalPage {
  items: BeaconSignal[];
  snoozed_items: BeaconSignal[];
  evaluated_at: string;
  expires_at: string;
  lifecycle_commands_available: boolean;
}

export async function getBeaconSignals(): Promise<BeaconSignalPage> {
  const [page, workflow] = await Promise.all([
    apiClient.get<BeaconSignalPage>("/api/v1/beacon/signals"),
    apiClient.get<{
      ranking_version: string;
      ranking_digest: string;
      items: Array<{
        signal: BeaconSignal;
        ranking: {
          position: number;
          priority_band: BeaconPriorityBand;
          ranking_reason: string;
        };
        workflow: BeaconWorkflowState | null;
        escalation: BeaconSignal["escalation"];
      }>;
    }>("/api/v1/beacon/operational-signals/workflow", {
      params: { view: "all" },
    }),
  ]);
  return {
    ...page.data,
    items: workflow.data.items.map((item) => ({
      ...item.signal,
      priority: {
        ...item.signal.priority,
        band: item.ranking.priority_band,
        rank: item.ranking.position,
        explanation: item.ranking.ranking_reason,
      },
      workflow: item.workflow,
      escalation: item.escalation,
    })),
  };
}

export async function recordBeaconLifecycleAction(
  signal: Pick<BeaconSignal, "id" | "evidence_digest">,
  action: BeaconLifecycleAction,
  snoozeUntil?: string,
): Promise<BeaconLifecycleEvent> {
  const payload = {
    evidence_digest: signal.evidence_digest,
    ...(action === "acknowledge" ? { request_id: crypto.randomUUID() } : {}),
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

export async function recordBeaconWorkflowAction(
  signal: Pick<BeaconSignal, "id" | "evidence_digest">,
  action: BeaconWorkflowAction,
  expectedVersion?: number,
  ownerUserId?: string,
): Promise<BeaconWorkflowEvent> {
  return (
    await apiClient.post<BeaconWorkflowEvent>(
      `/api/v1/beacon/signals/${signal.id}/${action}`,
      {
        evidence_digest: signal.evidence_digest,
        request_id: crypto.randomUUID(),
        ...(action !== "acknowledge"
          ? { expected_version: expectedVersion ?? 0 }
          : {}),
        ...(action === "assign" || action === "transfer"
          ? { owner_user_id: ownerUserId }
          : {}),
      },
    )
  ).data;
}

export async function getBeaconWorkflowHistory(
  conditionKey: string,
): Promise<BeaconWorkflowEvent[]> {
  return (
    await apiClient.get<{ items: BeaconWorkflowEvent[] }>(
      "/api/v1/beacon/workflow-history",
      { params: { condition_key: conditionKey } },
    )
  ).data.items;
}
