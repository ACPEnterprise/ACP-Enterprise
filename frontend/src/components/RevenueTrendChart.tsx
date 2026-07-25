import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useRevenueTrend } from "../hooks/useRevenueTrend";

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

export function RevenueTrendChart() {
  const { data, isLoading, isError } = useRevenueTrend();

  const chartData =
    data?.points.map((point) => ({
      date: new Date(`${point.date}T12:00:00`).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      }),
      bookedRevenue: Number(point.booked_revenue),
      cashCollected: Number(point.cash_collected),
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
    <div className="mt-ui-5 h-56 min-w-0 rounded-xl border border-stroke bg-surface-subtle p-ui-2 sm:h-72 sm:p-ui-4 landscape:max-h-48">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--semantic-border)" />

          <XAxis dataKey="date" stroke="var(--semantic-text-muted)" />

          <YAxis
            stroke="var(--semantic-text-muted)"
            tickFormatter={(value) => `$${Number(value).toLocaleString()}`}
          />

          <Tooltip
            formatter={(value) => formatCurrency(Number(value))}
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
  );
}
