import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { getOperatorApiError } from "../../api/errors";
import { Alert, Badge, Button, EmptyState, Spinner } from "../../ui";
import {
  useAcknowledgeMissionNotification,
  useMissionNotifications,
  useMobileWorkstreams,
  usePendingMobileReviews,
} from "./hooks";
import { useEngineeringRealtime } from "./realtime";
import {
  mobileEngineeringLabel,
  mobileEngineeringTimestamp,
} from "./presentation";

export function MobileEngineeringListPage() {
  const [page, setPage] = useState(1);
  const query = useMobileWorkstreams({ page, pageSize: 10 });
  const notifications = useMissionNotifications();
  const acknowledge = useAcknowledgeMissionNotification();
  const approvalQueue = usePendingMobileReviews();
  const realtime = useEngineeringRealtime();

  return (
    <div className="mx-auto w-full max-w-5xl space-y-ui-5 overflow-x-hidden">
      <header>
        <p className="text-sm font-semibold text-blue-400">
          Engineering Control
        </p>
        <h1 className="mt-ui-1 text-2xl font-bold sm:text-3xl">
          Engineering workstreams
        </h1>
        <p className="mt-ui-2 text-sm text-content-muted">
          See what is happening now, what needs your attention, and the next
          bounded owner action.
        </p>
      </header>

      <p className="text-xs font-semibold uppercase tracking-wide text-content-muted" role="status">
        Live updates: {realtime}
      </p>

      {query.data && (
        <Alert
          variant={
            query.data.connectivity.state === "connected"
              ? "information"
              : "warning"
          }
          title={`Worker execution: ${mobileEngineeringLabel(query.data.connectivity.state)}`}
        >
          {query.data.connectivity.state === "connected"
            ? "An authenticated worker session and fresh heartbeat are available. Individual execution still requires explicit approval and eligible durable state."
            : query.data.connectivity.state === "connecting"
              ? "An authenticated worker session exists without a fresh heartbeat. Execution is not connected."
              : "No active authenticated worker session with a fresh heartbeat is available. Execution is not connected."}
        </Alert>
      )}

      {query.data && query.data.items.length > 0 && (
        <section className="grid grid-cols-2 gap-ui-3 sm:grid-cols-4" aria-label="Engineering dashboard summary">
          {[
            ["Active", query.data.items.filter((item) => !["completed", "failed", "cancelled"].includes(item.pipeline_status)).length],
            ["Running", query.data.items.filter((item) => item.pipeline_status === "running").length],
            ["Owner attention", query.data.items.filter((item) => item.owner_attention_required).length],
            ["Completed", query.data.items.filter((item) => item.pipeline_status === "completed").length],
          ].map(([label, value]) => (
            <div key={label} className="rounded-xl border border-stroke bg-surface p-ui-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-content-muted">{label}</p>
              <p className="mt-ui-1 text-2xl font-bold">{value}</p>
            </div>
          ))}
        </section>
      )}

      <section className="grid gap-ui-4 lg:grid-cols-2" aria-label="Owner mission queues">
        <div className="rounded-xl border border-stroke bg-surface p-ui-4">
          <div className="flex items-center justify-between gap-ui-3">
            <h2 className="font-bold">Notification center</h2>
            {notifications.data && <Badge>{notifications.data.unread_count} unread</Badge>}
          </div>
          {notifications.data?.items.length === 0 && <p className="mt-ui-3 text-sm text-content-muted">No mission notifications.</p>}
          <ol className="mt-ui-3 space-y-ui-3">
            {notifications.data?.items.slice(0, 5).map((item) => (
              <li key={item.id} className="rounded-lg border border-stroke p-ui-3 text-sm">
                <div className="flex flex-wrap items-start justify-between gap-ui-2">
                  <Link className="font-semibold text-blue-400 hover:underline" to={`/engineering/${item.command_id}`}>{mobileEngineeringLabel(item.kind)}</Link>
                  <Badge>{item.escalated_at ? "Escalated" : mobileEngineeringLabel(item.severity)}</Badge>
                </div>
                <p className="mt-ui-1 text-content-muted">{mobileEngineeringTimestamp(item.created_at)}</p>
                {item.status === "unread" && <Button className="mt-ui-2" variant="outline" disabled={acknowledge.isPending} onClick={() => acknowledge.mutate({ id: item.id, version: item.version })}>Acknowledge</Button>}
              </li>
            ))}
          </ol>
        </div>

        <div className="rounded-xl border border-stroke bg-surface p-ui-4">
          <div className="flex items-center justify-between gap-ui-3">
            <h2 className="font-bold">Owner approval queue</h2>
            {approvalQueue.data && <Badge>{approvalQueue.data.total_count} pending</Badge>}
          </div>
          {approvalQueue.data?.items.length === 0 && <p className="mt-ui-3 text-sm text-content-muted">No commands await owner approval.</p>}
          <ol className="mt-ui-3 space-y-ui-3">
            {approvalQueue.data?.items.slice(0, 5).map((item) => (
              <li key={item.id} className="rounded-lg border border-stroke p-ui-3 text-sm">
                <Link className="break-all font-semibold text-blue-400 hover:underline" to={`/engineering/${item.id}`}>{item.ecid}</Link>
                <p className="mt-ui-1 text-content-muted">{item.repository_key} · {item.expected_branch}</p>
                <p className="mt-ui-1">Expires {mobileEngineeringTimestamp(item.expires_at)}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section aria-label="Engineering workstreams">
        {query.isLoading && (
          <div className="flex min-h-48 items-center justify-center">
            <Spinner label="Loading engineering workstreams" />
          </div>
        )}
        {query.isError &&
          (() => {
            const error = getOperatorApiError(
              query.error,
              "Engineering workstreams",
            );
            return (
              <Alert
                variant="danger"
                announcement="assertive"
                title={error.title}
                action={
                  error.retryable ? (
                    <Button
                      variant="outline"
                      onClick={() => void query.refetch()}
                    >
                      Retry
                    </Button>
                  ) : undefined
                }
              >
                {error.message}
              </Alert>
            );
          })()}
        {query.data?.items.length === 0 && (
          <EmptyState
            title="No engineering workstreams"
            description="There are no Engineering Commands in the current Company scope."
          />
        )}
        {query.data && query.data.items.length > 0 && (
          <div className="grid gap-ui-3">
            {query.data.items.map((workstream) => (
              <article
                key={workstream.command_id}
                className="min-w-0 rounded-xl border border-stroke bg-surface p-ui-4"
              >
                <div className="flex min-w-0 flex-wrap items-start justify-between gap-ui-3">
                  <div className="min-w-0">
                    <Link
                      to={`/engineering/${workstream.command_id}`}
                      className="break-all text-lg font-bold text-blue-400 hover:underline"
                    >
                      {workstream.ecid}
                    </Link>
                    <p className="mt-ui-1 text-sm text-content-muted">
                      {workstream.repository_key} · {workstream.expected_branch}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-ui-2">
                    <Badge>{mobileEngineeringLabel(workstream.pipeline_status)}</Badge>
                    {workstream.owner_attention_required && (
                      <Badge>Owner attention</Badge>
                    )}
                  </div>
                </div>
                <p className="mt-ui-3 text-sm">
                  {workstream.current_activity ?? workstream.progress_summary}
                </p>
                {workstream.progress_percent != null && (
                  <div className="mt-ui-2" aria-label={`Progress ${workstream.progress_percent}%`}>
                    <div className="h-2 overflow-hidden rounded-full bg-surface-muted">
                      <div className="h-full bg-blue-400" style={{ width: `${workstream.progress_percent}%` }} />
                    </div>
                  </div>
                )}
                {workstream.control_pending && (
                  <p className="mt-ui-2 text-xs font-semibold text-amber-300">Owner control request awaiting worker acknowledgement</p>
                )}
                <dl className="mt-ui-4 grid min-w-0 gap-ui-3 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-content-muted">Next safe action</dt>
                    <dd className="break-all">
                      {mobileEngineeringLabel(workstream.next_owner_action)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-content-muted">Worker</dt>
                    <dd className="break-all">
                      {workstream.assigned_worker_id ?? "Not assigned"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-content-muted">Lease or offer</dt>
                    <dd>
                      {workstream.offer_or_lease_state
                        ? mobileEngineeringLabel(workstream.offer_or_lease_state)
                        : "Not available"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-content-muted">Last heartbeat</dt>
                    <dd>
                      {mobileEngineeringTimestamp(workstream.heartbeat_at)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-content-muted">Review</dt>
                    <dd>
                      {workstream.review_state
                        ? mobileEngineeringLabel(workstream.review_state)
                        : "Not available"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-content-muted">Repository operation</dt>
                    <dd>
                      {workstream.repository_operation_status
                        ? mobileEngineeringLabel(
                            workstream.repository_operation_status,
                          )
                        : "Not available"}
                    </dd>
                  </div>
                  {workstream.resulting_commit_sha && (
                    <div>
                      <dt className="text-content-muted">Completed commit</dt>
                      <dd className="break-all font-mono">
                        {workstream.resulting_commit_sha}
                      </dd>
                    </div>
                  )}
                  {workstream.failure_classification && (
                    <div>
                      <dt className="text-content-muted">Failure</dt>
                      <dd className="break-all">
                        {mobileEngineeringLabel(
                          workstream.failure_classification,
                        )}
                      </dd>
                    </div>
                  )}
                </dl>
                <Link
                  to={`/engineering/${workstream.command_id}`}
                  className="mt-ui-4 inline-flex min-h-11 w-full items-center justify-center rounded-md border border-stroke-strong px-ui-4 text-sm font-semibold hover:bg-surface-muted sm:w-auto"
                  aria-label={`Open ${workstream.ecid}`}
                >
                  Open workstream
                </Link>
              </article>
            ))}
          </div>
        )}
      </section>

      {query.data && query.data.total_pages > 0 && (
        <nav
          className="flex flex-wrap items-center justify-between gap-ui-3 border-t border-stroke pt-ui-4"
          aria-label="Review pages"
        >
          <span className="text-sm text-content-muted">
            Page {query.data.page} of {query.data.total_pages} ·{" "}
            {query.data.total_count} workstreams
          </span>
          <div className="flex gap-ui-2">
            <Button
              variant="outline"
              aria-label="Previous page"
              disabled={query.data.page <= 1}
              onClick={() => setPage(query.data.page - 1)}
            >
              <ChevronLeft size={18} />
            </Button>
            <Button
              variant="outline"
              aria-label="Next page"
              disabled={query.data.page >= query.data.total_pages}
              onClick={() => setPage(query.data.page + 1)}
            >
              <ChevronRight size={18} />
            </Button>
          </div>
        </nav>
      )}
    </div>
  );
}
