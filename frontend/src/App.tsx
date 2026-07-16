import {
  Activity,
  Bell,
  Building2,
  CalendarDays,
  CircleDollarSign,
  LayoutDashboard,
  Radio,
  Settings,
  Users,
  Wrench,
} from "lucide-react";

import { useAnalyticsSummary } from "./hooks/useAnalyticsSummary";

const navigation = [
  { name: "Mission Control", icon: LayoutDashboard, active: true },
  { name: "Dispatch", icon: CalendarDays, active: false },
  { name: "Customers", icon: Users, active: false },
  { name: "Jobs", icon: Wrench, active: false },
  { name: "Accounting", icon: CircleDollarSign, active: false },
  { name: "Settings", icon: Settings, active: false },
];

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

function App() {
  const { data, isLoading, isError, error, dataUpdatedAt } =
    useAnalyticsSummary();

  const metrics = data
    ? [
        {
          label: data.cash_collected.name,
          value: formatCurrency(data.cash_collected.value),
          detail: `${data.cash_collected.event_count ?? 0} payment events`,
        },
        {
          label: data.booked_revenue.name,
          value: formatCurrency(data.booked_revenue.value),
          detail: `${data.booked_revenue.event_count ?? 0} booking events`,
        },
        {
          label: data.new_customers.name,
          value: String(data.new_customers.value),
          detail: "Customers created today",
        },
        {
          label: data.appointments_booked.name,
          value: String(data.appointments_booked.value),
          detail: "Appointments booked today",
        },
        {
          label: data.total_events.name,
          value: String(data.total_events.value),
          detail: "Business events processed",
        },
      ]
    : [];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="flex min-h-screen">
        <aside className="hidden w-72 border-r border-slate-800 bg-slate-950 lg:flex lg:flex-col">
          <div className="flex h-20 items-center gap-3 border-b border-slate-800 px-6">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-600">
              <Building2 size={24} />
            </div>

            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-blue-400">
                ACP Enterprise
              </p>
              <p className="text-lg font-semibold text-white">
                Mission Control
              </p>
            </div>
          </div>

          <nav className="flex-1 space-y-2 p-4">
            {navigation.map((item) => {
              const Icon = item.icon;

              return (
                <button
                  key={item.name}
                  type="button"
                  className={`flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left text-sm font-medium transition ${
                    item.active
                      ? "bg-blue-600 text-white"
                      : "text-slate-400 hover:bg-slate-900 hover:text-white"
                  }`}
                >
                  <Icon size={20} />
                  {item.name}
                </button>
              );
            })}
          </nav>

          <div className="border-t border-slate-800 p-4">
            <div className="rounded-xl bg-slate-900 p-4">
              <p className="text-sm font-semibold text-white">
                All County Plumbing
              </p>
              <p className="mt-1 text-xs text-slate-400">
                Clearwater, Florida
              </p>
            </div>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-20 items-center justify-between border-b border-slate-800 bg-slate-950 px-5 md:px-8">
            <div>
              <p className="text-sm text-slate-400">Operations Overview</p>
              <h1 className="text-xl font-semibold text-white">
                Business Command Center
              </h1>
            </div>

            <div className="flex items-center gap-3">
              <div className="hidden items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-300 sm:flex">
                <Radio size={15} className="animate-pulse" />
                {isError ? "API Offline" : "System Online"}
              </div>

              <button
                type="button"
                className="rounded-xl border border-slate-800 bg-slate-900 p-3 text-slate-300"
              >
                <Bell size={19} />
              </button>
            </div>
          </header>

          <main className="flex-1 overflow-y-auto p-5 md:p-8">
            <section className="mb-8">
              <div className="flex items-center gap-2 text-blue-400">
                <Activity size={18} />
                <span className="text-sm font-medium">
                  Real-Time Operations
                </span>
              </div>

              <h2 className="mt-2 text-3xl font-bold tracking-tight text-white">
                Mission Control
              </h2>

              <p className="mt-2 text-slate-400">
                Live operating intelligence for All County Plumbing and Leak.
              </p>

              {dataUpdatedAt > 0 && (
                <p className="mt-2 text-xs text-slate-600">
                  Last updated: {new Date(dataUpdatedAt).toLocaleTimeString()}
                </p>
              )}
            </section>

            {isLoading && (
              <div className="rounded-2xl border border-slate-800 bg-slate-900 p-8 text-slate-400">
                Loading live analytics…
              </div>
            )}

            {isError && (
              <div className="rounded-2xl border border-red-900 bg-red-950/40 p-6 text-red-300">
                Unable to load analytics from the FastAPI backend.
                <div className="mt-2 text-sm text-red-400">
                  {error instanceof Error ? error.message : "Unknown API error"}
                </div>
              </div>
            )}

            {data && (
              <>
                <section className="grid gap-5 sm:grid-cols-2 xl:grid-cols-5">
                  {metrics.map((metric) => (
                    <article
                      key={metric.label}
                      className="rounded-2xl border border-slate-800 bg-slate-900 p-5"
                    >
                      <p className="text-sm text-slate-400">{metric.label}</p>
                      <p className="mt-3 text-3xl font-bold text-white">
                        {metric.value}
                      </p>
                      <p className="mt-2 text-xs text-slate-500">
                        {metric.detail}
                      </p>
                    </article>
                  ))}
                </section>

                <section className="mt-8 grid gap-6 xl:grid-cols-[1.5fr_1fr]">
                  <article className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
                    <p className="text-sm text-blue-400">Live Analytics</p>
                    <h3 className="mt-1 text-xl font-semibold text-white">
                      Revenue Performance
                    </h3>

                    <div className="mt-8 grid min-h-56 place-items-center rounded-xl border border-dashed border-slate-700 bg-slate-950">
                      <div className="text-center">
                        <p className="text-4xl font-bold text-white">
                          {formatCurrency(data.booked_revenue.value)}
                        </p>
                        <p className="mt-2 text-sm text-slate-500">
                          Booked revenue today
                        </p>
                      </div>
                    </div>
                  </article>

                  <article className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
                    <p className="text-sm text-blue-400">
                      Business Event Engine
                    </p>
                    <h3 className="mt-1 text-xl font-semibold text-white">
                      Recent Activity
                    </h3>

                    <div className="mt-6 space-y-5">
                      {data.recent_activity.length === 0 && (
                        <p className="text-sm text-slate-500">
                          No recent activity.
                        </p>
                      )}

                      {data.recent_activity.map((event, index) => (
                        <div
                          key={`${event.event_type}-${event.occurred_at}-${index}`}
                          className="flex gap-3"
                        >
                          <div className="mt-1 h-2.5 w-2.5 rounded-full bg-emerald-400" />

                          <div>
                            <p className="text-sm font-medium text-slate-200">
                              {formatEventName(event.event_type)}
                            </p>
                            <p className="mt-1 text-xs text-slate-500">
                              {event.entity_type} ·{" "}
                              {new Date(event.occurred_at).toLocaleTimeString()}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </article>
                </section>
              </>
            )}
          </main>
        </div>
      </div>
    </div>
  );
}

export default App;
