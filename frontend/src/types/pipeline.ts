export type LeadStage =
  | "new"
  | "contacted"
  | "qualified"
  | "appointment_needed"
  | "scheduled"
  | "estimate_follow_up"
  | "won"
  | "lost"
  | "nurture";

export interface Lead {
  id: string;
  company_id: string;
  branch_id: string;
  customer_id: string | null;
  prospect_name: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  lead_source: string;
  source_detail: string | null;
  source_system: string | null;
  service_category: string | null;
  service_need: string;
  assigned_user_id: string | null;
  stage: LeadStage;
  created_at: string;
  last_action_at: string | null;
  next_action_type: string | null;
  next_action_due_at: string | null;
  contact_attempt_count: number;
  appointment_id: string | null;
  job_id: string | null;
  estimate_id: string | null;
  attributable_value_minor: number | null;
  value_currency: string | null;
  value_authority: string | null;
  attention_state: string | null;
  version: number;
}

export interface LeadList {
  items: Lead[];
  total: number;
  filters: Record<string, string | null>;
}

export interface LeadCreate {
  branch_id: string;
  prospect_name: string;
  contact_phone?: string;
  contact_email?: string;
  lead_source: string;
  service_category?: string;
  service_need: string;
  next_action_type?: string;
  next_action_due_at?: string;
}

