import { RadioTower } from "lucide-react";
import { useState } from "react";

import type {
  BeaconLifecycleAction,
  BeaconLifecycleEvent,
  BeaconPriorityBand,
  BeaconSeverity,
  BeaconSignal,
  BeaconSupportingFact,
  BeaconWorkflowAction,
  BeaconWorkflowEvent,
} from "../../api/beacon";
import {
  getBeaconLifecycleHistory,
  getBeaconWorkflowHistory,
} from "../../api/beacon";
import { Alert, Badge, Button, EmptyState, Input, Spinner } from "../../ui";
import { CommandCenterPanel } from "./CommandCenterPrimitives";

const severityPresentation: Record<
  BeaconSeverity,
  { label: string; variant: "information" | "warning" | "danger" }
> = {
  information: { label: "Information", variant: "information" },
  attention: { label: "Attention", variant: "warning" },
  important: { label: "Important", variant: "warning" },
  critical: { label: "Critical", variant: "danger" },
};

const priorityPresentation: Record<
  BeaconPriorityBand,
  { label: string; variant: "information" | "warning" | "danger" | "neutral" }
> = {
  critical: { label: "Critical priority", variant: "danger" },
  immediate: { label: "Immediate priority", variant: "warning" },
  important: { label: "Important priority", variant: "information" },
  monitor: { label: "Monitor", variant: "neutral" },
};

function factValue(fact: BeaconSupportingFact): string {
  if (fact.unit === "currency_amount") {
    const value = Number(fact.value);
    if (Number.isFinite(value)) {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
      }).format(value);
    }
  }
  return `${fact.value}${fact.unit ? ` ${fact.unit.replaceAll("_", " ")}` : ""}`;
}

function sourcePath(entityType: string, entityId: string): string | null {
  if (entityType === "job") return `/jobs/${entityId}`;
  if (entityType === "invoice") return `/invoices/${entityId}`;
  if (entityType === "appointment") return `/appointments/${entityId}`;
  return null;
}

