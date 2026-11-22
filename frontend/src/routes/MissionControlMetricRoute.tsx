import { Link, useSearchParams } from "react-router";

import { useAuth, useHasPermission } from "../auth";
import { useAnalyticsMetricDetail } from "../hooks/useAnalyticsMetricDetail";
import type { AnalyticsMetricKey } from "../types/analytics";
import { Alert, Card, CardContent, CardDescription, CardHeader, CardTitle, Spinner } from "../ui";

const metricKeys = new Set<AnalyticsMetricKey>([
  "cash_collected",
  "booked_revenue",
  "new_customers",
  "appointments_booked",
  "total_events",
]);

function recordPath(entityType: string, entityId: string | null): string | null {
  if (!entityId) return null;
  const paths: Record<string, string> = {
    appointment: "appointments",
    customer: "customers",
    invoice: "invoices",
    job: "jobs",
    payment: "payments",
  };
  const resource = paths[entityType.toLowerCase()];
  return resource ? `/${resource}/${encodeURIComponent(entityId)}` : null;
}

function formatValue(value: string | null, metric: AnalyticsMetricKey): string {
  if (value == null) return "Unavailable";
  if (metric === "cash_collected" || metric === "booked_revenue") {
    return Number(value).toLocaleString(undefined, { style: "currency", currency: "USD" });
  }
  return Number(value).toLocaleString();
}

export function MissionControlMetricRoute() {
  const [searchParams] = useSearchParams();
  const { activeCompany } = useAuth();
  const canRead = useHasPermission("COMPANY_ANALYTICS_READ");
  const metricParam = searchParams.get("metric");
  const metric = metricParam && metricKeys.has(metricParam as AnalyticsMetricKey)
    ? metricParam as AnalyticsMetricKey
    : null;
  const periodStart = searchParams.get("period_start");
  const periodEnd = searchParams.get("period_end");
  const detail = useAnalyticsMetricDetail(
    metric,
    periodStart,
    periodEnd,
    canRead && Boolean(activeCompany),
  );

  if (!canRead) return <Alert variant="danger">You are not authorized to view Mission Control analytics.</Alert>;
  if (!metric) return <Alert variant="danger">This Mission Control metric is unavailable.</Alert>;
  if (!activeCompany) return <Alert variant="danger" title="Company context unavailable">Select an accessible Company before opening metric detail.</Alert>;

  return (
    <div className="mx-auto max-w-5xl space-y-6 pb-12">
      <header>
        <Link className="text-sm font-semibold text-action-primary hover:underline" to="/mission-control">← Back to Mission Control</Link>
        <p className="mt-4 text-sm font-semibold text-action-primary">Mission Control drill-down</p>
        <h1 className="mt-1 text-2xl font-bold sm:text-3xl">{detail.data?.metric_name ?? "Metric detail"}</h1>
        <p className="mt-2 text-content-muted">{activeCompany.name} · source-backed business-event records</p>
      </header>
      {detail.isPending && <Spinner label="Loading metric detail" />}
      {detail.isError && <Alert variant="danger" title="Metric detail unavailable">The selected source-backed records could not be loaded. No total was inferred.</Alert>}
      {detail.data && (
        <>
          <Card className="dashboard-card-border">
            <CardHeader>
              <CardTitle>{formatValue(detail.data.value, detail.data.metric)}</CardTitle>
              <CardDescription>
                {new Date(detail.data.period_start).toLocaleString()} – {new Date(detail.data.period_end).toLocaleString()} · {detail.data.timezone}
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 text-sm sm:grid-cols-3">
              <p><span className="text-content-muted">Included records</span><strong className="block">{detail.data.event_count}</strong></p>
              <p><span className="text-content-muted">Observed records</span><strong className="block">{detail.data.observed_event_count}</strong></p>
              <p><span className="text-content-muted">Evidence state</span><strong className="block">{detail.data.completeness}</strong></p>
            </CardContent>
          </Card>
          {detail.data.completeness !== "COMPLETE" && (
            <Alert variant="warning" title="Source evidence is incomplete">
              {detail.data.excluded_event_count} observed record{detail.data.excluded_event_count === 1 ? " is" : "s are"} missing usable amount evidence. The displayed total excludes those records and does not treat them as zero.
            </Alert>
          )}
          <Card>
            <CardHeader>
              <CardTitle>Underlying records</CardTitle>
              <CardDescription>Records are restricted to the authenticated company and selected period.</CardDescription>
            </CardHeader>
            <CardContent>
              {detail.data.events.length === 0 ? <p className="text-sm text-content-muted">No source-backed records were observed for this metric and period.</p> : (
                <ul className="space-y-2">
                  {detail.data.events.map((event) => {
                    const path = recordPath(event.entity_type, event.entity_id);
                    return <li className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-stroke p-3" key={event.id}>
                      <div>
                        <p className="font-medium">{event.event_type.replaceAll(".", " ")}</p>
                        <p className="text-xs text-content-muted">{event.entity_type} · {event.entity_id ?? "Source record identity unavailable"} · {new Date(event.occurred_at).toLocaleString()}</p>
                      </div>
                      <div className="text-right">
                        {event.amount !== null && <p className="font-semibold">{formatValue(event.amount, detail.data.metric)}</p>}
                        {path ? <Link className="text-sm font-semibold text-action-primary hover:underline" to={path}>Open source record</Link> : <p className="text-xs text-content-muted">No navigable record identity</p>}
                      </div>
                    </li>;
                  })}
                </ul>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
