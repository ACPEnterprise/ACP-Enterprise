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
import { mobileEngineeringLabel } from "./presentation";
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
  if (item.status === "ready") return ["start", "skip"];
  if (item.status === "waiting_review")
    return ["approve", "request_revision", "reject"];
  if (item.status === "waiting_approval") return ["approve", "reject", "skip"];
  if (item.status === "blocked") return ["request_revision", "skip", "archive"];
  if (item.status === "running") return ["pause", "cancel"];
  if (item.status === "paused") return ["resume", "cancel"];
  if (["completed", "cancelled", "skipped"].includes(item.status))
    return ["archive"];
  return [];
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
  return (
    <article
      className={`rounded-2xl border p-ui-4 ${prominent ? "border-blue-400/50 bg-blue-400/5" : "border-stroke bg-surface"}`}
    >
      <div className="flex items-start justify-between gap-ui-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-content-muted">
            Milestone {item.position}
          </p>
          <h3 className="mt-1 text-lg font-bold leading-6">{item.title}</h3>
        </div>
        <Badge>{mobileEngineeringLabel(item.status)}</Badge>
      </div>
      <p className="mt-ui-3 text-sm leading-6 text-content-muted">
        {item.objective}
      </p>
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
  const current = data.current_milestones.filter(
    (item) => item.status !== "ready" && item.status !== "waiting_review",
  );
  const future = [
    ...data.next_approved_milestones,
    ...data.future_milestones,
  ];
  const completed = data.completed_milestones;
  const blocked = data.blocked_milestones;
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
      <Card className="p-ui-4">
        <div className="flex items-center justify-between gap-ui-3">
          <div className="flex items-center gap-ui-2">
            <ShieldAlert
              className={
                data.actionable_count ? "text-amber-400" : "text-emerald-400"
              }
            />
            <h3 className="font-bold">Waiting for me</h3>
          </div>
          <Badge>{data.actionable_count}</Badge>
        </div>
        {data.actionable_count === 0 ? (
          <p className="mt-ui-3 text-sm text-content-muted">
            Nothing currently requires your attention.
          </p>
        ) : (
          <div className="mt-ui-4 grid gap-ui-3">
            {data.waiting_for_me.map((item) => (
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
      {current.length > 0 && (
        <div>
          <div className="mb-ui-3 flex items-center gap-ui-2">
            <CircleDot className="text-blue-400" size={20} />
            <h3 className="font-bold">Current milestone</h3>
          </div>
          <div className="grid gap-ui-3">
            {current.map((item) => (
              <MilestoneCard key={item.id} item={item} />
            ))}
          </div>
        </div>
      )}
      {future.length > 0 && (
        <div>
          <div className="mb-ui-3 flex items-center gap-ui-2">
            <Route className="text-violet-400" size={20} />
            <h3 className="font-bold">Next and future milestones</h3>
          </div>
          <div className="grid gap-ui-3">
            {future.map((item) => (
              <MilestoneCard key={item.id} item={item} />
            ))}
          </div>
        </div>
      )}
      {blocked.length > 0 && (
        <div>
          <div className="mb-ui-3 flex items-center gap-ui-2">
            <LockKeyhole className="text-rose-400" size={20} />
            <h3 className="font-bold">Blocked milestones</h3>
          </div>
          <div className="grid gap-ui-3">
            {blocked.map((item) => (
              <MilestoneCard key={item.id} item={item} />
            ))}
          </div>
        </div>
      )}
      {completed.length > 0 && (
        <details className="rounded-2xl border border-stroke bg-surface p-ui-4">
          <summary className="flex min-h-11 cursor-pointer items-center gap-ui-2 font-bold">
            <CheckCircle2 className="text-emerald-400" size={20} />
            Completed milestones · {completed.length}
          </summary>
          <div className="mt-ui-3 grid gap-ui-3">
            {completed.map((item) => (
              <MilestoneCard key={item.id} item={item} />
            ))}
          </div>
        </details>
      )}
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
