import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  CalendarDays,
  CircleDollarSign,
  RadioTower,
  ReceiptText,
  Sparkles,
} from "lucide-react";
import { Link } from "react-router";

import { useAuth } from "../auth/useAuth";
import { useEffectivePermissions } from "../auth/usePermissions";
import type { BeaconSignal, BeaconSupportingFact } from "../api/beacon";
import type { LuminaryEvidence, LuminaryFinding } from "../api/luminary";
import {
  useBeaconLifecycleActions,
  useActiveBeaconRecommendations,
  useBeaconSignals,
} from "../hooks/useBeaconSignals";
import { useDispatchBoard } from "../hooks/useDispatch";
import { useReceivablesSummary } from "../hooks/useInvoices";
import { useCompletedJobTrend } from "../hooks/useJobs";
import { useLuminaryBriefing } from "../hooks/useLuminary";
import { useMoneyPosition } from "../hooks/usePayments";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Select,
  Spinner,
} from "../ui";
import type { DispatchBoardItem } from "../types/dispatch";

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const now = new Date();
const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
const tomorrowDate = new Date(
  now.getFullYear(),
  now.getMonth(),
  now.getDate() + 1,
);
const tomorrow = `${tomorrowDate.getFullYear()}-${String(tomorrowDate.getMonth() + 1).padStart(2, "0")}-${String(tomorrowDate.getDate()).padStart(2, "0")}`;
const monthStart = `${today.slice(0, 7)}-01`;

type ContextRecord = {
  entity_type: string;
  entity_id: string | null;
  label?: string;
};
type ContextMetric = { name: string; value: string; unit?: string };

function money(
  value: string | number | boolean | null | undefined,
  currency: string | null = "USD",
) {
  if (value === null || value === undefined || value === "") return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency ?? "USD",
    maximumFractionDigits: 0,
  }).format(Number(value));
}

function count(value: number | null | undefined) {
  return value === null || value === undefined ? "—" : value.toLocaleString();
}

function ownerLabel(value: string) {
  const labels: Record<string, string> = {
    operations: "Operations",
    revenue: "Revenue",
    customer: "Customer",
    scheduling: "Scheduling",
    workforce: "People",
    count: "Jobs",
  };
  return labels[value] ?? value.replaceAll("_", " ");
}

function observationValue(item: {
  value_minor: number | null;
  unit: string;
  currency: string | null;
}) {
  if (item.value_minor == null) return "Not available";
  if (item.unit === "minor_currency") {
    return money(item.value_minor / 100, item.currency ?? "USD");
  }
  return `${item.value_minor.toLocaleString()} ${ownerLabel(item.unit)}`;
}

function dateWindow(date: string) {
  const [year, month, day] = date.split("-").map(Number);
  return {
    start: new Date(year, month - 1, day).toISOString(),
    end: new Date(year, month - 1, day + 1).toISOString(),
  };
}

function contextPath(
  domain: string,
  records: readonly ContextRecord[] = [],
  metrics: readonly ContextMetric[] = [],
  entityId?: string,
) {
  const params = new URLSearchParams({ contextDomain: domain });
  if (entityId && UUID.test(entityId)) params.set("contextId", entityId);
  records
    .filter((record) => record.entity_id && UUID.test(record.entity_id))
    .slice(0, 50)
    .forEach((record) =>
      params.append(
        "contextRecord",
        `${record.entity_type}:${record.entity_id}`,
      ),
    );
  metrics
    .slice(0, 20)
    .forEach((metric) =>
      params.append(
        "contextMetric",
        `${metric.name}:${metric.value}:${metric.unit ?? ""}`,
      ),
    );
  return `/lia?${params.toString()}`;
}