function SignalRow({
  signal,
  canReview,
  canOwn,
  canAssign,
  currentUserId,
  evaluatedAt,
  lifecyclePending,
  workflowPending,
  onLifecycleAction,
  onWorkflowAction,
}: {
  readonly signal: BeaconSignal;
  readonly canReview: boolean;
  readonly canOwn: boolean;
  readonly canAssign: boolean;
  readonly currentUserId: string | null;
  readonly evaluatedAt: string | null;
  readonly lifecyclePending: boolean;
  readonly workflowPending: boolean;
  readonly onLifecycleAction: (
    signal: BeaconSignal,
    action: BeaconLifecycleAction,
    snoozeUntil?: string,
  ) => void;
  readonly onWorkflowAction: (
    signal: BeaconSignal,
    action: BeaconWorkflowAction,
    expectedVersion?: number,
    ownerUserId?: string,
  ) => void;
}) {
  const severity = severityPresentation[signal.severity];
  const priority = priorityPresentation[signal.priority.band];
  const [snoozeUntil, setSnoozeUntil] = useState("");
  const [history, setHistory] = useState<readonly BeaconLifecycleEvent[] | null>(
    null,
  );
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState(false);
  const [workflowHistory, setWorkflowHistory] = useState<
    readonly BeaconWorkflowEvent[] | null
  >(null);
  const [ownerUserId, setOwnerUserId] = useState("");
  const workflow = signal.workflow ?? null;
  const isMine = workflow?.owner_user_id === currentUserId;
  const isExpired = evaluatedAt
    ? new Date(signal.expires_at).getTime() <= new Date(evaluatedAt).getTime()
    : false;

  const loadHistory = async () => {
    setHistoryLoading(true);
    setHistoryError(false);
    try {
      setHistory(await getBeaconLifecycleHistory(signal.condition_key));
    } catch {
      setHistoryError(true);
    } finally {
      setHistoryLoading(false);
    }
  };

  const loadWorkflowHistory = async () => {
    setHistoryLoading(true);
    setHistoryError(false);
    try {
      setWorkflowHistory(await getBeaconWorkflowHistory(signal.condition_key));
    } catch {
      setHistoryError(true);
    } finally {
      setHistoryLoading(false);
    }
  };

  return (
    <li className="border-b border-stroke py-ui-4 first:pt-0 last:border-0 last:pb-0">
      {signal.priority.rank === 1 && (
        <p className="mb-ui-2 text-overline uppercase text-accent">
          First for owner attention
        </p>
      )}
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-ui-3">
        <div className="min-w-0">
          <p className="text-overline uppercase text-content-muted">
            Priority {signal.priority.rank} · {signal.category} · {signal.source}
          </p>
          <h3 className="mt-ui-1 break-words font-semibold text-content">
            {signal.title}
          </h3>
        </div>
        <div className="flex flex-wrap gap-ui-2">
          <Badge variant={priority.variant}>{priority.label}</Badge>
          <Badge variant={severity.variant}>{severity.label} severity</Badge>
          <Badge variant="neutral">{signal.confidence.level} confidence</Badge>
          {signal.escalation && (
            <Badge
              variant={
                signal.escalation.state === "escalated" ? "danger" : "neutral"
              }
            >
              {signal.escalation.state === "escalated"
                ? "Escalated"
                : "Normal escalation"}
            </Badge>
          )}
        </div>
      </div>
      <p className="mt-ui-3 rounded-md border border-stroke bg-surface-muted p-ui-3 text-body-s text-content-secondary">
        <span className="font-semibold text-content">Why this priority:</span>{" "}
        {signal.priority.explanation}
      </p>
      {signal.evidence_quality && (
        <div className="mt-ui-3 rounded-md border border-stroke p-ui-3 text-body-s">
          <h4 className="font-semibold text-content">Evidence readiness</h4>
          <div className="mt-ui-2 flex flex-wrap gap-ui-2">
            <Badge variant="neutral">
              {signal.evidence_quality.completeness} completeness
            </Badge>
            <Badge variant="neutral">
              {signal.evidence_quality.freshness} freshness
            </Badge>
            <Badge variant="neutral">
              {signal.evidence_quality.reconciliation} reconciliation
            </Badge>
          </div>
          <p className="mt-ui-2 text-content-secondary">
            {signal.evidence_quality.explanation}
          </p>
          {signal.evidence_quality.limitations.length > 0 && (
            <ul className="mt-ui-2 list-disc pl-ui-5 text-content-muted">
              {signal.evidence_quality.limitations.map((limitation) => (
                <li key={limitation}>{limitation}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {signal.escalation && (
        <p className="mt-ui-2 text-body-s text-content-muted">
          Escalation: {signal.escalation.reason}
        </p>
      )}
      <dl className="mt-ui-3 grid gap-ui-2 text-body-s sm:grid-cols-2">
        {signal.supporting_facts.map((fact) => (
          <div className="rounded-md bg-surface-muted p-ui-3" key={fact.name}>
            <dt className="break-words text-content-muted">
              {fact.name.replaceAll("_", " ")}
            </dt>
            <dd className="mt-ui-1 break-words font-semibold text-content">
              {factValue(fact)}
            </dd>
          </div>
        ))}
      </dl>
      <details className="mt-ui-3 text-body-s">
        <summary className="cursor-pointer font-semibold text-content">
          Evidence and source drillback
        </summary>
        <ul className="mt-ui-2 space-y-ui-2">
          {signal.supporting_facts.flatMap((fact) =>
            fact.evidence.map((evidence) => {
              const path = sourcePath(evidence.entity_type, evidence.entity_id);
              return (
                <li
                  className="rounded-md border border-stroke p-ui-2 text-content-secondary"
                  key={`${fact.name}-${evidence.entity_type}-${evidence.entity_id}-${evidence.event_id ?? "record"}`}
                >
                  <span className="font-medium text-content">
                    {evidence.entity_type}
                  </span>{" "}
                  · evidence {evidence.event_type ?? "authoritative record"}
                  {evidence.occurred_at
                    ? ` · ${new Date(evidence.occurred_at).toLocaleString()}`
                    : ""}
                  {path && (
                    <a className="ml-ui-2 text-accent underline" href={path}>
                      Open source workflow
                    </a>
                  )}
                </li>
              );
            }),
          )}
        </ul>
      </details>
      <p className="mt-ui-3 text-body-s text-content-secondary">
        <span className="font-semibold text-content">Recommended action:</span>{" "}
        {signal.recommended_action}
      </p>
      <div className="mt-ui-3 rounded-md border border-stroke bg-surface-muted p-ui-3 text-body-s">
        <p className="font-semibold text-content">Operator responsibility</p>
        <p className="mt-ui-1 text-content-secondary">
          {workflow?.acknowledged_at
            ? `Acknowledged ${new Date(workflow.acknowledged_at).toLocaleString()}`
            : "Not acknowledged"}
          {workflow?.owner_user_id
            ? ` · Owner ${workflow.owner_user_id}${isMine ? " (you)" : ""}`
            : " · Unowned"}
          {isExpired ? " · Evidence expired" : ""}
        </p>
        <p className="mt-ui-1 text-content-muted">
          Acknowledgement and ownership record review responsibility only. They
          do not resolve the signal or grant authority over its source domain.
        </p>
      </div>
      {signal.lifecycle.status !== "active" && (
        <p className="mt-ui-3 text-body-s text-content-muted">
          Owner lifecycle status:{" "}
          <strong className="text-content">{signal.lifecycle.status}</strong>.
          This does not indicate operational resolution.
        </p>
      )}
      <div className="mt-ui-4 flex flex-wrap items-end gap-ui-2">
        {canReview && (
          <>
            <Button
              disabled={lifecyclePending}
              variant="outline"
              onClick={() => onLifecycleAction(signal, "review")}
            >
              Mark reviewed
            </Button>
            <label className="min-w-56 flex-1 text-body-s text-content-secondary">
              Snooze until
              <Input
                className="mt-ui-1"
                type="datetime-local"
                value={snoozeUntil}
                onChange={(event) => setSnoozeUntil(event.target.value)}
              />
            </label>
            <Button
              disabled={!snoozeUntil || lifecyclePending}
              variant="outline"
              onClick={() =>
                onLifecycleAction(
                  signal,
                  "snooze",
                  new Date(snoozeUntil).toISOString(),
                )
              }
            >
              Snooze temporarily
            </Button>
          </>
        )}
        {canReview && !workflow?.acknowledged && (
          <Button
            disabled={workflowPending || isExpired}
            variant="outline"
            onClick={() =>
              onWorkflowAction(signal, "acknowledge", undefined, undefined)
            }
          >
            Acknowledge responsibility
          </Button>
        )}
        {canOwn && !workflow?.owner_user_id && (
          <Button
            disabled={workflowPending || isExpired}
            variant="outline"
            onClick={() =>
              onWorkflowAction(
                signal,
                "claim",
                workflow?.workflow_version ?? 0,
              )
            }
          >
            Take ownership
          </Button>
        )}
        {(isMine || canAssign) && workflow?.owner_user_id && (
          <Button
            disabled={workflowPending || isExpired}
            variant="outline"
            onClick={() =>
              onWorkflowAction(
                signal,
                "release",
                workflow.workflow_version,
              )
            }
          >
            Release ownership
          </Button>
        )}
        {canAssign && (
          <>
            <label className="min-w-64 flex-1 text-body-s text-content-secondary">
              Owner user ID
              <Input
                className="mt-ui-1"
                value={ownerUserId}
                onChange={(event) => setOwnerUserId(event.target.value)}
              />
            </label>
            <Button
              disabled={!ownerUserId || workflowPending || isExpired}
              variant="outline"
              onClick={() =>
                onWorkflowAction(
                  signal,
                  workflow?.owner_user_id ? "transfer" : "assign",
                  workflow?.workflow_version ?? 0,
                  ownerUserId,
                )
              }
            >
              {workflow?.owner_user_id ? "Transfer ownership" : "Assign owner"}
            </Button>
          </>
        )}
        <Button
          disabled={historyLoading}
          variant="ghost"
          onClick={() => void loadHistory()}
        >
          View review history
        </Button>
        <Button
          disabled={historyLoading}
          variant="ghost"
          onClick={() => void loadWorkflowHistory()}
        >
          View ownership history
        </Button>
      </div>
      {historyError && (
        <p className="mt-ui-2 text-body-s text-status-danger">
          Review history is unavailable.
        </p>
      )}
      {history && (
        <div className="mt-ui-3 rounded-md border border-stroke p-ui-3">
          <h4 className="font-semibold text-content">Review history</h4>
          {history.length === 0 ? (
            <p className="mt-ui-1 text-body-s text-content-muted">
              No lifecycle actions recorded.
            </p>
          ) : (
            <ol className="mt-ui-2 space-y-ui-2">
              {history.map((event) => (
                <li className="text-body-s text-content-secondary" key={event.id}>
                  {event.action} ·{" "}
                  {new Date(event.action_at).toLocaleString()}
                  {event.snooze_until
                    ? ` · until ${new Date(event.snooze_until).toLocaleString()}`
                    : ""}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
      {workflowHistory && (
        <div className="mt-ui-3 rounded-md border border-stroke p-ui-3">
          <h4 className="font-semibold text-content">Ownership history</h4>
          {workflowHistory.length === 0 ? (
            <p className="mt-ui-1 text-body-s text-content-muted">
              No acknowledgement or ownership actions recorded.
            </p>
          ) : (
            <ol className="mt-ui-2 space-y-ui-2">
              {workflowHistory.map((event) => (
                <li className="text-body-s text-content-secondary" key={event.id}>
                  {event.action} · {new Date(event.occurred_at).toLocaleString()}
                  {event.state.owner_user_id
                    ? ` · owner ${event.state.owner_user_id}`
                    : " · unowned"}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </li>
  );
}

export function BeaconPanel({
  signals,
  snoozedSignals,
  canReview,
  canOwn,
  canAssign,
  currentUserId,
  evaluatedAt,
  loading,
  error,
  lifecycleError,
  lifecyclePending,
  workflowError,
  workflowPending,
  onLifecycleAction,
  onWorkflowAction,
  retry,
}: {
  readonly signals: readonly BeaconSignal[] | undefined;
  readonly snoozedSignals: readonly BeaconSignal[] | undefined;
  readonly canReview: boolean;
  readonly canOwn: boolean;
  readonly canAssign: boolean;
  readonly currentUserId: string | null;
  readonly evaluatedAt: string | null;
  readonly loading: boolean;
  readonly error: boolean;
  readonly lifecycleError: boolean;
  readonly lifecyclePending: boolean;
  readonly workflowError: boolean;
  readonly workflowPending: boolean;
  readonly onLifecycleAction: (
    signal: BeaconSignal,
    action: BeaconLifecycleAction,
    snoozeUntil?: string,
  ) => void;
  readonly onWorkflowAction: (
    signal: BeaconSignal,
    action: BeaconWorkflowAction,
    expectedVersion?: number,
    ownerUserId?: string,
  ) => void;
  readonly retry: () => void;
}) {
  const visibleSignals = signals ?? [];
  const acknowledgedCount = visibleSignals.filter(
    (signal) => signal.workflow?.acknowledged,
  ).length;
  const ownedCount = visibleSignals.filter(
    (signal) => signal.workflow?.owner_user_id,
  ).length;
  const evidenceAttentionCount = visibleSignals.filter(
    (signal) =>
      signal.evidence_quality &&
      (signal.evidence_quality.completeness !== "complete" ||
        signal.evidence_quality.freshness === "stale" ||
        signal.evidence_quality.reconciliation !== "reconciled"),
  ).length;
  return (
    <CommandCenterPanel
      title="Beacon"
      description="Deterministic operational signals measured from authoritative Company data."
      action={
        <div className="flex items-center gap-ui-2 text-body-s text-content-muted">
          <RadioTower aria-hidden="true" className="size-4" />
          Explainable intelligence
        </div>
      }
    >
      {loading && (
        <div className="flex min-h-32 items-center justify-center">
          <Spinner label="Evaluating Beacon signals" />
        </div>
      )}
      {error && (
        <Alert
          variant="danger"
          title="Beacon signals unavailable"
          action={
            <Button variant="outline" onClick={retry}>
              Retry
            </Button>
          }
        >
          Beacon could not read its authoritative sources. No signal state has
          been inferred.
        </Alert>
      )}
      {lifecycleError && (
        <Alert variant="danger" title="Lifecycle action not recorded">
          Beacon did not accept the requested action. The authoritative queue
          has not been changed.
        </Alert>
      )}
      {workflowError && (
        <Alert variant="danger" title="Responsibility action not recorded">
          Beacon rejected the request because it was stale, conflicted, forbidden,
          or invalid. Refresh the authoritative queue before trying again.
        </Alert>
      )}
      {!loading && !error && visibleSignals.length > 0 && (
        <dl className="mb-ui-4 grid gap-ui-2 text-body-s sm:grid-cols-4">
          <div className="rounded-md border border-stroke p-ui-3">
            <dt className="text-content-muted">Requires attention</dt>
            <dd className="mt-ui-1 text-title-m font-semibold text-content">
              {visibleSignals.length}
            </dd>
          </div>
          <div className="rounded-md border border-stroke p-ui-3">
            <dt className="text-content-muted">Acknowledged</dt>
            <dd className="mt-ui-1 text-title-m font-semibold text-content">
              {acknowledgedCount}
            </dd>
          </div>
          <div className="rounded-md border border-stroke p-ui-3">
            <dt className="text-content-muted">Owned</dt>
            <dd className="mt-ui-1 text-title-m font-semibold text-content">
              {ownedCount}
            </dd>
          </div>
          <div className="rounded-md border border-stroke p-ui-3">
            <dt className="text-content-muted">Evidence needs review</dt>
            <dd className="mt-ui-1 text-title-m font-semibold text-content">
              {evidenceAttentionCount}
            </dd>
          </div>
        </dl>
      )}
      {!loading &&
        !error &&
        signals?.length === 0 &&
        snoozedSignals?.length === 0 && (
        <EmptyState
          title="No active Beacon signals"
          description="Current authoritative records do not satisfy any configured deterministic signal rule."
        />
      )}
      {!loading && !error && signals && signals.length > 0 && (
        <ol aria-label="Owner attention queue">
          {signals.map((signal) => (
            <SignalRow
              canReview={canReview}
              canOwn={canOwn}
              canAssign={canAssign}
              currentUserId={currentUserId}
              evaluatedAt={evaluatedAt}
              key={signal.id}
              lifecyclePending={lifecyclePending}
              workflowPending={workflowPending}
              signal={signal}
              onLifecycleAction={onLifecycleAction}
              onWorkflowAction={onWorkflowAction}
            />
          ))}
        </ol>
      )}
      {!loading &&
        !error &&
        signals?.length === 0 &&
        snoozedSignals &&
        snoozedSignals.length > 0 && (
          <Alert variant="information" title="Current signals are temporarily snoozed">
            Unresolved conditions will return automatically when their snoozes
            expire or their authoritative evidence changes.
          </Alert>
        )}
      {!loading && !error && snoozedSignals && snoozedSignals.length > 0 && (
        <details className="mt-ui-4 border-t border-stroke pt-ui-4">
          <summary className="cursor-pointer font-semibold text-content">
            Temporarily snoozed ({snoozedSignals.length})
          </summary>
          <ol className="mt-ui-3" aria-label="Temporarily snoozed Beacon signals">
            {snoozedSignals.map((signal) => (
              <SignalRow
                canReview={false}
                canOwn={false}
                canAssign={false}
                currentUserId={currentUserId}
                evaluatedAt={evaluatedAt}
                key={signal.id}
                lifecyclePending={lifecyclePending}
                workflowPending={workflowPending}
                signal={signal}
                onLifecycleAction={onLifecycleAction}
                onWorkflowAction={onWorkflowAction}
              />
            ))}
          </ol>
        </details>
      )}
    </CommandCenterPanel>
  );
}
