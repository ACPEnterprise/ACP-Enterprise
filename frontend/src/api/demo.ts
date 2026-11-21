import { apiClient } from "./client";

export interface DemoScenario {
  code: string;
  title: string;
  position: number;
  guided_steps: Array<{ order: number; action: string }>;
  condition: Record<string, unknown>;
  record_refs: Record<string, unknown>;
}

export interface DemoProvisionResult {
  environment_id: string;
  company_id: string;
  branch_id: string;
  generation: number;
  action: string;
  counts: Record<string, number>;
}

export const getDemoScenarios = async () => (await apiClient.get<DemoScenario[]>("/api/v1/demo/scenarios")).data;
export const resetDemo = async () => (await apiClient.post<DemoProvisionResult>("/api/v1/demo/reset")).data;
export const sendDemoFeedback = async (payload: { category: string; page: string; scenario_code?: string; comment: string; app_sha: string }) => (await apiClient.post("/api/v1/demo/feedback", payload)).data;

export interface DemoEstimateDraft {
  label: string;
  estimate_id: string;
  estimate_number: string;
  status: string;
  selling_price: string;
}

export const createDemoEstimateDrafts = async () =>
  (await apiClient.post<{ drafts: DemoEstimateDraft[] }>("/api/v1/demo/estimating/water-heater-drafts")).data;
