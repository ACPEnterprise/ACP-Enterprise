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
