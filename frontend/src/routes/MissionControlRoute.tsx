import { Activity, Radio } from "lucide-react";

import { RevenueTrendChart } from "../components/RevenueTrendChart";
import { KPIStatCard } from "../components/dashboard/KPIStatCard";
import { useAnalyticsSummary } from "../hooks/useAnalyticsSummary";
import { Alert, Card, Spinner } from "../ui";

function formatCurrency(value: string | number): string {
  const numericValue = Number(value);
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(Number.isFinite(numericValue) ? numericValue : 0);
}

function formatEventName(eventType: string): string {
  return eventType
    .replaceAll(".", " ")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function MissionControlRoute() {
  const { data, isLoading, isError, error, dataUpdatedAt } = useAnalyticsSummary();
  const metrics = data
    ? [
        { label: data.cash_collected.name, value: formatCurrency(data.cash_collected.value), detail: `${data.cash_collected.event_count ?? 0} payment events` },
        { label: data.booked_revenue.name, value: formatCurrency(data.booked_revenue.value), detail: `${data.booked_revenue.event_count ?? 0} booking events` },
        { label: data.new_customers.name, value: String(data.new_customers.value), detail: "Customers created today" },
        { label: data.appointments_booked.name, value: String(data.appointments_booked.value), detail: "Appointments booked today" },
        { label: data.total_events.name, value: String(data.total_events.value), detail: "Business events processed" },
      ]
    : [];

  return (
    <>
      <section className="mb-ui-6 sm:mb-ui-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-action-primary">
            <Activity size={18} />
            <span className="text-sm font-medium">Real-Time Operations</span>
          </div>
          <div className="flex min-h-11 items-center gap-2 rounded-full border border-stroke bg-surface-subtle px-4 py-2 text-sm text-content-secondary">
            <Radio size={15} aria-hidden="true" />
            {isError
              ? "Analytics API unavailable"
              : isLoading
                ? "Checking analytics API"
                : "Analytics API available"}
          </div>
        </div>
        <h2 className="mt-2 text-2xl font-bold tracking-tight text-content sm:text-3xl">Mission Control</h2>
        <p className="mt-2 text-content-muted">Authoritative analytics currently available to ACP Enterprise.</p>
        <p className="mt-2 text-xs text-content-muted">
          Analytics API availability does not represent complete operational system health.
        </p>
        {dataUpdatedAt > 0 && <p className="mt-2 text-xs text-content-muted">Last updated: {new Date(dataUpdatedAt).toLocaleTimeString()}</p>}
      </section>

      {isLoading && <Card className="flex min-h-32 items-center justify-center"><Spinner label="Loading analytics" /></Card>}
      {isError && (
        <Alert variant="danger" title="Analytics unavailable">
          Unable to load analytics from the FastAPI backend.
          <span className="mt-2 block text-sm">{error instanceof Error ? error.message : "Unknown API error"}</span>
        </Alert>
      )}
      {data && (
        <>
          <section className="grid gap-ui-3 sm:grid-cols-2 xl:grid-cols-5">
            {metrics.map((metric) => <KPIStatCard key={metric.label} label={metric.label} value={metric.value} detail={metric.detail} />)}
          </section>
          <section className="mt-ui-6 grid gap-ui-5 xl:grid-cols-[1.5fr_1fr]">
            <Card>
              <p className="text-sm text-action-primary">Live Analytics</p>
              <h3 className="mt-1 text-xl font-semibold text-content">Revenue Performance</h3>
              <RevenueTrendChart />
            </Card>
            <Card>
              <p className="text-sm text-action-primary">Business Event Engine</p>
              <h3 className="mt-1 text-xl font-semibold text-content">Recent Activity</h3>
              <div className="mt-ui-5 space-y-ui-4">
                {data.recent_activity.length === 0 && <p className="text-sm text-content-muted">No recent authoritative activity is available.</p>}
                {data.recent_activity.map((event, index) => (
                  <div key={`${event.event_type}-${event.occurred_at}-${index}`} className="flex gap-3">
                    <div className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-status-success" />
                    <div className="min-w-0">
                      <p className="break-words text-sm font-medium text-content">{formatEventName(event.event_type)}</p>
                      <p className="mt-1 break-words text-xs text-content-muted">{event.entity_type} · {new Date(event.occurred_at).toLocaleTimeString()}</p>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </section>
        </>
      )}
    </>
  );
}
