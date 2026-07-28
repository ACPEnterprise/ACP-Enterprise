import { RadioTower } from "lucide-react";

import type {
  BeaconPriorityBand,
  BeaconSeverity,
  BeaconSignal,
  BeaconSupportingFact,
} from "../../api/beacon";
import { Alert, Badge, Button, EmptyState, Spinner } from "../../ui";
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

function SignalRow({ signal }: { readonly signal: BeaconSignal }) {
  const severity = severityPresentation[signal.severity];
  const priority = priorityPresentation[signal.priority.band];
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
        </div>
      </div>
      <p className="mt-ui-3 rounded-md border border-stroke bg-surface-muted p-ui-3 text-body-s text-content-secondary">
        <span className="font-semibold text-content">Why this priority:</span>{" "}
        {signal.priority.explanation}
      </p>
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
      <p className="mt-ui-3 text-body-s text-content-secondary">
        <span className="font-semibold text-content">Recommended action:</span>{" "}
        {signal.recommended_action}
      </p>
    </li>
  );
}

export function BeaconPanel({
  signals,
  loading,
  error,
  retry,
}: {
  readonly signals: readonly BeaconSignal[] | undefined;
  readonly loading: boolean;
  readonly error: boolean;
  readonly retry: () => void;
}) {
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
      {!loading && !error && signals?.length === 0 && (
        <EmptyState
          title="No active Beacon signals"
          description="Current authoritative records do not satisfy any configured deterministic signal rule."
        />
      )}
      {!loading && !error && signals && signals.length > 0 && (
        <ol aria-label="Owner attention queue">
          {signals.map((signal) => (
            <SignalRow key={signal.id} signal={signal} />
          ))}
        </ol>
      )}
    </CommandCenterPanel>
  );
}
