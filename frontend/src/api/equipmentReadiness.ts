import { apiClient } from "./client";

const ROOT = "/api/v1/equipment-readiness";

export type EquipmentChecklistRequirement = "not_required" | "required_at_clock_in";
export type EquipmentConfirmationState = "present_ready" | "transferred" | "left_at_shop" | "in_repair" | "missing_or_unknown" | "incomplete_set" | "broken_or_out_of_service" | "other";

export interface EquipmentChecklistSetting { employee_id: string; equipment_checklist_requirement: EquipmentChecklistRequirement }
export interface EquipmentPromptItem { catalog_item_id: string; code: string; display_name: string; item_kind: string; placement_id: string | null; default_state: EquipmentConfirmationState; readiness_state: string; last_confirmed_at: string | null }
export interface DailyEquipmentPrompt { employee_id: string; work_date: string; required: boolean; reason: string; already_confirmed: boolean; items: EquipmentPromptItem[] }
export interface EquipmentAttention { id: string; branch_id: string; attention_code: string; priority: string; state: string; employee_id: string | null; catalog_item_id: string | null; job_id: string | null; appointment_id: string | null; title: string; explanation: string; responsibility_code: string; first_observed_at: string; last_observed_at: string; evidence_digest: string }
export interface DispatchEquipmentReadiness { employee_id: string; employee_name: string; branch_id: string; state: string; warning_codes: string[]; missing_capabilities: string[]; scheduling_eligible: boolean | null }

export const getEquipmentChecklistSetting = async (employeeId: string) =>
  (await apiClient.get<EquipmentChecklistSetting>(`${ROOT}/employees/${employeeId}/checklist-setting`)).data;
export const setEquipmentChecklistSetting = async (employeeId: string, equipment_checklist_requirement: EquipmentChecklistRequirement) =>
  (await apiClient.put<EquipmentChecklistSetting>(`${ROOT}/employees/${employeeId}/checklist-setting`, { equipment_checklist_requirement })).data;
export const getDailyEquipmentPrompt = async (employeeId: string, workDate: string) =>
  (await apiClient.get<DailyEquipmentPrompt>(`${ROOT}/employees/${employeeId}/daily-prompt`, { params: { work_date: workDate } })).data;
export const confirmDailyEquipment = async (input: { employee_id: string; work_date: string; confirmed_at: string; items: { catalog_item_id: string; placement_id: string | null; state: EquipmentConfirmationState; missing_components: string[]; note: string | null; receiving_employee_id: string | null; receiving_location_kind: string | null; receiving_location_entity_id: string | null }[]; idempotency_key: string }) =>
  (await apiClient.post(`${ROOT}/daily-confirmations`, input)).data;
export const getEquipmentAttention = async (branchId?: string) =>
  (await apiClient.get<EquipmentAttention[]>(`${ROOT}/attention`, { params: branchId ? { branch_id: branchId } : undefined })).data;
export const getDispatchEquipmentReadiness = async (branchId: string) =>
  (await apiClient.get<DispatchEquipmentReadiness[]>(`${ROOT}/dispatch/branches/${branchId}`)).data;
export const recordEquipmentChange = async (placementId: string, input: { to_employee_id: string | null; to_location_kind: string; to_location_entity_id: string | null; reason: string; event_type: string; resulting_state: string; occurred_at: string; expected_version: number; idempotency_key: string }) =>
  (await apiClient.post(`${ROOT}/placements/${placementId}/custody`, input)).data;
