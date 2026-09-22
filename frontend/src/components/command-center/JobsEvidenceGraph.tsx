import { Link } from "react-router";

import type { JobTrendPoint } from "../../types/jobs";

type Metric = "produced_value" | "job_count";

function pointValue(point: JobTrendPoint, metric: Metric): number | null {
  if (metric === "job_count") return point.job_count;
  return point.produced_value === null ? null : Number(point.produced_value);
}

function displayProducedValue(value: number, currency: string | null): string {
  if (!currency) return value === 0 ? "Measured zero" : "Currency unavailable";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

function drilldown(point: JobTrendPoint, branchId?: string): string {
  const query = new URLSearchParams({
    status: "completed",
    completedStartAt: point.completed_start_at,
    completedEndAt: point.completed_end_at,
  });
  if (branchId) query.set("branchId", branchId);
  return `/jobs?${query.toString()}`;
}

export function JobsEvidenceGraph({
  points,
  metric,
  branchId,
  currency,
}: {
  readonly points: readonly JobTrendPoint[];
  readonly metric: Metric;
  readonly branchId?: string;
  readonly currency: string | null;
}) {
  const values = points.map((point) => pointValue(point, metric));
  const maximum = Math.max(
    1,
    ...values.filter((value): value is number => value !== null),
  );
  const columnWidth = 900 / Math.max(points.length, 1);

  return (
    <div>
      <div className="overflow-x-auto rounded-lg bg-surface-muted p-3">
        <svg
          aria-label={
            metric === "job_count"
              ? "Completed Job count graph"
              : "Produced value graph"
          }
          className="h-64 min-w-[42rem] w-full"
          role="img"
          viewBox="0 0 1000 280"
        >
          <line
            stroke="var(--semantic-border-strong)"
            x1="60"
            x2="970"
            y1="230"
            y2="230"
          />
          {points.map((point, index) => {
            const value = values[index];
            const height =
              value === null
                ? 0
                : Math.max(value === 0 ? 2 : 8, (value / maximum) * 180);
            const x = 65 + index * columnWidth;
            const href = drilldown(point, branchId);
            const display =
              metric === "job_count"
                ? `${point.job_count} Jobs`
                : value === null
                  ? "Produced value unavailable"
                  : displayProducedValue(value, currency);
            return (
              <a
                aria-label={`${point.label}: ${display}. Open ${point.job_count} underlying completed Jobs.`}
                href={href}
                key={`${point.period_start}-${metric}`}
              >
                {value === null ? (
                  <g>
                    <rect
                      fill="var(--semantic-surface)"
                      height="178"
                      stroke="var(--semantic-warning)"
                      strokeDasharray="6 5"
                      width={Math.max(12, columnWidth - 12)}
                      x={x}
                      y="50"
                    />
                    <text
                      fill="var(--semantic-text-muted)"
                      fontSize="12"
                      textAnchor="middle"
                      x={x + Math.max(12, columnWidth - 12) / 2}
                      y="142"
                    >
                      Incomplete
                    </text>
                  </g>
                ) : (
                  <rect
                    className="transition-opacity hover:opacity-75"
                    fill="var(--semantic-action-primary)"
                    height={height}
                    rx="3"
                    width={Math.max(12, columnWidth - 12)}
                    x={x}
                    y={230 - height}
                  />
                )}
                <text
                  fill="var(--semantic-text-secondary)"
                  fontSize="11"
                  textAnchor="middle"
                  x={x + Math.max(12, columnWidth - 12) / 2}
                  y="250"
                >
                  {point.label}
                </text>
                <title>{`${point.label}: ${display}. Click to inspect the exact Job population.`}</title>
              </a>
            );
          })}
        </svg>
      </div>
      <div
        className="mt-3 flex flex-wrap gap-2"
        aria-label="Graph point drill-downs"
      >
        {points.map((point) => (
          <Link
            className="min-h-11 rounded-md border border-stroke px-3 py-2 text-xs font-semibold text-action-primary hover:bg-surface-muted"
            key={point.period_start}
            to={drilldown(point, branchId)}
          >
            {point.label}:{" "}
            {metric === "job_count"
              ? `${point.job_count} Jobs`
              : point.produced_value === null
                ? "Value unavailable"
                : displayProducedValue(Number(point.produced_value), currency)}
          </Link>
        ))}
      </div>
    </div>
  );
}
