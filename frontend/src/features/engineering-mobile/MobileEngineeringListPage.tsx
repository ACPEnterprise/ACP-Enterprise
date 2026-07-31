import {
  Activity,
  CheckCircle2,
  ChevronRight,
  Clock3,
  HeartPulse,
  Inbox,
  Rocket,
  Route,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";

import { getOperatorApiError } from "../../api/errors";
import { Alert, Badge, Button, Card, EmptyState, Spinner } from "../../ui";
import {
  useAcknowledgeMissionNotification,
  useMissionNotifications,
  useMobileWorkstreams,
  usePendingMobileReviews,
  useRoadmaps,
  useTransitionMissionNotification,
} from "./hooks";
import {
  mobileEngineeringLabel,
  mobileEngineeringRelativeTime,
  mobileEngineeringTimestamp,
  workstreamDisplayName,
} from "./presentation";
import { useEngineeringRealtime } from "./realtime";
import { MissionRoadmapPanel } from "./MissionRoadmapPanel";
import type { MissionNotificationItem, MobileWorkstreamSummary } from "./types";

type View = "overview" | "roadmap" | "inbox" | "briefing" | "analytics";
type InboxFilter =
  "all" | "attention" | "failures" | "recovering" | "completed";

const terminal = new Set(["completed", "failed", "cancelled"]);
const today = new Date().toDateString();
const isToday = (value: string) => new Date(value).toDateString() === today;

function average(
  items: readonly MobileWorkstreamSummary[],
  field: keyof MobileWorkstreamSummary,
): string {
  const values = items
    .map((item) => item[field])
    .filter((value): value is number => typeof value === "number");
  if (!values.length) return "—";
  const milliseconds =
    values.reduce((sum, value) => sum + value, 0) / values.length;
  return milliseconds < 60_000
    ? `${(milliseconds / 1000).toFixed(1)}s`
    : `${(milliseconds / 60_000).toFixed(1)}m`;
}

function Metric({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string | number;
  tone?: "default" | "attention" | "success";
}) {
  return (
    <Card
      className={`min-h-28 p-ui-4 ${tone === "attention" ? "border-amber-400/50" : tone === "success" ? "border-emerald-400/40" : ""}`}
    >
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-content-muted">
        {label}
      </p>
      <p className="mt-ui-2 text-3xl font-bold tracking-tight">{value}</p>
    </Card>
  );
}

function WorkstreamCard({ item }: { item: MobileWorkstreamSummary }) {
  return (
    <Link
      to={`/engineering/${item.command_id}`}
      className="group block rounded-2xl border border-stroke bg-surface p-ui-4 transition hover:border-blue-400/60 hover:bg-surface-muted"
    >
      <div className="flex items-start justify-between gap-ui-3">
        <div className="min-w-0">
          <p className="line-clamp-2 text-base font-bold leading-6">
            {workstreamDisplayName(item.display_name, item.ecid)}
          </p>
          <p className="mt-1 truncate text-xs font-medium uppercase tracking-wide text-content-muted">
            {item.ecid} · {item.repository_key}
          </p>
        </div>
        <ChevronRight
          className="mt-1 shrink-0 text-content-muted transition group-hover:translate-x-0.5"
          size={20}
        />
      </div>
      <div className="mt-ui-3 flex flex-wrap gap-ui-2">
        <Badge>{mobileEngineeringLabel(item.pipeline_status)}</Badge>
        {item.owner_attention_required && <Badge>Needs you</Badge>}
      </div>
      <p className="mt-ui-3 text-sm leading-6">
        {item.current_activity ?? item.progress_summary}
      </p>
      {item.progress_percent != null && (
        <div
          className="mt-ui-3 h-2 overflow-hidden rounded-full bg-surface-muted"
          aria-label={`${item.progress_percent}% complete`}
        >
          <div
            className="h-full rounded-full bg-blue-400"
            style={{ width: `${item.progress_percent}%` }}
          />
        </div>
      )}
    </Link>
  );
}

function NotificationRow({
  item,
  workstreamName,
}: {
  item: MissionNotificationItem;
  workstreamName: string;
}) {
  const acknowledge = useAcknowledgeMissionNotification();
  const transition = useTransitionMissionNotification();
  return (
    <li
      className={`rounded-2xl border p-ui-4 ${item.status === "unread" ? "border-blue-400/50 bg-blue-400/5" : "border-stroke bg-surface"}`}
    >
      <div className="flex items-start justify-between gap-ui-3">
        <div className="min-w-0">
          <Link
            to={`/engineering/${item.command_id}`}
            className="font-bold hover:text-blue-400"
          >
            {mobileEngineeringLabel(item.kind)}
          </Link>
          <p className="mt-1 truncate text-sm text-content-muted">
            {workstreamName}
          </p>
        </div>
        <Badge>
          {item.escalated_at
            ? "Escalated"
            : mobileEngineeringLabel(item.severity)}
        </Badge>
      </div>
      <p className="mt-ui-1 text-sm text-content-muted">
        {mobileEngineeringTimestamp(item.created_at)}
      </p>
      <div className="mt-ui-3 flex flex-wrap gap-ui-2">
        {item.status === "unread" && (
          <Button
            className="min-h-11"
            variant="outline"
            disabled={transition.isPending}
            onClick={() =>
              transition.mutate({
                id: item.id,
                version: item.version,
                action: "read",
              })
            }
          >
            Mark read
          </Button>
        )}
        {item.status !== "acknowledged" && item.status !== "archived" && (
          <Button
            className="min-h-11"
            disabled={acknowledge.isPending}
            onClick={() =>
              acknowledge.mutate({ id: item.id, version: item.version })
            }
          >
            Acknowledge
          </Button>
        )}
        {item.status !== "archived" && (
          <Button
            className="min-h-11"
            variant="outline"
            disabled={transition.isPending}
            onClick={() =>
              transition.mutate({
                id: item.id,
                version: item.version,
                action: "archive",
              })
            }
          >
            Archive
          </Button>
        )}
      </div>
    </li>
  );
}

export function MobileEngineeringListPage() {
  const [view, setView] = useState<View>("overview");
  const [filter, setFilter] = useState<InboxFilter>("all");
  const [observedAt] = useState(() => Date.now());
  const workstreams = useMobileWorkstreams({ page: 1, pageSize: 100 });
  const notifications = useMissionNotifications();
  const approvals = usePendingMobileReviews();
  const roadmaps = useRoadmaps();
  const realtime = useEngineeringRealtime();
  const items = useMemo(
    () => workstreams.data?.items ?? [],
    [workstreams.data?.items],
  );
  const counts = useMemo(
    () => ({
      active: items.filter((item) => !terminal.has(item.pipeline_status))
        .length,
      waiting: roadmaps.data?.actionable_count ?? 0,
      running: items.filter((item) =>
        ["acknowledged", "running", "validating", "deploying_preview"].includes(
          item.pipeline_status,
        ),
      ).length,
      completed: items.filter(
        (item) =>
          item.pipeline_status === "completed" && isToday(item.updated_at),
      ).length,
      failed: items.filter(
        (item) => item.pipeline_status === "failed" && isToday(item.updated_at),
      ).length,
    }),
    [items, roadmaps.data?.actionable_count],
  );
  const filteredNotifications = (notifications.data?.items ?? []).filter(
    (item) => {
      if (item.status === "archived") return false;
      if (filter === "attention") return item.kind === "waiting_for_owner";
      if (filter === "failures") return item.kind.includes("failed");
      if (filter === "recovering")
        return [
          "recovering",
          "heartbeat_expired",
          "worker_disconnected",
        ].includes(item.kind);
      if (filter === "completed") return item.kind.includes("completed");
      return true;
    },
  );
  const workstreamNames = new Map(
    items.map((item) => [
      item.command_id,
      workstreamDisplayName(item.display_name, item.ecid),
    ]),
  );
  const heartbeatAt = workstreams.data?.connectivity.heartbeat_at ?? null;
  const heartbeatAge = heartbeatAt
    ? Math.max(0, observedAt - new Date(heartbeatAt).getTime())
    : null;
  const workerState =
    workstreams.data?.connectivity.state === "connected" &&
    heartbeatAge != null &&
    heartbeatAge < 90_000
      ? {
          label: "Healthy and ready",
          detail: "Authenticated and responding",
          color: "bg-emerald-400",
          tone: "text-emerald-400",
        }
      : workstreams.data?.connectivity.state === "connecting" ||
          (heartbeatAge != null && heartbeatAge < 300_000)
        ? {
            label: "Reconnecting",
            detail: "Work is paused while the connection recovers",
            color: "bg-amber-400",
            tone: "text-amber-400",
          }
        : {
            label: "Unavailable",
            detail: "No fresh authenticated worker signal",
            color: "bg-rose-400",
            tone: "text-rose-400",
          };

  if (workstreams.isLoading)
    return (
      <div className="flex min-h-64 items-center justify-center">
        <Spinner label="Opening Mission Control" />
      </div>
    );
  if (workstreams.isError) {
    const error = getOperatorApiError(workstreams.error, "Mission Control");
    return (
      <Alert variant="danger" announcement="assertive" title={error.title}>
        {error.message}
      </Alert>
    );
  }

  return (
    <div className="mx-auto w-full max-w-6xl space-y-ui-5 overflow-x-hidden pb-12">
      <header className="rounded-3xl border border-blue-400/20 bg-gradient-to-br from-blue-500/15 via-surface to-violet-500/10 p-ui-5 sm:p-ui-6">
        <div className="flex flex-wrap items-center justify-between gap-ui-3">
          <div>
            <p className="text-sm font-semibold text-blue-400">
              Engineering Mission Control
            </p>
            <h1 className="mt-1 text-3xl font-bold tracking-tight sm:text-4xl">
              Good{" "}
              {new Date().getHours() < 12
                ? "morning"
                : new Date().getHours() < 18
                  ? "afternoon"
                  : "evening"}
              .
            </h1>
          </div>
          <Badge>Live · {realtime}</Badge>
        </div>
        <p className="mt-ui-3 max-w-2xl text-base leading-7 text-content-muted">
          {counts.waiting
            ? `${counts.waiting} item${counts.waiting === 1 ? " needs" : "s need"} your attention.`
            : "Engineering is moving without anything waiting on you."}{" "}
          {counts.running
            ? `${counts.running} workstream${counts.running === 1 ? " is" : "s are"} in progress.`
            : "The worker is ready for its next assignment."}
        </p>
      </header>

      <nav
        className="grid grid-cols-5 gap-1 rounded-2xl border border-stroke bg-surface p-1"
        aria-label="Mission Control views"
      >
        {(
          [
            ["overview", Activity, "Overview"],
            ["roadmap", Route, "Roadmap"],
            ["inbox", Inbox, "Inbox"],
            ["briefing", Sparkles, "Briefing"],
            ["analytics", HeartPulse, "Analytics"],
          ] as const
        ).map(([id, Icon, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setView(id)}
            aria-current={view === id ? "page" : undefined}
            className={`flex min-h-14 flex-col items-center justify-center gap-1 rounded-xl px-1 text-xs font-semibold sm:flex-row sm:text-sm ${view === id ? "bg-blue-500 text-white" : "text-content-muted hover:bg-surface-muted"}`}
          >
            <Icon size={18} />
            {label}
          </button>
        ))}
      </nav>

      {view === "roadmap" && <MissionRoadmapPanel />}

      {view === "overview" && (
        <>
          <section
            className="grid grid-cols-2 gap-ui-3 lg:grid-cols-5"
            aria-label="Mission summary"
          >
            <Metric label="Active" value={counts.active} />
            <Metric
              label="Waiting for you"
              value={counts.waiting}
              tone={counts.waiting ? "attention" : "default"}
            />
            <Metric label="Running" value={counts.running} />
            <Metric
              label="Completed today"
              value={counts.completed}
              tone="success"
            />
            <Metric
              label="Failed today"
              value={counts.failed}
              tone={counts.failed ? "attention" : "default"}
            />
          </section>
          <section className="grid gap-ui-4 lg:grid-cols-3">
            <Card className="p-ui-4 lg:col-span-2">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-bold">Current activity</h2>
                <Activity size={20} className="text-blue-400" />
              </div>
              <div className="mt-ui-4 grid gap-ui-3 sm:grid-cols-2">
                {items
                  .filter((item) => !terminal.has(item.pipeline_status))
                  .slice(0, 4)
                  .map((item) => (
                    <WorkstreamCard key={item.command_id} item={item} />
                  ))}
                {!counts.active && (
                  <p className="text-sm text-content-muted">
                    No workstreams are active right now.
                  </p>
                )}
              </div>
            </Card>
            <div className="space-y-ui-4">
              <Card className="overflow-hidden p-0">
                <div className="p-ui-4">
                  <div className="flex items-center justify-between">
                    <h2 className="font-bold">Worker</h2>
                    <span
                      className={`h-3 w-3 rounded-full ${workerState.color} shadow-[0_0_12px_currentColor]`}
                      aria-hidden="true"
                    />
                  </div>
                  <p
                    className={`mt-ui-3 text-xl font-bold ${workerState.tone}`}
                  >
                    {workerState.label}
                  </p>
                  <p className="mt-1 text-sm text-content-muted">
                    {workerState.detail}
                  </p>
                </div>
                <div className="border-t border-stroke bg-surface-muted/40 px-ui-4 py-ui-3 text-sm">
                  <span className="text-content-muted">Last checked </span>
                  <strong>
                    {mobileEngineeringRelativeTime(heartbeatAt, observedAt)}
                  </strong>
                </div>
              </Card>
              <Card className="p-ui-4">
                <h2 className="font-bold">Preview health</h2>
                <div className="mt-ui-3 flex items-center gap-ui-3">
                  <Rocket className="text-blue-400" size={22} />
                  <span className="font-semibold">
                    {items.some(
                      (item) =>
                        item.pipeline_status === "failed" &&
                        item.failure_classification?.includes("deploy"),
                    )
                      ? "Review needed"
                      : "No deployment issues"}
                  </span>
                </div>
                <p className="mt-ui-2 text-sm text-content-muted">
                  Recent deployments:{" "}
                  {
                    items.filter(
                      (item) =>
                        item.repository_operation_status === "completed",
                    ).length
                  }
                </p>
              </Card>
            </div>
          </section>
        </>
      )}

      {view === "inbox" && (
        <section className="space-y-ui-4">
          <div className="flex items-start justify-between gap-ui-3">
            <div>
              <h2 className="text-2xl font-bold">Approval inbox</h2>
              <p className="mt-1 text-sm text-content-muted">
                Decisions, recovery, and completed work in one place.
              </p>
            </div>
            {notifications.data && (
              <Badge>{notifications.data.unread_count} new</Badge>
            )}
          </div>
          <div className="flex gap-ui-2 overflow-x-auto pb-1">
            {(
              [
                "all",
                "attention",
                "failures",
                "recovering",
                "completed",
              ] as const
            ).map((value) => {
              const count =
                value === "all"
                  ? (notifications.data?.items.filter(
                      (item) => item.status !== "archived",
                    ).length ?? 0)
                  : (notifications.data?.items.filter((item) =>
                      value === "attention"
                        ? item.kind === "waiting_for_owner"
                        : value === "failures"
                          ? item.kind.includes("failed")
                          : value === "recovering"
                            ? [
                                "recovering",
                                "heartbeat_expired",
                                "worker_disconnected",
                              ].includes(item.kind)
                            : item.kind.includes("completed"),
                    ).length ?? 0);
              return (
                <Button
                  key={value}
                  className="min-h-11 shrink-0"
                  variant={filter === value ? "primary" : "outline"}
                  onClick={() => setFilter(value)}
                >
                  {mobileEngineeringLabel(value)} · {count}
                </Button>
              );
            })}
          </div>
          {approvals.data && approvals.data.items.length > 0 && (
            <Card className="p-ui-4">
              <div className="flex items-center gap-ui-2">
                <ShieldAlert className="text-amber-400" />
                <h3 className="font-bold">Waiting for approval</h3>
                <Badge>{approvals.data.total_count}</Badge>
              </div>
              <ol className="mt-ui-3 space-y-ui-3">
                {approvals.data.items.map((item) => (
                  <li
                    key={item.id}
                    className="rounded-xl border border-stroke p-ui-4"
                  >
                    <Link
                      className="font-bold text-blue-400"
                      to={`/engineering/${item.id}`}
                    >
                      {workstreamNames.get(item.id) ?? item.ecid}
                    </Link>
                    <p className="mt-1 text-sm text-content-muted">
                      {item.ecid} · expires{" "}
                      {mobileEngineeringTimestamp(item.expires_at)}
                    </p>
                    <Link
                      className="mt-ui-3 inline-flex min-h-11 items-center rounded-lg bg-blue-500 px-ui-4 text-sm font-semibold text-white"
                      to={`/engineering/${item.id}`}
                    >
                      Review decision
                    </Link>
                  </li>
                ))}
              </ol>
            </Card>
          )}
          <ol className="space-y-ui-3">
            {filteredNotifications.map((item) => (
              <NotificationRow
                key={item.id}
                item={item}
                workstreamName={
                  workstreamNames.get(item.command_id) ??
                  "Engineering workstream"
                }
              />
            ))}
          </ol>
          {filteredNotifications.length === 0 &&
            !approvals.data?.items.length && (
              <EmptyState
                title="Inbox clear"
                description="Nothing in this group needs your attention."
              />
            )}
        </section>
      )}

      {view === "briefing" && (
        <section className="space-y-ui-4">
          <div>
            <h2 className="text-2xl font-bold">Daily briefing</h2>
            <p className="mt-1 text-sm text-content-muted">
              A concise readout of engineering since your last check-in.
            </p>
          </div>
          <Card className="p-ui-5">
            <div className="flex items-center gap-ui-3">
              <Sparkles className="text-violet-400" />
              <h3 className="text-xl font-bold">Executive summary</h3>
            </div>
            <ul className="mt-ui-4 space-y-ui-4 text-base leading-7">
              <li className="flex gap-ui-3">
                <CheckCircle2
                  className="mt-1 shrink-0 text-emerald-400"
                  size={20}
                />
                <span>
                  <strong>{counts.completed} completed today.</strong>{" "}
                  {
                    items.filter((item) => item.pipeline_status === "completed")
                      .length
                  }{" "}
                  milestones are complete in the current view.
                </span>
              </li>
              <li className="flex gap-ui-3">
                <Inbox className="mt-1 shrink-0 text-amber-400" size={20} />
                <span>
                  <strong>{counts.waiting} waiting for you.</strong> Open the
                  Inbox to review or acknowledge them.
                </span>
              </li>
              <li className="flex gap-ui-3">
                <HeartPulse className="mt-1 shrink-0 text-blue-400" size={20} />
                <span>
                  <strong>
                    Worker{" "}
                    {workstreams.data?.connectivity.state === "connected"
                      ? "is healthy"
                      : "needs attention"}
                    .
                  </strong>{" "}
                  Last authenticated signal{" "}
                  {mobileEngineeringTimestamp(
                    workstreams.data?.connectivity.heartbeat_at ?? null,
                  )}
                  .
                </span>
              </li>
              <li className="flex gap-ui-3">
                <Rocket className="mt-1 shrink-0 text-violet-400" size={20} />
                <span>
                  <strong>
                    {
                      items.filter(
                        (item) =>
                          item.repository_operation_status === "completed",
                      ).length
                    }{" "}
                    recent deliveries.
                  </strong>{" "}
                  {counts.failed
                    ? "Review failures before starting more work."
                    : "No failed delivery needs escalation."}
                </span>
              </li>
            </ul>
          </Card>
          <Alert
            variant={counts.failed ? "warning" : "information"}
            title="Recommendation"
          >
            {counts.failed
              ? "Review failed work first, then clear owner approvals in priority order."
              : counts.waiting
                ? "Clear the approval inbox so active engineering can continue."
                : "No owner action is required. Keep the worker available for the next priority."}
          </Alert>
        </section>
      )}

      {view === "analytics" && (
        <section className="space-y-ui-4">
          <div>
            <h2 className="text-2xl font-bold">Engineering analytics</h2>
            <p className="mt-1 text-sm text-content-muted">
              Delivery pace and reliability from authoritative runtime evidence.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-ui-3 lg:grid-cols-4">
            <Metric
              label="Avg. execution"
              value={average(items, "execution_latency_ms")}
            />
            <Metric
              label="Avg. validation"
              value={average(items, "validation_latency_ms")}
            />
            <Metric
              label="Approval latency"
              value={average(items, "acknowledgement_latency_ms")}
            />
            <Metric
              label="Worker uptime"
              value={
                items.length
                  ? `${Math.round(Math.max(...items.map((item) => item.worker_uptime_seconds ?? 0)) / 3600)}h`
                  : "—"
              }
            />
            <Metric
              label="Completed milestones"
              value={
                items.filter((item) => item.pipeline_status === "completed")
                  .length
              }
              tone="success"
            />
            <Metric
              label="Failure rate"
              value={
                items.length
                  ? `${Math.round((items.filter((item) => item.pipeline_status === "failed").length / items.length) * 100)}%`
                  : "—"
              }
            />
            <Metric
              label="Deployment success"
              value={
                items.some((item) => item.repository_operation_status)
                  ? `${Math.round((items.filter((item) => item.repository_operation_status === "completed").length / items.filter((item) => item.repository_operation_status).length) * 100)}%`
                  : "—"
              }
            />
            <Metric
              label="Reconnects"
              value={items.reduce((sum, item) => sum + item.reconnect_count, 0)}
            />
          </div>
          <Card className="p-ui-4">
            <div className="flex items-center gap-ui-2">
              <Clock3 className="text-blue-400" />
              <h3 className="font-bold">What these numbers mean</h3>
            </div>
            <p className="mt-ui-3 text-sm leading-6 text-content-muted">
              Metrics come from persisted execution events, validation evidence,
              deployments, and authenticated worker signals. Missing evidence is
              shown as an em dash, never estimated.
            </p>
          </Card>
        </section>
      )}
    </div>
  );
}
