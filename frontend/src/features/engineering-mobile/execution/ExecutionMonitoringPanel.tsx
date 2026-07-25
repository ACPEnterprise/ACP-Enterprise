import { RefreshCw } from "lucide-react";

import { getOperatorApiError } from "../../../api/errors";
import { Alert, Badge, Button, Card, Spinner } from "../../../ui";
import {
  mobileEngineeringLabel,
  mobileEngineeringTimestamp,
} from "../presentation";
import { useExecutionStatus } from "./hooks";

export function ExecutionMonitoringPanel({
  commandId,
}: {
  commandId: string;
}) {
  const query = useExecutionStatus(commandId);

  if (query.isLoading) {
    return (
      <Card className="min-w-0 p-ui-4 sm:p-ui-5">
        <Spinner label="Loading execution status" />
      </Card>
    );
  }
  if (query.isError || !query.data) {
    const error = getOperatorApiError(query.error, "execution status");
    return (
      <Alert
        variant="danger"
        announcement="assertive"
        title={error.title}
        action={
          error.retryable ? (
            <Button variant="outline" onClick={() => void query.refetch()}>
              Retry
            </Button>
          ) : undefined
        }
      >
        {error.message}
      </Alert>
    );
  }

  const status = query.data;
  return (
    <section className="space-y-ui-4" aria-labelledby="execution-monitor-title">
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-ui-3">
        <div>
          <h2 id="execution-monitor-title" className="text-xl font-bold">
            Execution status
          </h2>
          <p className="mt-ui-1 text-sm text-content-muted">
            Last checked {mobileEngineeringTimestamp(status.updated_at)}
          </p>
        </div>
        <Button
          className="w-full sm:w-auto"
          variant="outline"
          leadingIcon={<RefreshCw size={18} />}
          loading={query.isFetching}
          loadingLabel="Refreshing execution status"
          onClick={() => void query.refetch()}
        >
          Refresh
        </Button>
      </div>

      <Alert
        variant={
          status.connection_state === "connected" ? "information" : "warning"
        }
        title={`Worker transport: ${mobileEngineeringLabel(status.connection_state)}`}
      >
        {status.connection_state === "connected"
          ? "A recent authenticated worker heartbeat is available. This does not mean engineering execution has started."
          : status.connection_state === "connecting"
            ? "An authenticated transport session exists, but a fresh heartbeat has not been observed."
            : "No fresh authenticated worker connection is available. No live progress is being inferred."}
      </Alert>

      <div className="grid gap-ui-4 lg:grid-cols-2">
        <Card className="min-w-0 p-ui-4">
          <h3 className="font-bold">Progress</h3>
          <dl className="mt-ui-3 grid gap-ui-3 text-sm">
            <div>
              <dt className="text-content-muted">State</dt>
              <dd>
                <Badge>
                  {mobileEngineeringLabel(status.monitoring_state)}
                </Badge>
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Execution record</dt>
              <dd className="break-all">
                {status.execution_id ?? "Not available"}
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Started</dt>
              <dd>{mobileEngineeringTimestamp(status.started_at)}</dd>
            </div>
            <div>
              <dt className="text-content-muted">Finished</dt>
              <dd>{mobileEngineeringTimestamp(status.finished_at)}</dd>
            </div>
          </dl>
        </Card>

        <Card className="min-w-0 p-ui-4">
          <h3 className="font-bold">Worker availability</h3>
          <dl className="mt-ui-3 grid gap-ui-3 text-sm">
            <div>
              <dt className="text-content-muted">Connection</dt>
              <dd>
                <Badge>{mobileEngineeringLabel(status.connection_state)}</Badge>
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Transport health</dt>
              <dd className="break-words">{mobileEngineeringLabel(status.transport_health)}</dd>
            </div>
            <div>
              <dt className="text-content-muted">Lease</dt>
              <dd className="break-words">
                {status.lease.status
                  ? `${mobileEngineeringLabel(status.lease.status)} (${mobileEngineeringLabel(status.lease.phase)})`
                  : mobileEngineeringLabel(status.lease.availability)}
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Lease expires</dt>
              <dd>{mobileEngineeringTimestamp(status.lease.expires_at)}</dd>
            </div>
            <div>
              <dt className="text-content-muted">Heartbeat</dt>
              <dd className="break-words">
                {status.heartbeat.health ??
                  mobileEngineeringLabel(status.heartbeat.availability)}
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Last heartbeat</dt>
              <dd>{mobileEngineeringTimestamp(status.heartbeat.last_seen)}</dd>
            </div>
            <div>
              <dt className="text-content-muted">Heartbeat age</dt>
              <dd className="break-words">
                {status.heartbeat.age_seconds === null
                  ? "Unavailable"
                  : `${status.heartbeat.age_seconds} seconds`}
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Session</dt>
              <dd>
                {status.transport_session.state ??
                  mobileEngineeringLabel(status.transport_session.availability)}
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Last contact</dt>
              <dd>
                {mobileEngineeringTimestamp(
                  status.transport_session.last_contact_at,
                )}
              </dd>
            </div>
          </dl>
        </Card>
      </div>

      <Card className="min-w-0 p-ui-4">
        <h3 className="font-bold">Result</h3>
        <dl className="mt-ui-3 grid gap-ui-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-content-muted">Availability</dt>
            <dd>{mobileEngineeringLabel(status.result.availability)}</dd>
          </div>
          <div>
            <dt className="text-content-muted">Status</dt>
            <dd>{status.result.status ?? "Not available"}</dd>
          </div>
          <div>
            <dt className="text-content-muted">Validation summary</dt>
            <dd>
              {status.result.validation_available ? "Available" : "Unavailable"}
            </dd>
          </div>
          <div>
            <dt className="text-content-muted">Evidence summary</dt>
            <dd>
              {status.result.evidence_available ? "Available" : "Unavailable"}
            </dd>
          </div>
          <div>
            <dt className="text-content-muted">Failure</dt>
            <dd className="break-all">
              {status.result.failure_classification ?? "None reported"}
            </dd>
          </div>
        </dl>
      </Card>

      <Card className="min-w-0 p-ui-4">
        <h3 className="font-bold">Timeline</h3>
        <ol className="mt-ui-3 space-y-ui-3">
          {status.timeline.map((entry, index) => (
            <li
              key={`${entry.occurred_at}-${entry.event}-${index}`}
              className="border-l-2 border-stroke pl-ui-3 text-sm"
            >
              <p className="font-semibold">
                {mobileEngineeringLabel(entry.event)}
              </p>
              <p className="text-content-muted">
                {mobileEngineeringTimestamp(entry.occurred_at)}
              </p>
            </li>
          ))}
        </ol>
      </Card>

      <p className="text-xs text-content-muted">
        Automatic refresh is bounded and pauses when this execution reaches a
        terminal state. Streaming updates are not connected.
      </p>
    </section>
  );
}
