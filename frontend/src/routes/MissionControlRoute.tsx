import { Activity, Radio } from "lucide-react";

import { RevenueTrendChart } from "../components/RevenueTrendChart";
import { KPIStatCard } from "../components/dashboard/KPIStatCard";
import { Leaderboard } from "../components/dashboard/Leaderboard";
import { RevenueGoalCard } from "../components/dashboard/RevenueGoalCard";
import { useAnalyticsSummary } from "../hooks/useAnalyticsSummary";

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
      <section className="mb-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-blue-400">
            <Activity size={18} />
            <span className="text-sm font-medium">Real-Time Operations</span>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-300">
            <Radio size={15} className="animate-pulse" />
            {isError ? "API Offline" : "System Online"}
          </div>
        </div>
        <h2 className="mt-2 text-3xl font-bold tracking-tight text-white">Mission Control</h2>
        <p className="mt-2 text-slate-400">Live operating intelligence for All County Plumbing and Leak.</p>
        {dataUpdatedAt > 0 && <p className="mt-2 text-xs text-slate-600">Last updated: {new Date(dataUpdatedAt).toLocaleTimeString()}</p>}
      </section>

      {isLoading && <div className="rounded-2xl border border-slate-800 bg-slate-900 p-8 text-slate-400">Loading live analytics…</div>}
      {isError && (
        <div className="rounded-2xl border border-red-900 bg-red-950/40 p-6 text-red-300">
          Unable to load analytics from the FastAPI backend.
          <div className="mt-2 text-sm text-red-400">{error instanceof Error ? error.message : "Unknown API error"}</div>
        </div>
      )}
      {data && (
        <>
          <section className="grid gap-5 sm:grid-cols-2 xl:grid-cols-5">
            {metrics.map((metric) => <KPIStatCard key={metric.label} label={metric.label} value={metric.value} detail={metric.detail} />)}
          </section>
          <RevenueGoalCard title="Today's Revenue Goal" goal={5000} current={Number(data.booked_revenue.value)} />
          <section className="mt-8 grid gap-6 xl:grid-cols-[1.5fr_1fr]">
            <article className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
              <p className="text-sm text-blue-400">Live Analytics</p>
              <h3 className="mt-1 text-xl font-semibold text-white">Revenue Performance</h3>
              <RevenueTrendChart />
            </article>
            <article className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
              <p className="text-sm text-blue-400">Business Event Engine</p>
              <h3 className="mt-1 text-xl font-semibold text-white">Recent Activity</h3>
              <div className="mt-6 space-y-5">
                {data.recent_activity.length === 0 && <p className="text-sm text-slate-500">No recent activity.</p>}
                {data.recent_activity.map((event, index) => (
                  <div key={`${event.event_type}-${event.occurred_at}-${index}`} className="flex gap-3">
                    <div className="mt-1 h-2.5 w-2.5 rounded-full bg-emerald-400" />
                    <div>
                      <p className="text-sm font-medium text-slate-200">{formatEventName(event.event_type)}</p>
                      <p className="mt-1 text-xs text-slate-500">{event.entity_type} · {new Date(event.occurred_at).toLocaleTimeString()}</p>
                    </div>
                  </div>
                ))}
              </div>
            </article>
          </section>
          <section className="mt-8">
            <Leaderboard
              title="Top Technicians"
              subtitle="Today's production"
              rows={[
                { id: "1", name: "Mike", primaryValue: "$4,250", secondaryValue: "6 completed jobs" },
                { id: "2", name: "John", primaryValue: "$3,980", secondaryValue: "5 completed jobs" },
                { id: "3", name: "David", primaryValue: "$2,740", secondaryValue: "4 completed jobs" },
              ]}
            />
          </section>
        </>
      )}
    </>
  );
}
