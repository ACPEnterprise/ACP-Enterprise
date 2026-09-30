import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useState } from "react";

import { useRevenueTrend } from "../hooks/useRevenueTrend";

function formatAmount(value: number): string {
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 2,
  }).format(value);
}

export function RevenueTrendChart() {
  const [days, setDays] = useState(7);
  const { data, isLoading, isError } = useRevenueTrend(days);

  const chartData =
    data?.points.map((point) => ({
      date: new Date(`${point.date}T12:00:00`).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      }),
      bookedRevenue: point.booked_revenue == null ? null : Number(point.booked_revenue),
      cashCollected: point.cash_collected == null ? null : Number(point.cash_collected),
    })) ?? [];

  if (isLoading) {
    return (
      <div className="mt-ui-5 grid h-56 place-items-center rounded-xl border border-stroke bg-surface-subtle text-content-muted sm:h-72 landscape:max-h-48">
        Loading revenue trend…
      </div>
    );
  }

  if (isError) {
    return (
      <div className="mt-ui-5 grid h-56 place-items-center rounded-xl border border-status-danger/40 bg-status-danger/10 p-ui-4 text-center text-status-danger sm:h-72 landscape:max-h-48">
        Unable to load revenue trend.
      </div>
    );
  }

  if (chartData.length === 0) {
    return (
      <div className="mt-ui-5 grid h-56 place-items-center rounded-xl border border-dashed border-stroke bg-surface-subtle p-ui-4 text-center text-content-muted sm:h-72 landscape:max-h-48">
        No revenue trend data is available.
      </div>
    );
  }

  return (
    <div className="mt-ui-5 min-w-0 rounded-xl border border-stroke bg-surface-subtle p-ui-2 sm:p-ui-4">
      <div className="mb-ui-2 flex flex-wrap items-center justify-between gap-ui-2">
        <p className="text-xs text-content-muted">
          {data?.period_start ? `${new Date(data.period_start).toLocaleDateString()}–${new Date(data.period_end).toLocaleDateString()} · ${data.timezone}` : "Period unavailable"}
          {data?.completeness ? ` · ${data.completeness} evidence` : ""}
          {" · currency unavailable"}
        </p>
        <label className="text-xs font-medium text-content-secondary">
          Trend period
          <select className="ml-ui-2 rounded-md border border-stroke bg-surface px-ui-2 py-ui-1" value={days} onChange={(event) => setDays(Number(event.target.value))}>
            <option value={7}>7 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
          </select>
        </label>
      </div>
      {data?.excluded_event_count ? <p className="mb-ui-2 text-xs text-status-warning">{data.excluded_event_count} monetary event(s) excluded because their amount evidence was unavailable or invalid.</p> : null}
      <div className="h-56 sm:h-72 landscape:max-h-48">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--semantic-border)" />

          <XAxis dataKey="date" stroke="var(--semantic-text-muted)" />

          <YAxis
            stroke="var(--semantic-text-muted)"
            tickFormatter={(value) => formatAmount(Number(value))}
          />

          <Tooltip
            formatter={(value) => formatAmount(Number(value))}
            contentStyle={{
              backgroundColor: "var(--semantic-surface)",
              border: "1px solid var(--semantic-border)",
              color: "var(--semantic-text-primary)",
              borderRadius: "12px",
            }}
          />

          <Line
            type="monotone"
            dataKey="bookedRevenue"
            stroke="#2563eb"
            strokeWidth={3}
            name="Booked Revenue"
          />

          <Line
            type="monotone"
            dataKey="cashCollected"
            stroke="#10b981"
            strokeWidth={3}
            name="Cash Collected"
          />
        </LineChart>
      </ResponsiveContainer>
      </div>
    </div>
  );
}
