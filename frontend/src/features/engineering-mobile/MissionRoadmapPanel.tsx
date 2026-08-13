import {
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Flag,
  LockKeyhole,
  Route,
  ShieldAlert,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { getOperatorApiError } from "../../api/errors";
import { Alert, Badge, Button, Card, EmptyState, Spinner } from "../../ui";
import { useMilestoneAction, useRoadmaps } from "./hooks";
import { milestoneDisplayStatus, mobileEngineeringLabel } from "./presentation";
import type { MilestoneAction, MilestoneItem } from "./types";

const actionLabels: Partial<Record<MilestoneAction, string>> = {
  start: "Start next milestone",
  approve: "Approve",
  reject: "Reject",
  request_revision: "Request revision",
  skip: "Skip",
  pause: "Pause",
  resume: "Resume",
  cancel: "Cancel",
  archive: "Archive",
};

function actions(item: MilestoneItem): readonly MilestoneAction[] {
  return item.attention_class === "owner_action_required"
    ? item.available_owner_actions
    : [];
}

function MilestoneCard({
  item,
  prominent = false,
}: {
  item: MilestoneItem;
  prominent?: boolean;
}) {
  const mutation = useMilestoneAction();
  const [confirming, setConfirming] = useState<MilestoneAction | null>(null);
  const apply = (action: MilestoneAction) =>
    mutation.mutate(
      { id: item.id, version: item.version, action },
      { onSuccess: () => setConfirming(null) },
    );
  const displayStatus = milestoneDisplayStatus(item);
  return (
    <article
      className={`rounded-2xl border p-ui-4 ${prominent ? "border-blue-400/50 bg-blue-400/5" : "border-stroke bg-surface"}`}
    >
      <div className="flex items-start justify-between gap-ui-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-content-muted">
            {item.milestone_code ?? `Milestone ${item.position}`}
          </p>
          <h3 className="mt-1 text-lg font-bold leading-6">{item.title}</h3>
        </div>
        <Badge>{displayStatus}</Badge>
      </div>
      <p className="mt-ui-3 text-sm leading-6 text-content-muted">
        {item.objective}
      </p>
      <p className="mt-ui-2 text-xs font-medium text-content-muted">
        {item.owning_workstream} · {item.owning_branch}
        {item.permanent_capacity_identity
          ? ` · ${item.permanent_capacity_identity}`
          : ""}
      </p>
      <p className="mt-1 text-xs font-medium text-content-muted">
        {mobileEngineeringLabel(item.readiness_state ?? item.status)} · Reconciliation: {mobileEngineeringLabel(item.reconciliation_state ?? "legacy_unreconciled")}
      </p>
      <p className="mt-ui-2 text-sm font-medium text-content-muted">
        {item.attention_reason}
      </p>
      {item.attention_class === "waiting_on_capacity" && (
        <dl className="mt-ui-3 grid grid-cols-2 gap-ui-2 rounded-xl border border-violet-400/30 bg-violet-400/10 p-ui-3 text-xs text-content-muted">
          <div>
            <dt>Queue position</dt>
            <dd className="font-semibold text-content">
              {item.queue_position ?? "Pending"}
            </dd>
          </div>
          <div>
            <dt>Estimated start</dt>
            <dd className="font-semibold text-content">
              {item.estimated_start_at
                ? new Date(item.estimated_start_at).toLocaleString()
                : "Not yet available"}
            </dd>
          </div>
          <div className="col-span-2">
            <dt>Worker capacity</dt>
            <dd className="font-semibold text-content">
              {item.worker_capacity_summary ?? "Capacity unavailable"}
            </dd>
          </div>
        </dl>
      )}
      {!item.requested_code_changes && (
        <p className="mt-ui-2 text-xs font-semibold text-emerald-400">
          Read-only · repository changes prohibited
        </p>
      )}
      {item.status === "externally_running" && item.external_evidence && (
        <p className="mt-ui-2 rounded-xl border border-violet-400/30 bg-violet-400/10 p-ui-3 text-sm text-content-muted">
          Already underway outside Mission Control · {item.external_evidence}
        </p>
      )}
      {item.external_adoption && (
        <div className="mt-ui-3 rounded-xl border border-violet-400/30 bg-violet-400/10 p-ui-3 text-sm">
          <div className="flex items-center justify-between gap-ui-2">
            <span className="font-semibold">External work</span>
            <Badge>{mobileEngineeringLabel(item.external_adoption.status)}</Badge>
          </div>
          <p className="mt-ui-2 text-content-muted">
            {item.external_adoption.current_activity ??
              "Waiting for authenticated start evidence"}
          </p>
          {item.external_adoption.evidence_stale && (
            <p className="mt-ui-2 font-semibold text-amber-300">
              External evidence is stale. Worker availability is unaffected.
            </p>
          )}
          {item.external_adoption.blockers.length > 0 && (
            <p className="mt-ui-2 text-amber-300">
              Blocked: {item.external_adoption.blockers.join(" · ")}
            </p>
          )}
          <dl className="mt-ui-2 grid grid-cols-2 gap-ui-2 text-xs text-content-muted">
            <div>
              <dt>Progress</dt>
              <dd className="font-semibold text-content">
                {item.external_adoption.progress_percent}%
              </dd>
            </div>
            <div>
              <dt>Mission Control dispatched</dt>
              <dd className="font-semibold text-content">No</dd>
            </div>
            <div className="col-span-2">
              <dt>Source branch</dt>
              <dd className="break-all font-mono text-content">
                {item.external_adoption.branch}
              </dd>
            </div>
            <div className="col-span-2">
              <dt>Current HEAD</dt>
              <dd className="break-all font-mono text-content">
                {item.external_adoption.current_head.slice(0, 12)}
              </dd>
            </div>
            <div className="col-span-2">
              <dt>Last evidence</dt>
              <dd className="font-semibold text-content">
                {item.external_adoption.last_evidence_at
                  ? new Date(
                      item.external_adoption.last_evidence_at,
                    ).toLocaleString()
                  : "No authenticated evidence yet"}
              </dd>
            </div>
          </dl>
        </div>
      )}
      {item.command_id && (
        <Link
          to={`/engineering/${item.command_id}`}
          className="mt-ui-3 inline-flex min-h-11 items-center gap-ui-1 text-sm font-semibold text-blue-400"
        >
          View live work <ChevronRight size={18} />
        </Link>
      )}
      {mutation.isError && (
        <Alert className="mt-ui-3" variant="danger" title="Action not accepted">
          {getOperatorApiError(mutation.error, "Milestone action").message}
        </Alert>
      )}
      <div className="mt-ui-4 flex flex-wrap gap-ui-2">
        {actions(item).map((action) => (
          <Button
            key={action}
            className="min-h-11 flex-1 sm:flex-none"
            variant={
              ["reject", "cancel"].includes(action)
                ? "destructive"
                : action === "start" ||
                    action === "approve" ||
                    action === "resume"
                  ? "primary"
                  : "outline"
            }
            disabled={mutation.isPending}
            onClick={() =>
              ["start", "approve", "resume", "pause"].includes(action)
                ? apply(action)
                : setConfirming(action)
            }
          >
            {actionLabels[action]}
          </Button>
        ))}
      </div>
      {confirming && (
        <div className="mt-ui-3 rounded-xl border border-amber-400/40 bg-amber-400/10 p-ui-3">
          <p className="text-sm font-semibold">
            {actionLabels[confirming]} this milestone?
          </p>
          <div className="mt-ui-2 flex gap-ui-2">
            <Button
              className="min-h-11"
              variant={
                confirming === "reject" || confirming === "cancel"
                  ? "destructive"
                  : "primary"
              }
              onClick={() => apply(confirming)}
            >
              Confirm
            </Button>
            <Button
              className="min-h-11"
              variant="outline"
              onClick={() => setConfirming(null)}
            >
              Keep it
            </Button>
          </div>
        </div>
      )}
    </article>
  );
}

export function MissionRoadmapPanel() {
  const query = useRoadmaps();
  if (query.isLoading)
    return (
      <div className="flex min-h-48 items-center justify-center">
        <Spinner label="Loading engineering roadmaps" />
      </div>
    );
  if (query.isError || !query.data) {
    const error = getOperatorApiError(query.error, "Engineering roadmaps");
    return (
      <Alert variant="danger" title={error.title}>
        {error.message}
      </Alert>
    );
  }
  const data = query.data;
  const sections = [
    {
      title: "Running",
      icon: CircleDot,
      color: "text-blue-400",
      items: data.running_milestones,
    },
    {
      title: "Waiting on Dependencies",
      icon: LockKeyhole,
      color: "text-amber-400",
      items: data.dependency_waiting_milestones,
    },
    {
      title: "Waiting on Capacity",
      icon: Route,
      color: "text-violet-400",
      items: data.capacity_waiting_milestones,
    },
    {
      title: "External Work",
      icon: Route,
      color: "text-violet-400",
      items: data.external_work_milestones,
    },
    {
      title: "Completed Recently",
      icon: CheckCircle2,
      color: "text-emerald-400",
      items: data.completed_recently,
    },
  ] as const;
  return (
    <section className="space-y-ui-5">
      <header>
        <p className="text-sm font-semibold text-blue-400">
          Owner-controlled dispatch
        </p>
        <h2 className="mt-1 text-2xl font-bold">Engineering roadmap</h2>
        <p className="mt-1 text-sm leading-6 text-content-muted">
          Approve and dispatch durable milestones directly. Mission Control
          sends the complete definition to the worker.
        </p>
      </header>
      {data.projection_warnings?.map((warning) => (
        <Alert
          key={warning}
          variant="warning"
          title="Some roadmap data needs attention"
        >
          {warning}
        </Alert>
      ))}
      <Card className="p-ui-4">
        <div className="flex items-center justify-between gap-ui-3">
          <div className="flex items-center gap-ui-2">
            <ShieldAlert
              className={
                data.actionable_count ? "text-amber-400" : "text-emerald-400"
              }
            />
            <h3 className="font-bold">Owner Attention</h3>
          </div>
          <Badge>{data.actionable_count}</Badge>
        </div>
        {data.actionable_count === 0 ? (
          <p className="mt-ui-3 text-sm text-content-muted">
            Nothing currently requires your attention.
          </p>
        ) : (
          <div className="mt-ui-4 grid gap-ui-3">
            {data.owner_attention.map((item) => (
              <MilestoneCard key={item.id} item={item} prominent />
            ))}
          </div>
        )}
      </Card>
      {data.roadmaps.length === 0 && (
        <EmptyState
          title="No engineering roadmap"
          description="No approved milestone library exists in this Company scope."
        />
      )}
      {sections.map(({ title, icon: Icon, color, items }) => (
        <details
          key={title}
          className="rounded-2xl border border-stroke bg-surface p-ui-4"
          open={title === "Running" && items.length > 0}
        >
          <summary className="flex min-h-11 cursor-pointer items-center gap-ui-2 font-bold">
            <Icon className={color} size={20} />
            <span className="flex-1">{title}</span>
            <Badge>{items.length}</Badge>
          </summary>
          {items.length ? (
            <div className="mt-ui-3 grid gap-ui-3">
              {items.map((item) => (
                <MilestoneCard key={item.id} item={item} />
              ))}
            </div>
          ) : (
            <p className="mt-ui-3 text-sm text-content-muted">None currently.</p>
          )}
        </details>
      ))}
      <Card className="p-ui-4">
        <div className="flex items-center gap-ui-2">
          <Flag className="text-blue-400" />
          <h3 className="font-bold">Dispatch guarantee</h3>
        </div>
        <p className="mt-ui-2 text-sm leading-6 text-content-muted">
          Roadmap progression only promotes an approved milestone to Ready.
          Execution begins only when you explicitly tap Start next milestone.
        </p>
      </Card>
    </section>
  );
}