function evidenceRecords(signal: BeaconSignal): ContextRecord[] {
  const records = signal.supporting_facts.flatMap((fact) =>
    fact.evidence.map((item) => ({
      entity_type: item.entity_type,
      entity_id: item.entity_id,
    })),
  );
  return [
    ...new Map(
      records
        .filter((item) => UUID.test(item.entity_id))
        .map((item) => [`${item.entity_type}:${item.entity_id}`, item]),
    ).values(),
  ];
}

function evidencePath(entityType: string, entityId: string | null) {
  if (!entityId) return null;
  const paths: Record<string, string> = {
    customer: `/customers/${entityId}`,
    estimate: `/estimates/${entityId}`,
    job: `/jobs/${entityId}`,
    invoice: `/invoices/${entityId}`,
    appointment: `/appointments/${entityId}`,
    payment: `/payments/${entityId}`,
    employee: `/employees/${entityId}`,
  };
  return paths[entityType] ?? null;
}

function factLabel(fact: BeaconSupportingFact) {
  if (fact.unit === "currency_amount") return money(fact.value);
  return `${fact.value}${fact.unit ? ` ${fact.unit.replaceAll("_", " ")}` : ""}`;
}

function signalDate(signal: BeaconSignal) {
  const factDate = signal.supporting_facts.find(
    (fact) =>
      /date|start|scheduled/i.test(fact.name) &&
      typeof fact.value === "string" &&
      /^\d{4}-\d{2}-\d{2}/.test(fact.value),
  );
  if (factDate && typeof factDate.value === "string") {
    return factDate.value.slice(0, 10);
  }
  const evidenceDate = signal.supporting_facts
    .flatMap((fact) => fact.evidence)
    .find((item) => item.occurred_at)?.occurred_at;
  return evidenceDate?.slice(0, 10) ?? today;
}

function findingEvidence(finding: LuminaryFinding): ContextRecord[] {
  const rows = finding.evidence
    .filter((item) => UUID.test(item.record_id))
    .map((item) => ({
      entity_type: item.record_type,
      entity_id: item.record_id,
    }));
  return [
    ...new Map(
      rows.map((item) => [`${item.entity_type}:${item.entity_id}`, item]),
    ).values(),
  ];
}

function luminaryEvidencePath(item: LuminaryEvidence) {
  return evidencePath(item.record_type, item.record_id);
}

