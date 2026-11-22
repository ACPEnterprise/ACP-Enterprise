export interface AnalyticsMetric {
  name: string;
  value: string | number | null;
  event_count?: number;
  observed_event_count?: number;
  excluded_event_count?: number;
  completeness?: "COMPLETE" | "PARTIAL" | "NO_EVENTS";
  authority?: string;
}

export interface AnalyticsCountMetric {
  name: string;
  value: string | number;
}

export interface RecentActivity {
  event_type: string;
  entity_type: string;
  payload: Record<string, unknown>;
  occurred_at: string;
}

export interface AnalyticsSummary {
  period_start: string;
  period_end: string;
  timezone: string;
  cash_collected: AnalyticsMetric;
  booked_revenue: AnalyticsMetric;
  new_customers: AnalyticsCountMetric;
  appointments_booked: AnalyticsCountMetric;
  total_events: AnalyticsCountMetric;
  recent_activity: RecentActivity[];
}

export type AnalyticsMetricKey =
  | "cash_collected"
  | "booked_revenue"
  | "new_customers"
  | "appointments_booked"
  | "total_events";

export interface AnalyticsDrilldownEvent {
  id: string;
  event_type: string;
  entity_type: string;
  entity_id: string | null;
  occurred_at: string;
  amount: string | null;
}

export interface AnalyticsDrilldown {
  metric: AnalyticsMetricKey;
  metric_name: string;
  company_id: string;
  company_name: string;
  period_start: string;
  period_end: string;
  timezone: string;
  value: string | null;
  event_count: number;
  observed_event_count: number;
  excluded_event_count: number;
  completeness: "COMPLETE" | "PARTIAL" | "NO_EVENTS";
  authority: string;
  events: AnalyticsDrilldownEvent[];
}

export interface RevenueTrendPoint {
  date: string;
  booked_revenue: string | null;
  cash_collected: string | null;
  booked_event_count: number;
  payment_event_count: number;
  excluded_booked_event_count: number;
  excluded_payment_event_count: number;
}

export interface RevenueTrend {
  period_start: string;
  period_end: string;
  timezone: string;
  days: number;
  authority: string;
  completeness: "COMPLETE" | "PARTIAL" | "NO_EVENTS";
  excluded_event_count: number;
  points: RevenueTrendPoint[];
}
