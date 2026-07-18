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
      <div className="mt-8 grid h-80 place-items-center rounded-xl border border-slate-700 bg-slate-950 text-slate-400">
        Loading revenue trend…
      </div>
    );
  }

  if (isError) {
    return (
      <div className="mt-8 grid h-80 place-items-center rounded-xl border border-red-900 bg-red-950/30 text-red-300">
        Unable to load revenue trend.
      </div>
    );
  }

  return (
    <div className="mt-8 h-80 rounded-xl border border-slate-700 bg-slate-950 p-4">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />

          <XAxis dataKey="date" stroke="#94a3b8" />

          <YAxis
            stroke="#94a3b8"
            tickFormatter={(value) => `$${Number(value).toLocaleString()}`}
          />

          <Tooltip
            formatter={(value) => formatCurrency(Number(value))}
            contentStyle={{
              backgroundColor: "#0f172a",
              border: "1px solid #334155",
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