function Section({
  title,
  description,
  icon: Icon,
  children,
}: {
  readonly title: string;
  readonly description: string;
  readonly icon: typeof RadioTower;
  readonly children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-action-primary">
            <Icon aria-hidden="true" size={20} />
            <CardTitle>{title}</CardTitle>
          </div>
          <CardDescription>{description}</CardDescription>
        </div>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function PulseMetric({
  label,
  value,
  detail,
  to,
  tone = "normal",
}: {
  readonly label: string;
  readonly value: string;
  readonly detail: string;
  readonly to: string;
  readonly tone?: "normal" | "warning";
}) {
  return (
    <Link
      className={`block rounded-xl border p-4 transition hover:border-action-primary hover:bg-surface-muted ${tone === "warning" ? "border-status-warning/50" : "border-stroke"}`}
      to={to}
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-content-muted">
        {label}
      </p>
      <p className="mt-2 text-2xl font-bold text-action-primary">
        {value}
      </p>
      <p className="mt-1 text-xs text-content-muted">{detail}</p>
    </Link>
  );
}

function AttentionItem({
  signal,
  onSnooze,
}: {
  readonly signal: BeaconSignal;
  readonly onSnooze: (signal: BeaconSignal) => void;
}) {
  const records = evidenceRecords(signal);
  const askPath = contextPath(
    "beacon",
    records,
    signal.supporting_facts.map((fact) => ({
      name: fact.name,
      value: String(fact.value),
      unit: fact.unit ?? undefined,
    })),
    signal.id,
  );
  const staleEvidence = signal.evidence_quality?.freshness === "stale";
  const urgency = staleEvidence
    ? "Needs refresh"
    : signal.priority.band === "critical" || signal.priority.band === "immediate"
      ? "Act now"
      : signal.priority.band === "important"
        ? "Today"
        : "Monitor";
  return (
    <article className="rounded-xl border border-stroke bg-surface p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant={
                urgency === "Needs refresh"
                  ? "warning"
                  : urgency === "Act now"
                    ? "danger"
                    : urgency === "Today"
                      ? "warning"
                      : "neutral"
              }
            >
              {urgency}
            </Badge>
            <span className="text-xs text-content-muted">
              {ownerLabel(signal.category)}
            </span>
          </div>
          <h3 className="mt-2 text-lg font-semibold text-content">
            {signal.title}
          </h3>
          <p className="mt-1 text-sm text-content-secondary">
            {signal.priority.explanation}
          </p>
        </div>
        <RadioTower aria-hidden="true" className="text-accent" size={20} />
      </div>
      {staleEvidence ? (
        <Alert className="mt-4" variant="warning" title="Evidence needs refresh">
          This finding is based on stale source records. Refresh the source
          record before treating the recommendation as current.
        </Alert>
      ) : null}
      {signal.supporting_facts.length ? (
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          {signal.supporting_facts.slice(0, 4).map((fact) => (
            <div className="rounded-lg bg-surface-muted p-3" key={fact.name}>
              <p className="text-xs capitalize text-content-muted">
                {fact.name.replaceAll("_", " ")}
              </p>
              <p className="mt-1 font-semibold text-content">
                {factLabel(fact)}
              </p>
            </div>
          ))}
        </div>
      ) : null}
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-content-muted">
            Why it matters
          </p>
          <p className="mt-1 text-sm text-content-secondary">
            {signal.priority.explanation}
          </p>
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-content-muted">
            Recommended action
          </p>
          <p className="mt-1 text-sm text-content-secondary">
            {signal.recommended_action}
          </p>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        {signal.source === "scheduling" ? (
          <Link
            className="inline-flex min-h-10 items-center gap-1 font-semibold text-action-primary underline"
            to={`/scheduling?date=${signalDate(signal)}&perspective=dispatch${signal.rule_code.includes("unassigned") || signal.definition_id.includes("unassigned") ? "&queue=scheduled_unassigned" : ""}`}
          >
            Open Dispatch <ArrowRight size={15} />
          </Link>
        ) : null}
        {records.length ? (
          records.map((record) => {
            const path = evidencePath(record.entity_type, record.entity_id);
            return path ? (
              <Link
                className="inline-flex min-h-10 items-center gap-1 font-semibold text-action-primary underline"
                key={`${record.entity_type}:${record.entity_id}`}
                to={path}
              >
                Open {record.entity_type.replaceAll("_", " ")}{" "}
                <ArrowRight size={15} />
              </Link>
            ) : null;
          })
        ) : (
          <Link
            className="font-semibold text-action-primary underline"
            to={
              signal.source === "scheduling"
                ? `/scheduling?date=${today}&perspective=dispatch`
                : signal.source === "invoices"
                  ? `/invoices?state=open&asOf=${today}`
                  : "/jobs"
            }
          >
            Open{" "}
            {signal.source === "scheduling"
              ? "Dispatch"
              : signal.source === "invoices"
                ? "Invoices"
                : "Jobs"}
          </Link>
        )}
        <Link
          className="inline-flex min-h-10 items-center gap-1 font-semibold text-content underline"
          to={askPath}
        >
          <Bot size={16} /> Ask LIA about this
        </Link>
        <Button
          className="ml-auto"
          size="small"
          variant="outline"
          onClick={() => onSnooze(signal)}
        >
          Snooze until tomorrow
        </Button>
      </div>
      <details className="mt-4 text-xs text-content-muted">
        <summary className="cursor-pointer font-semibold">
          Why am I seeing this?
        </summary>
        <div className="mt-2 space-y-1">
          <p>
            Measured from {signal.source} records at{" "}
            {new Date(signal.created_at).toLocaleString()}.
          </p>
          <p>
            Rule: {signal.rule_code} · evidence digest: {signal.evidence_digest}
          </p>
          {records.map((record) => (
            <p key={`${record.entity_type}:${record.entity_id}`}>
              {record.entity_type}: {record.entity_id}
            </p>
          ))}
        </div>
      </details>
    </article>
  );
}

function AttentionSection({
  signals,
  loading,
  error,
  enabled,
  onSnooze,
  retry,
}: {
  readonly signals: readonly BeaconSignal[] | undefined;
  readonly loading: boolean;
  readonly error: boolean;
  readonly enabled: boolean;
  readonly onSnooze: (signal: BeaconSignal) => void;
  readonly retry: () => void;
}) {
  return (
    <Section
      title="Needs Your Attention"
      description="Beacon shows only current, actionable findings backed by tenant records."
      icon={AlertTriangle}
    >
      {!enabled ? (
        <Alert variant="information" title="Beacon is not available">
          Your account does not have access to current Beacon findings.
        </Alert>
      ) : loading ? (
        <Spinner label="Checking current business conditions" />
      ) : error ? (
        <Alert
          variant="danger"
          title="Beacon is temporarily unavailable"
          action={
            <Button variant="outline" onClick={retry}>
              Retry
            </Button>
          }
        >
          No finding state was inferred.
        </Alert>
      ) : signals?.length ? (
        <div className="space-y-3">
          {signals.map((signal) => (
            <AttentionItem
              key={signal.id}
              signal={signal}
              onSnooze={onSnooze}
            />
          ))}
        </div>
      ) : signals ? (
        <div className="rounded-xl border border-status-success/40 bg-status-success/10 p-5">
          <p className="text-lg font-semibold text-content">
            Nothing urgent needs your attention.
          </p>
          <p className="mt-1 text-sm text-content-secondary">
            Beacon found no active condition that needs owner action right now.
          </p>
        </div>
      ) : (
        <Alert variant="warning" title="Beacon data is not available">
          No current finding state was returned. No healthy or clear state was
          inferred.
        </Alert>
      )}
    </Section>
  );
}

function LuminarySection({
  start,
  end,
  enabled,
}: {
  readonly start: string;
  readonly end: string;
  readonly enabled: boolean;
}) {
  const briefing = useLuminaryBriefing(start, end, enabled);
  const findings = briefing.data?.findings ?? [];
  return (
    <Section
      title="Luminary"
      description="Patterns and changes explained from current business evidence."
      icon={Sparkles}
    >
      {!enabled ? (
        <Alert variant="information" title="Luminary is not available">
          Your account does not have access to Luminary explanations.
        </Alert>
      ) : briefing.isPending ? (
        <Spinner label="Explaining current business patterns" />
      ) : briefing.isError ? (
        <Alert variant="warning" title="Luminary is temporarily unavailable">
          No interpretation was inferred while the source evidence was
          unavailable.
        </Alert>
      ) : findings.length ? (
        <div className="space-y-3">
          {findings.slice(0, 3).map((finding) => {
            const records = findingEvidence(finding);
            const askPath = contextPath(
              "luminary",
              records,
              finding.observations.map((item) => ({
                name: item.metric,
                value: String(item.value_minor ?? "unavailable"),
                unit: item.unit,
              })),
            );
            return (
              <article
                className="rounded-xl border border-stroke p-4"
                key={finding.id}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                      What changed
                    </p>
                    <h3 className="mt-1 text-lg font-semibold text-content">
                      {finding.title}
                    </h3>
                    <p className="mt-1 text-sm text-content-secondary">
                      {finding.summary}
                    </p>
                  </div>
                  <Badge variant="information">
                    {finding.confidence_percent}% confidence
                  </Badge>
                </div>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                      Why
                    </p>
                    <p className="mt-1 text-sm text-content-secondary">
                      {finding.explanation}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-content-muted">
                      Measured impact
                    </p>
                    <p className="mt-1 text-sm text-content-secondary">
                      {finding.observations.length
                        ? finding.observations
                            .slice(0, 2)
                            .map(
                              (item) =>
                                `${item.metric.replaceAll("_", " ")}: ${observationValue(item)}`,
                            )
                            .join(" · ")
                        : "Impact is not available from the current evidence."}
                    </p>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-3">
                  {records.slice(0, 4).map((record) => {
                    const evidence = finding.evidence.find(
                      (item) => item.record_id === record.entity_id,
                    );
                    const path = evidence
                      ? luminaryEvidencePath(evidence)
                      : null;
                    return path ? (
                      <Link
                        className="font-semibold text-action-primary underline"
                        key={`${record.entity_type}:${record.entity_id}`}
                        to={path}
                      >
                        View {record.entity_type.replaceAll("_", " ")}
                      </Link>
                    ) : null;
                  })}
                  <Link
                    className="font-semibold text-content underline"
                    to={`/luminary?finding=${encodeURIComponent(finding.id)}`}
                  >
                    View details
                  </Link>
                  <Link
                    className="inline-flex items-center gap-1 font-semibold text-content underline"
                    to={askPath}
                  >
                    <Bot size={16} /> Ask LIA about this finding
                  </Link>
                </div>
                <details className="mt-3 text-xs text-content-muted">
                  <summary className="cursor-pointer font-semibold">
                    View evidence
                  </summary>
                  <ul className="mt-2 space-y-1">
                    {finding.evidence.map((item) => (
                      <li key={`${item.record_type}:${item.record_id}`}>
                        {item.source_domain} · {item.record_type} ·{" "}
                        {item.record_id}
                      </li>
                    ))}
                  </ul>
                </details>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="rounded-xl border border-stroke bg-surface-muted p-4 text-sm text-content-secondary">
          No material change was found in current Luminary evidence.
        </div>
      )}
      <Link
        className="mt-4 inline-flex min-h-10 items-center gap-1 font-semibold text-action-primary underline"
        to="/luminary"
      >
        Open Luminary details <ArrowRight size={16} />
      </Link>
    </Section>
  );
}

export function CommandCenterRoute() {
  const { activeCompany } = useAuth();
  const permissions = useEffectivePermissions();
  const [branchId, setBranchId] = useState("");
  const canReadAnalytics = permissions.has("COMPANY_ANALYTICS_READ");
  const canReadInvoices = permissions.has("COMPANY_INVOICE_READ");
  const canReadJobs = permissions.has("COMPANY_JOB_READ");
  const canReadDispatch = permissions.has("COMPANY_DISPATCH_READ");
  const canReadPayments = permissions.has("COMPANY_PAYMENT_READ");
  const canReadLuminary = permissions.has("COMPANY_LUMINARY_READ");
  const ar = useReceivablesSummary(
    today,
    branchId || undefined,
    canReadInvoices,
  );
  const jobs = useCompletedJobTrend(
    monthStart,
    today,
    "day",
    branchId || undefined,
    canReadJobs,
  );
  const todayDispatch = useDispatchBoard(
    dateWindow(today).start,
    dateWindow(today).end,
    branchId || undefined,
    canReadDispatch,
  );
  const tomorrowDispatch = useDispatchBoard(
    dateWindow(tomorrow).start,
    dateWindow(tomorrow).end,
    branchId || undefined,
    canReadDispatch,
  );
  const moneyPosition = useMoneyPosition(
    today,
    today,
    today,
    branchId || undefined,
    canReadPayments,
  );
  const beacon = useBeaconSignals(canReadAnalytics);
  const recommendations = useActiveBeaconRecommendations(
    canReadAnalytics && permissions.has("COMPANY_BEACON_OWN"),
  );
  const recommendationsEnabled =
    canReadAnalytics && permissions.has("COMPANY_BEACON_OWN");
  const lifecycle = useBeaconLifecycleActions();
  const mtdProduced = useMemo(
    () =>
      jobs.data?.points.length
        ? jobs.data.points.reduce(
            (total, point) => total + Number(point.produced_value ?? 0),
            0,
          )
        : null,
    [jobs.data],
  );
  const overdue = useMemo(
    () =>
      ar.data
        ? ar.data.buckets
            .filter((bucket) => bucket.key.startsWith("past_due"))
            .reduce((total, bucket) => total + Number(bucket.amount), 0)
        : null,
    [ar.data],
  );
  const unassignedToday = todayDispatch.data
    ? todayDispatch.data.items.filter(
        (item: DispatchBoardItem) => !item.assignment,
      ).length
    : null;
  const unassignedTomorrow = tomorrowDispatch.data
    ? tomorrowDispatch.data.items.filter(
        (item: DispatchBoardItem) => !item.assignment,
      ).length
    : null;
  const snooze = (signal: BeaconSignal) =>
    lifecycle.mutate({
      signal,
      action: "snooze",
      snoozeUntil: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
    });
  if (!activeCompany)
    return (
      <Alert variant="warning">
        Select a Company before opening Command Center.
      </Alert>
    );
  const dispatchLink = (date: string, queue?: string) =>
    `/scheduling?date=${date}&perspective=dispatch${queue ? `&queue=${queue}` : ""}${branchId ? `&branch=${encodeURIComponent(branchId)}` : ""}`;
  return (
    <div className="mx-auto max-w-[96rem] space-y-6 pb-14">
      <header className="flex flex-col gap-4 border-b border-stroke pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wider text-accent">
            Owner operations
          </p>
          <h1 className="mt-1 text-3xl font-bold text-action-primary sm:text-4xl">
            Command Center
          </h1>
          <p className="mt-2 max-w-3xl text-content-muted">
            Understand what changed, why it matters, and where to act.
          </p>
        </div>
        <label className="grid min-w-56 gap-1 text-sm font-semibold text-content">
          <span>Operating scope</span>
          <Select
            aria-label="Command Center Branch"
            value={branchId}
            onChange={(event) => setBranchId(event.target.value)}
          >
            <option value="">All accessible Branches</option>
            {activeCompany.branches.map((branch) => (
              <option key={branch.id} value={branch.id}>
                {branch.name}
              </option>
            ))}
          </Select>
        </label>
      </header>
      <AttentionSection
        signals={beacon.data?.items}
        loading={beacon.isPending || beacon.isLoading}
        error={beacon.isError}
        enabled={canReadAnalytics}
        onSnooze={snooze}
        retry={() => void beacon.refetch()}
      />
      <Section
        title="Business Pulse"
        description="A short view of today’s operating state. Select a metric to open the records behind it."
        icon={CircleDollarSign}
      >
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <PulseMetric
            label="Completed Job value today"
            value={
              !canReadJobs
                ? "Not available"
                : jobs.isError
                ? "Unavailable"
                : jobs.data
                  ? jobs.data.points.find((point) => point.period_start === today)
                    ? money(
                        jobs.data.points.find(
                          (point) => point.period_start === today,
                        )?.produced_value,
                        jobs.data.currency,
                      )
                    : "No data"
                  : "Loading…"
            }
            detail="Recorded value from completed Jobs"
            to={`/jobs?status=completed&completedStartAt=${encodeURIComponent(`${today}T00:00:00`)}&completedEndAt=${encodeURIComponent(`${tomorrow}T00:00:00`)}${branchId ? `&branchId=${encodeURIComponent(branchId)}` : ""}`}
          />
          <PulseMetric
            label="Completed Job value this month"
            value={
              !canReadJobs
                ? "Not available"
                : jobs.isError
                ? "Unavailable"
                : jobs.data
                  ? jobs.data.points.length
                    ? money(mtdProduced, jobs.data.currency)
                    : "No data"
                  : "Loading…"
            }
            detail={
              !canReadJobs
                ? "Job data is not available for this account"
                : jobs.data?.points.length
                  ? `${jobs.data.points.length} days with recorded value`
                  : "No completed Job value recorded in this period"
            }
            to={`/jobs?status=completed&completedStartAt=${encodeURIComponent(`${monthStart}T00:00:00`)}&completedEndAt=${encodeURIComponent(`${tomorrow}T00:00:00`)}${branchId ? `&branchId=${encodeURIComponent(branchId)}` : ""}`}
          />
          <PulseMetric
            label="Jobs scheduled today"
            value={
              !canReadDispatch
                ? "Not available"
                : todayDispatch.isError
                ? "Unavailable"
                : todayDispatch.data
                  ? count(todayDispatch.data.total_count)
                  : "Loading…"
            }
            detail="Appointments on today’s schedule"
            to={dispatchLink(today)}
          />
          <PulseMetric
            label="Jobs scheduled tomorrow"
            value={
              !canReadDispatch
                ? "Not available"
                : tomorrowDispatch.isError
                ? "Unavailable"
                : tomorrowDispatch.data
                  ? count(tomorrowDispatch.data.total_count)
                  : "Loading…"
            }
            detail={
              !canReadDispatch
                ? "Dispatch data is not available for this account"
                : tomorrowDispatch.data
                  ? unassignedTomorrow
                    ? `${unassignedTomorrow} without a technician`
                    : "No jobs without a technician"
                  : "Tomorrow’s schedule is not available yet"
            }
            to={dispatchLink(tomorrow)}
            tone={unassignedTomorrow ? "warning" : "normal"}
          />
          <PulseMetric
            label="Jobs without a technician today"
            value={
              !canReadDispatch
                ? "Not available"
                : todayDispatch.isError
                ? "Unavailable"
                : todayDispatch.data
                  ? count(unassignedToday)
                  : "Loading…"
            }
            detail="Jobs with no active technician assignment"
            to={dispatchLink(today, "scheduled_unassigned")}
            tone={unassignedToday ? "warning" : "normal"}
          />
          <PulseMetric
            label="Customer balances due"
            value={
              !canReadInvoices
                ? "Not available"
                : ar.isError
                ? "Unavailable"
                : ar.data
                  ? money(ar.data.total_open_amount, ar.data.currency ?? "USD")
                  : "Loading…"
            }
            detail={
              !canReadInvoices
                ? "Invoice data is not available for this account"
                : ar.data
                  ? `${ar.data.open_invoice_count} open Invoices`
                  : "Open Invoices could not be measured yet"
            }
            to={`/invoices?state=open&asOf=${today}${branchId ? `&branchId=${encodeURIComponent(branchId)}` : ""}`}
          />
          <PulseMetric
            label="Past-due customer balances"
            value={
              !canReadInvoices
                ? "Not available"
                : ar.isError
                ? "Unavailable"
                : ar.data
                  ? money(overdue, ar.data.currency ?? "USD")
                  : "Loading…"
            }
            detail="Past-due Invoices only"
            to={`/invoices?state=overdue&asOf=${today}${branchId ? `&branchId=${encodeURIComponent(branchId)}` : ""}`}
            tone={overdue ? "warning" : "normal"}
          />
          <PulseMetric
            label="Bank cash balance"
            value={
              !canReadPayments
                ? "Not available"
                : moneyPosition.data?.bank_balance.evidence_state === "AVAILABLE" ||
                  moneyPosition.data?.bank_balance.evidence_state === "MEASURED_ZERO"
                ? money(
                    moneyPosition.data.bank_balance.amount,
                    moneyPosition.data.bank_balance.currency,
                  )
                : moneyPosition.isError
                  ? "Unavailable"
                  : moneyPosition.data
                    ? "Not connected"
                    : "Loading…"
            }
            detail={
              moneyPosition.data?.bank_balance.evidence_state === "AVAILABLE" ||
              moneyPosition.data?.bank_balance.evidence_state === "MEASURED_ZERO"
                ? "Authoritative bank balance"
                : "No connected bank balance is available"
            }
            to="/banking"
          />
        </div>
      </Section>
      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <LuminarySection
          start={monthStart}
          end={today}
          enabled={canReadLuminary}
        />
        <Section
          title="Recommended actions"
          description="Next steps from current evidence. Ask LIA when you want help understanding the records."
          icon={Bot}
        >
          {!recommendationsEnabled ? (
            <Alert
              variant="information"
              title="Recommended actions are not available"
            >
              Beacon owner access is required to view action recommendations.
            </Alert>
          ) : recommendations.isPending ? (
            <Spinner label="Loading recommended actions" />
          ) : recommendations.isError ? (
            <Alert variant="warning">
              Recommended actions are temporarily unavailable.
            </Alert>
          ) : recommendations.data?.items.length ? (
            <div className="space-y-3">
              {recommendations.data.items.slice(0, 4).map((item) => (
                <article
                  className="rounded-xl border border-stroke p-4"
                  key={item.recommendation_id}
                >
                  <p className="font-semibold text-content">{item.title}</p>
                  <p className="mt-1 text-sm text-content-secondary">
                    {item.interpretation}
                  </p>
                  <p className="mt-2 text-sm">
                    <span className="font-semibold">Do this:</span>{" "}
                    {item.recommended_human_action}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-3">
                    <Link
                      className="font-semibold text-action-primary underline"
                      to={item.drilldown_path}
                    >
                      Open {item.action_destination}
                    </Link>
                    <Link
                      className="font-semibold text-content underline"
                      to={contextPath(
                        "beacon",
                        item.evidence.map((evidence) => ({
                          entity_type: evidence.entity_type,
                          entity_id: evidence.entity_id,
                        })),
                      )}
                    >
                      Ask LIA about this action
                    </Link>
                  </div>
                  <details className="mt-3 text-xs text-content-muted">
                    <summary className="cursor-pointer font-semibold">
                      Why am I seeing this?
                    </summary>
                    <p className="mt-2">
                      {item.measured_fact} · evidence as of{" "}
                      {new Date(item.evidence_as_of).toLocaleString()}
                    </p>
                  </details>
                </article>
              ))}
            </div>
          ) : (
            <p className="rounded-xl border border-stroke bg-surface-muted p-4 text-sm text-content-secondary">
              No additional recommended action is active from the current tenant
              evidence.
            </p>
          )}
          <Link
            className="mt-4 inline-flex min-h-10 items-center gap-1 font-semibold text-action-primary underline"
            to={contextPath("beacon")}
          >
            Ask LIA what to do next <ArrowRight size={16} />
          </Link>
        </Section>
      </div>
      <Section
        title="Owner shortcuts"
        description="Open the workspaces most often used to act on current conditions."
        icon={CalendarDays}
      >
        <div className="flex flex-wrap gap-3">
          <Link
            className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-stroke px-4 font-semibold text-action-primary hover:bg-surface-muted"
            to={dispatchLink(today)}
          >
            <CalendarDays size={16} /> Open Dispatch
          </Link>
          <Link
            className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-stroke px-4 font-semibold text-action-primary hover:bg-surface-muted"
            to={`/invoices?state=open&asOf=${today}`}
          >
            <ReceiptText size={16} /> Open Invoices
          </Link>
          <Link
            className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-stroke px-4 font-semibold text-action-primary hover:bg-surface-muted"
            to="/estimates"
          >
            <CircleDollarSign size={16} /> Open Estimates
          </Link>
        </div>
      </Section>
      <footer className="text-xs text-content-muted">
        Scope:{" "}
        {branchId
          ? activeCompany.branches.find((branch) => branch.id === branchId)
              ?.name
          : "All accessible Branches"}{" "}
        · as of {today}. Source details are available behind each finding.
      </footer>
    </div>
  );
}
