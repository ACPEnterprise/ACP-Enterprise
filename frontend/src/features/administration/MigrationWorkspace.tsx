import { AlertTriangle, Database, History, Milestone } from "lucide-react";

import {
  Alert,
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Spinner,
} from "../../ui";
import { useMigrationReadiness } from "./hooks";

function label(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function statusVariant(
  status: string,
): "success" | "warning" | "danger" | "neutral" {
  if (status === "ready" || status === "completed") return "success";
  if (status === "conflicting" || status === "blocked") return "danger";
  if (status === "external_owner_gate" || status.includes("required"))
    return "warning";
  return "neutral";
}

export function MigrationWorkspace() {
  const readiness = useMigrationReadiness();
  if (readiness.isPending)
    return (
      <div className="grid min-h-48 place-items-center">
        <Spinner label="Loading migration readiness" />
      </div>
    );
  if (readiness.isError)
    return (
      <Alert variant="danger" announcement="assertive">
        Migration readiness is unavailable. No readiness state was inferred.
      </Alert>
    );
  const data = readiness.data;
  if (!data)
    return (
      <Alert variant="information">
        No migration readiness evidence is available.
      </Alert>
    );
  return (
    <section
      aria-labelledby="migration-workspace-title"
      className="space-y-ui-5"
    >
      <header className="space-y-ui-2">
        <div className="flex flex-wrap items-center gap-ui-3">
          <Milestone aria-hidden="true" />
          <h2 id="migration-workspace-title" className="text-heading-m">
            Migration readiness
          </h2>
          <Badge variant={statusVariant(data.overall_status)}>
            {label(data.overall_status)}
          </Badge>
        </div>
        <p className="text-body-s text-content-muted">
          Read-only source, reconciliation, recovery, and owner-gate evidence.
          This workspace cannot activate Production.
        </p>
      </header>
      {data.stale && (
        <Alert variant="warning">
          Readiness evidence is stale. Activation eligibility is not asserted.
        </Alert>
      )}
      {data.safe_failure_code && (
        <Alert variant="danger">
          Readiness is blocked: {label(data.safe_failure_code)}
        </Alert>
      )}
      <div className="grid gap-ui-4 lg:grid-cols-3">
        {data.sources.map((source) => (
          <Card key={source.source}>
            <CardHeader>
              <CardTitle>{source.source}</CardTitle>
              <CardDescription>{label(source.environment)}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-ui-2 text-body-s">
              <Badge variant={statusVariant(source.status)}>
                {label(source.status)}
              </Badge>
              <dl className="grid grid-cols-[auto_1fr] gap-x-ui-3 gap-y-ui-1">
                <dt>Connection</dt>
                <dd>{label(source.connection_state)}</dd>
                <dt>Acquisition</dt>
                <dd>{label(source.acquisition_state)}</dd>
                <dt>Manifest</dt>
                <dd>{label(source.manifest_state)}</dd>
                <dt>Delta</dt>
                <dd>{label(source.delta_state)}</dd>
                <dt>Freeze</dt>
                <dd>{label(source.freeze_state)}</dd>
              </dl>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Cutover timeline</CardTitle>
          <CardDescription>
            Current phase: {label(data.current_phase)}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="grid gap-ui-2 sm:grid-cols-2 lg:grid-cols-3">
            {data.timeline.map((item, index) => (
              <li
                key={item.phase}
                className="rounded-lg border border-stroke p-ui-3"
              >
                <span className="text-body-s text-content-muted">
                  {index + 1}
                </span>
                <div className="mt-ui-1 font-semibold">{item.phase}</div>
                <Badge variant={statusVariant(item.status)}>
                  {label(item.status)}
                </Badge>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Deterministic go / no-go</CardTitle>
          <CardDescription>
            Activation is never inferred from a generic green status.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-ui-3">
          <Badge variant={statusVariant(data.go_no_go.state)}>
            {label(data.go_no_go.state)}
          </Badge>
          <ul className="grid gap-ui-2 sm:grid-cols-2">
            {data.go_no_go.blockers.map((blocker) => (
              <li key={blocker} className="rounded-lg border border-stroke p-ui-3 text-body-s">
                {label(blocker)}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Disposition accounting</CardTitle>
          <CardDescription>
            Source = migrated + held + exception + non-applicable + deferred +
            unresolved.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="min-w-[760px] w-full text-left text-body-s">
              <thead>
                <tr>
                  {[
                    "Domain",
                    "Source",
                    "Migrated",
                    "Held",
                    "Exception",
                    "N/A",
                    "Deferred",
                    "Unresolved",
                    "Delta",
                  ].map((item) => (
                    <th key={item} className="border-b border-stroke p-ui-2">
                      {item}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.counts.map((item) => (
                  <tr
                    key={item.domain}
                    className={item.delta ? "bg-status-danger-subtle" : ""}
                  >
                    <th className="border-b border-stroke p-ui-2">
                      {item.domain}
                    </th>
                    {[
                      item.source,
                      item.migrated,
                      item.held,
                      item.exception,
                      item.non_applicable,
                      item.deferred,
                      item.unresolved,
                      item.delta,
                    ].map((value, index) => (
                      <td
                        key={index}
                        className="border-b border-stroke p-ui-2 tabular-nums"
                      >
                        {value.toLocaleString()}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
      <div className="grid gap-ui-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Cross-source authority</CardTitle>
          </CardHeader>
          <CardContent className="space-y-ui-2">
            {data.authority_states.map((item) => (
              <div
                key={item.fact}
                className="flex flex-wrap items-center justify-between gap-ui-2 rounded-lg border border-stroke p-ui-3"
              >
                <span>{item.fact}</span>
                <Badge variant={statusVariant(item.state)}>
                  {label(item.state)}
                </Badge>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Historical window</CardTitle>
          </CardHeader>
          <CardContent className="space-y-ui-2 text-body-s">
            <p>Start: {data.historical_window.starts_on ?? "Not selected"}</p>
            <p>End: {data.historical_window.ends_on}</p>
            <Badge variant="warning">
              {label(data.historical_window.opening_evidence_state)}
            </Badge>
            <p>{label(data.historical_window.completeness)}</p>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Owner decision packet</CardTitle>
          <CardDescription>
            Configuration only; this workspace does not decide real source
            authority.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="mb-ui-4 grid gap-ui-3 lg:grid-cols-2">
            {data.decision_packets.map((packet) => (
              <article key={packet.decision_id} className="space-y-ui-2 rounded-lg border border-stroke p-ui-3">
                <div className="flex flex-wrap items-start justify-between gap-ui-2">
                  <strong>{packet.question}</strong>
                  <Badge variant={statusVariant(packet.state)}>{label(packet.state)}</Badge>
                </div>
                <p className="text-body-s">{packet.current_evidence}</p>
                <p className="text-body-xs text-content-muted"><strong>Options:</strong> {packet.options.map(label).join(" · ")}</p>
                {packet.recommended_default && <p className="text-body-xs"><strong>Recommended:</strong> {label(packet.recommended_default)}</p>}
                <p className="text-body-xs"><strong>Risk:</strong> {packet.risk}</p>
                <p className="text-body-xs"><strong>Unlocks:</strong> {packet.unlocks}</p>
              </article>
            ))}
          </div>
          <ul className="grid gap-ui-2 sm:grid-cols-2">
            {data.owner_decisions.map((item) => (
              <li
                key={item.decision}
                className="flex items-center gap-ui-2 rounded-lg border border-stroke p-ui-3"
              >
                <AlertTriangle className="size-4 shrink-0" aria-hidden="true" />
                <span className="flex-1">{item.decision}</span>
                <Badge variant="warning">Owner decision required</Badge>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Run and replay history</CardTitle>
        </CardHeader>
        <CardContent className="space-y-ui-3">
          {data.run_history.map((run) => (
            <article
              key={run.run_id}
              className="rounded-lg border border-stroke p-ui-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-ui-2">
                <strong>{run.source}</strong>
                <Badge variant="success">{label(run.state)}</Badge>
              </div>
              <p className="mt-ui-1 break-all font-mono text-body-xs">
                {run.run_id}
              </p>
              <p className="text-body-s text-content-muted">
                Reconciliation: {label(run.reconciliation)} · Replay:{" "}
                {label(run.replay)} · Holds: {run.holds.toLocaleString()} ·
                Exceptions: {run.exceptions.toLocaleString()}
              </p>
            </article>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Recovery and evidence</CardTitle>
        </CardHeader>
        <CardContent className="space-y-ui-2 text-body-s">
          <div className="flex items-center gap-ui-2">
            <History aria-hidden="true" className="size-4" />
            {label(data.recovery_state)}
          </div>
          <div className="flex items-start gap-ui-2">
            <Database aria-hidden="true" className="mt-1 size-4 shrink-0" />
            <dl>
              <dt>Authority digest</dt>
              <dd className="break-all font-mono text-body-xs">
                {data.authority_digest}
              </dd>
              <dt className="mt-ui-2">Reconciliation digest</dt>
              <dd className="break-all font-mono text-body-xs">
                {data.reconciliation_digest}
              </dd>
            </dl>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
