export interface AnalyticsMetric {
  name: string;
  value: string | number;
  event_count?: number;
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
  new_customers: AnalyticsMetric;
  appointments_booked: AnalyticsMetric;
  total_events: AnalyticsMetric;
  recent_activity: RecentActivity[];
}

export interface RevenueTrendPoint {
  date: string;
  booked_revenue: string;
  cash_collected: string;
  booked_event_count: number;
  payment_event_count: number;
}

export interface RevenueTrend {
  period_start: string;
  period_end: string;
  timezone: string;
  days: number;
  points: RevenueTrendPoint[];
}
