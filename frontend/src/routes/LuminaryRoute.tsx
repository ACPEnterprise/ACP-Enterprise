import { useState } from "react";
import { isAxiosError } from "axios";
import { Link, useNavigate } from "react-router";
import { useHasPermission } from "../auth";
import type {
  LuminaryFinding,
  LuminaryObservation,
  SourceCompletenessEntry,
} from "../api/luminary";
import {
  useAnalyzeLuminary,
  useLuminaryBriefing,
  useLuminaryOwnerEconomics,
  useLuminarySourceReadiness,
} from "../hooks/useLuminary";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Spinner,
} from "../ui";

const localDate = (value: Date) =>
  `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
const today = localDate(new Date());
const monthStart = `${today.slice(0, 7)}-01`;
const rangeFor = (kind: "DAY" | "WEEK" | "MONTH" | "YEAR") => {
  const now = new Date();
  const end = localDate(now);
  if (kind === "DAY") return { start: end, end };
  if (kind === "MONTH") return { start: `${end.slice(0, 7)}-01`, end };
  if (kind === "YEAR") return { start: `${end.slice(0, 4)}-01-01`, end };
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const mondayOffset = (start.getDay() + 6) % 7;
  start.setDate(start.getDate() - mondayOffset);
  return { start: localDate(start), end };
};
const words = (value: string) => value.replaceAll("_", " ");
const money = (item: LuminaryObservation) =>
  item.value_minor == null || !item.currency
    ? "Unavailable"
    : new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: item.currency,
      }).format(item.value_minor / 100);
const minorMoney = (value: number | null, currency: string | null = "USD") =>
  value == null
    ? "Not yet available"
    : !currency
      ? "Currency unavailable"
    : new Intl.NumberFormat(undefined, {
        style: "currency",
        currency,
      }).format(value / 100);
const signedMinorMoney = (value: number | undefined, currency = "USD") =>
  value == null
    ? "Unavailable"
    : `${value > 0 ? "+" : ""}${new Intl.NumberFormat(undefined, {
        style: "currency",
        currency,
      }).format(value / 100)}`;

function FindingCard({ finding }: { finding: LuminaryFinding }) {
  const warning = [
    "insufficient_evidence",
    "conflicting_evidence",
    "policy_required",
  ].includes(finding.finding_class);
  return (
    <Card tone={warning ? "warning" : "normal"}>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-content-muted">
            {words(finding.finding_class)}
          </span>
          <span className="rounded-full bg-surface-muted px-2 py-1 text-xs">
            {finding.confidence_percent}% confidence ·{" "}
            {words(finding.completeness)}
          </span>
        </div>
        <CardTitle>{finding.title}</CardTitle>
        <CardDescription>{finding.summary}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {finding.observations.length ? (
          <div className="grid gap-2 sm:grid-cols-2">
            {finding.observations.map((item) => (
              <div
                className="rounded-lg bg-surface-muted p-3"
                key={item.metric}
              >
                <p className="text-xs capitalize text-content-muted">
                  {words(item.metric)}
                </p>
                <p className="break-words text-lg font-semibold">
                  {item.unit === "minor_currency"
                    ? money(item)
                    : String(item.value_minor ?? "Unavailable")}
                </p>
              </div>
            ))}
          </div>
        ) : null}
        <div>
          <h3 className="text-sm font-semibold">Why this exists</h3>
          <p className="text-sm text-content-muted">{finding.explanation}</p>
        </div>
        {finding.limitations.length ? (
          <div>
            <h3 className="text-sm font-semibold">What remains uncertain</h3>
            <ul className="list-disc space-y-1 pl-5 text-sm text-content-muted">
              {finding.limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}
        <div>
          <h3 className="text-sm font-semibold">What to inspect next</h3>
          <ul className="list-disc space-y-1 pl-5 text-sm text-content-muted">
            {finding.investigate_next.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <details className="text-xs text-content-muted">
          <summary className="cursor-pointer font-medium">
            Evidence provenance
          </summary>
          <ul className="mt-2 space-y-1">
            {finding.evidence.map((item) => (
              <li
                className="break-all"
                key={`${item.source_domain}:${item.record_id}`}
              >
                {item.source_domain} · {item.record_type} · {item.record_id} ·{" "}
                {item.digest}
              </li>
            ))}
          </ul>
        </details>
      </CardContent>
    </Card>
  );
}

function SourceMatrix({ sources }: { sources: SourceCompletenessEntry[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Can I trust the profitability answer?</CardTitle>
        <CardDescription>
          Each source is classified from admitted evidence. Missing evidence is
          never zero.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {sources.map((item) => (
            <div
              className="rounded-lg border border-stroke p-3"
              key={item.source}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-semibold capitalize">{words(item.source)}</p>
                <span className="rounded-full bg-surface-muted px-2 py-1 text-xs font-semibold">
                  {words(item.state)}
                </span>
              </div>
              <p className="mt-2 text-sm text-content-muted">
                {item.explanation}
              </p>
              <p className="mt-2 text-xs text-content-muted">
                {item.evidence_count} admitted reference(s)
              </p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export function LuminaryRoute() {
  const navigate = useNavigate();
  const canRead = useHasPermission("COMPANY_LUMINARY_READ");
  const canAnalyze = useHasPermission("COMPANY_LUMINARY_ANALYZE");
  const [start, setStart] = useState(monthStart);
  const [end, setEnd] = useState(today);
  const [scope, setScope] = useState({ start: monthStart, end: today });
  const [scenarioKind, setScenarioKind] = useState("PRICE_PERCENT");
  const [scenarioChange, setScenarioChange] = useState("0");
  const [scenario, setScenario] = useState<{ kind: string; change?: number }>();
  const scenarioAcceptsChange = !["CLOSE_RATE_PERCENT", "ADD_TRUCK"].includes(scenarioKind);
  const parsedScenarioChange = Number(scenarioChange);
  const invalidScenarioChange = scenarioAcceptsChange && (
    scenarioChange.trim() === "" || !Number.isFinite(parsedScenarioChange) || parsedScenarioChange < -10000 || parsedScenarioChange > 10000
  );
  const invalidPeriod = !start || !end || start > end;
  const briefing = useLuminaryBriefing(scope.start, scope.end, canRead);
  const readiness = useLuminarySourceReadiness(scope.start, scope.end, canRead);
  const ownerEconomics = useLuminaryOwnerEconomics(
    scope.start,
    scope.end,
    scenario?.kind,
    scenario?.change,
    canRead,
  );
  const analyze = useAnalyzeLuminary(scope.start, scope.end);
  const briefingMissing =
    isAxiosError(briefing.error) && briefing.error.response?.status === 404;
  if (!canRead)
    return (
      <Alert variant="danger">
        You are not authorized to view Luminary intelligence.
      </Alert>
    );
  return (
    <div className="mx-auto max-w-6xl space-y-6 overflow-x-hidden pb-12">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-action-primary">
            Owner advisory intelligence
          </p>
          <h1 className="mt-1 text-2xl font-bold sm:text-3xl">Luminary</h1>
          <p className="mt-2 max-w-3xl text-content-muted">
            What accepted business evidence means—facts, comparisons,
            associations, limitations, and the next evidence worth inspecting.
          </p>
        </div>
        <Button
          variant="secondary"
          onClick={() => navigate("/lia?contextDomain=luminary")}
        >
          Ask LIA about this evidence
        </Button>
      </header>
      <Card>
        <CardContent className="pt-6">
          <div className="mb-3 flex flex-wrap gap-2" aria-label="Common business periods">
            {(["DAY", "WEEK", "MONTH", "YEAR"] as const).map((kind) => (
              <Button key={kind} type="button" variant="secondary" onClick={() => {
                const period = rangeFor(kind);
                setStart(period.start);
                setEnd(period.end);
                setScope(period);
              }}>
                {kind === "DAY" ? "Today" : `This ${kind.toLowerCase()}`}
              </Button>
            ))}
          </div>
          <form
            className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]"
            onSubmit={(event) => {
              event.preventDefault();
              if (invalidPeriod) return;
              setScope({ start, end });
            }}
          >
            <Input
              aria-label="Start date"
              type="date"
              value={start}
              onChange={(event) => setStart(event.target.value)}
            />
            <Input
              aria-label="End date"
              type="date"
              value={end}
              onChange={(event) => setEnd(event.target.value)}
            />
            <Button type="submit">View briefing</Button>
          </form>
          {invalidPeriod ? (
            <p className="mt-3 text-sm text-status-danger" role="alert">
              Choose a start date on or before the end date. No comparison was requested.
            </p>
          ) : null}
        </CardContent>
      </Card>
      {readiness.isPending ? (
        <Spinner label="Checking source completeness" />
      ) : readiness.data ? (
        <SourceMatrix sources={readiness.data.profitability.sources} />
      ) : (
        <Alert variant="warning">
          Source completeness could not be verified. No readiness was inferred.
        </Alert>
      )}
      {ownerEconomics.isPending ? (
        <Spinner label="Preparing read-only owner economics" />
      ) : ownerEconomics.data ? (
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle>Owner economics decision support</CardTitle>
              <span className="rounded-full bg-surface-muted px-2 py-1 text-xs font-semibold">
                {words(ownerEconomics.data.readiness)} · {ownerEconomics.data.confidence.score_percent}% confidence
              </span>
            </div>
            <CardDescription>
              Read-only candidates from admitted evidence. No price, Employee, Payroll, payment, or Accounting state can be changed here.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <section aria-labelledby="owner-health-title" className="rounded-lg border border-stroke p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h3 className="font-semibold" id="owner-health-title">Where the business stands</h3>
                  <p className="text-sm text-content-muted">Revenue, contribution, required burden, and break-even stay separate. Cash is not inferred.</p>
                </div>
                <span className="rounded-full bg-surface-muted px-2 py-1 text-xs font-semibold">
                  {words(ownerEconomics.data.owner_health.economic_health.status)}
                </span>
              </div>
              <dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {[
                  ["Revenue production", ownerEconomics.data.owner_health.revenue_production.value_minor, ownerEconomics.data.owner_health.revenue_production.classification],
                  ["Economic contribution", ownerEconomics.data.owner_health.economic_contribution.value_minor, ownerEconomics.data.owner_health.economic_contribution.classification],
                  ["Required economic burden", ownerEconomics.data.owner_health.required_economic_burden.value_minor, ownerEconomics.data.owner_health.required_economic_burden.classification],
                ].map(([label, value, classification]) => (
                  <div className="rounded-md bg-surface-muted p-3" key={String(label)}>
                    <dt className="text-xs font-semibold uppercase tracking-wide">{label}</dt>
                    <dd className="text-lg font-semibold">{minorMoney(value as number | null, ownerEconomics.data.currency)}</dd>
                    <dd className="text-xs text-content-muted">{words(String(classification))}</dd>
                  </div>
                ))}
                <div className="rounded-md bg-surface-muted p-3">
                  <dt className="text-xs font-semibold uppercase tracking-wide">Economic health</dt>
                  <dd className="text-lg font-semibold">{ownerEconomics.data.owner_health.economic_health.value_basis_points == null ? "Not yet available" : `${(ownerEconomics.data.owner_health.economic_health.value_basis_points / 100).toFixed(1)}%`}</dd>
                  <dd className="text-xs text-content-muted">{words(ownerEconomics.data.owner_health.economic_health.classification)} · 100% is break-even</dd>
                </div>
              </dl>
              {ownerEconomics.data.owner_health.economic_health.limitation ? <Alert variant="warning">{ownerEconomics.data.owner_health.economic_health.limitation}</Alert> : null}
              <details className="mt-3 text-sm text-content-muted">
                <summary className="cursor-pointer font-medium">Evidence and missing burden inputs</summary>
                <p className="mt-2">Revenue basis: {words(ownerEconomics.data.owner_health.revenue_production.basis)}.</p>
                <p>{ownerEconomics.data.owner_health.required_economic_burden.missing_components.length ? `Still needed: ${ownerEconomics.data.owner_health.required_economic_burden.missing_components.map(words).join(" · ")}.` : "The approved burden pool is available for this period."}</p>
                <p>{ownerEconomics.data.owner_health.cash_health.limitation}</p>
              </details>
            </section>
            <section aria-labelledby="active-reasoning-title" className="rounded-lg border border-stroke p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h3 className="font-semibold" id="active-reasoning-title">What this evidence means</h3>
                  <p className="text-sm text-content-muted">
                    Luminary evaluates the decision boundary without estimating missing values.
                  </p>
                </div>
                <span className="rounded-full bg-surface-muted px-2 py-1 text-xs font-semibold">
                  {words(ownerEconomics.data.active_reasoning.contribution.state)} contribution
                </span>
              </div>
              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                <div className="rounded-md bg-surface-muted p-3">
                  <h4 className="text-sm font-semibold">What ACP can conclude</h4>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
                    {ownerEconomics.data.active_reasoning.can_conclude.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                </div>
                <div className="rounded-md bg-surface-muted p-3">
                  <h4 className="text-sm font-semibold">What remains unknown</h4>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
                    {ownerEconomics.data.active_reasoning.cannot_conclude.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                </div>
              </div>
              <p className="mt-3 text-sm">
                Contribution evidence covers {ownerEconomics.data.active_reasoning.contribution.ready_job_count} of {ownerEconomics.data.active_reasoning.contribution.job_count} admitted Jobs ({(ownerEconomics.data.active_reasoning.contribution.job_population_coverage_basis_points / 100).toFixed(0)}% by Job population).
              </p>
              <p className="text-xs text-content-muted">{ownerEconomics.data.active_reasoning.required_burden.coverage_limitation}</p>
              {ownerEconomics.data.active_reasoning.highest_value_next_action ? (
                <div className="mt-4 rounded-lg border border-stroke p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-content-muted">Highest-value missing evidence</p>
                  <p className="font-semibold">{words(ownerEconomics.data.active_reasoning.highest_value_next_action.gap)}</p>
                  <p className="text-sm text-content-muted">{ownerEconomics.data.active_reasoning.highest_value_next_action.why_it_matters}</p>
                  {ownerEconomics.data.active_reasoning.highest_value_next_action.affected_job_count != null ? <p className="mt-2 text-sm">Affects {ownerEconomics.data.active_reasoning.highest_value_next_action.affected_job_count} Job(s){ownerEconomics.data.active_reasoning.highest_value_next_action.affected_authoritative_revenue_minor != null ? ` representing ${minorMoney(ownerEconomics.data.active_reasoning.highest_value_next_action.affected_authoritative_revenue_minor, ownerEconomics.data.currency)} of authoritative invoiced population` : ""}.</p> : null}
                  <p className="mt-2 text-sm"><span className="font-semibold">Who acts:</span> {words(ownerEconomics.data.active_reasoning.highest_value_next_action.responsible_party)}</p>
                  <p className="text-sm"><span className="font-semibold">What becomes knowable:</span> {ownerEconomics.data.active_reasoning.highest_value_next_action.unlocks}</p>
                  {ownerEconomics.data.active_reasoning.highest_value_next_action.ui_path ? (
                    <Link className="mt-2 inline-block text-sm font-semibold text-action-primary underline" to={ownerEconomics.data.active_reasoning.highest_value_next_action.ui_path}>
                      {ownerEconomics.data.active_reasoning.highest_value_next_action.ui_path_label}
                    </Link>
                  ) : <p className="mt-2 text-sm text-content-muted">{ownerEconomics.data.active_reasoning.highest_value_next_action.ui_path_label}</p>}
                </div>
              ) : <p className="mt-3 text-sm text-content-muted">No missing evidence is currently ranked.</p>}
              <details className="mt-4 text-sm">
                <summary className="cursor-pointer font-medium">Ranked evidence gaps</summary>
                <ol className="mt-2 space-y-2">
                  {ownerEconomics.data.active_reasoning.ranked_evidence_gaps.map((gap) => (
                    <li className="rounded-md bg-surface-muted p-3" key={gap.gap}>
                      <p className="font-semibold">{gap.rank}. {words(gap.gap)} · {words(gap.responsible_party)}</p>
                      <p className="text-content-muted">{gap.why_it_matters}</p>
                      <p className="text-xs text-content-muted">Impact: {words(gap.decision_impact)} · Source: {gap.expected_source} · Unlocks: {gap.unlocks}</p>
                      {gap.affected_job_count != null ? <p className="text-xs text-content-muted">Affected population: {gap.affected_job_count} Job(s){gap.affected_authoritative_revenue_minor != null ? ` · ${minorMoney(gap.affected_authoritative_revenue_minor, ownerEconomics.data.currency)} authoritative invoiced revenue` : ""}</p> : null}
                    </li>
                  ))}
                </ol>
                <p className="mt-2 text-xs text-content-muted">{ownerEconomics.data.active_reasoning.ranking_basis}</p>
              </details>
            </section>
            <section aria-labelledby="completion-planner-title" className="rounded-lg border border-stroke p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h3 className="font-semibold" id="completion-planner-title">Complete the economics model</h3>
                  <p className="text-sm text-content-muted">Luminary shows what is missing, who owns it, where it belongs, and what it unlocks. It cannot enter or estimate a value.</p>
                </div>
                <span className="rounded-full bg-surface-muted px-2 py-1 text-xs font-semibold">
                  {ownerEconomics.data.economic_completion_planner.summary.complete_category_count} of {ownerEconomics.data.economic_completion_planner.summary.total_category_count} complete
                </span>
              </div>
              {(ownerEconomics.data.economic_completion_planner.highest_value_next_completion ?? ownerEconomics.data.economic_completion_planner.ranked_completion_plan[0]) ? (() => {
                const next = (ownerEconomics.data.economic_completion_planner.highest_value_next_completion ?? ownerEconomics.data.economic_completion_planner.ranked_completion_plan[0])!;
                return (
                  <div className="mt-4 rounded-lg border border-stroke bg-surface-muted p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-content-muted">Complete next</p>
                    <p className="font-semibold">{next.label}</p>
                    <p className="mt-1 text-sm"><span className="font-semibold">Who:</span> {next.responsible_parties.map(words).join(" / ")}</p>
                    <p className="text-sm"><span className="font-semibold">Source:</span> {next.sources.join(" / ")}</p>
                    <p className="text-sm"><span className="font-semibold">What it unlocks:</span> {next.unlocks.join("; ")}</p>
                    {next.affected_job_count != null ? <p className="text-sm">Affected population: {next.affected_job_count} Job(s){next.affected_authoritative_revenue_minor != null ? ` · ${minorMoney(next.affected_authoritative_revenue_minor, ownerEconomics.data.currency)} authoritative invoiced revenue` : ""}</p> : null}
                    {next.ui_path ? <Link className="mt-2 inline-block text-sm font-semibold text-action-primary underline" to={next.ui_path}>{next.ui_path_label}</Link> : <p className="mt-2 text-sm text-content-muted">{next.ui_path_label}</p>}
                  </div>
                );
              })() : ownerEconomics.data.economic_completion_planner.summary.complete_category_count === ownerEconomics.data.economic_completion_planner.summary.total_category_count ? (
                <p className="mt-3 text-sm">All evaluated Economics categories are complete for this period.</p>
              ) : (
                <p className="mt-3 text-sm text-content-muted">No completion action can be ranked until an authoritative source population is available for this period.</p>
              )}
              <Alert variant="warning" className="mt-3">
                Temporary owner-confirmed amounts are not supported by the current canonical Economics authority. Luminary will not create one or treat a note as economic evidence.
              </Alert>
              <details className="mt-4 text-sm">
                <summary className="cursor-pointer font-medium">Completion matrix</summary>
                <ol className="mt-2 space-y-2">
                  {ownerEconomics.data.economic_completion_planner.ranked_completion_plan.map((item) => (
                    <li className="rounded-md bg-surface-muted p-3" key={item.category}>
                      <p className="font-semibold">{item.rank}. {item.label} · {words(item.state)}</p>
                      <p className="text-content-muted">Missing: {item.missing_dependencies.map(words).join(" · ")}</p>
                      <p className="text-xs text-content-muted">Who: {item.responsible_parties.map(words).join(" / ")} · Source: {item.sources.join(" / ")}</p>
                      <p className="text-xs text-content-muted">Unlocks: {item.unlocks.join("; ")}</p>
                    </li>
                  ))}
                </ol>
                <p className="mt-2 text-xs text-content-muted">{ownerEconomics.data.economic_completion_planner.ranking_limit}</p>
              </details>
            </section>
            <section aria-labelledby="driver-analysis-title" className="rounded-lg border border-stroke p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h3 className="font-semibold" id="driver-analysis-title">What happened and what drove it</h3>
                  <p className="text-sm text-content-muted">Materiality uses measured amounts and prior-period percentages—not an invented severity score.</p>
                </div>
                <span className="rounded-full bg-surface-muted px-2 py-1 text-xs font-semibold">{words(ownerEconomics.data.driver_analysis.state)}</span>
              </div>
              {ownerEconomics.data.driver_analysis.state === "AVAILABLE" ? (
                <>
                  <dl className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {ownerEconomics.data.driver_analysis.observed_changes.map((item) => (
                      <div className="rounded-md bg-surface-muted p-3" key={item.metric}>
                        <dt className="text-xs font-semibold uppercase tracking-wide">{words(item.metric)}</dt>
                        <dd className="text-sm font-semibold">
                          {item.unit === "minor_currency" ? signedMinorMoney(item.change, item.currency ?? "USD") : `${item.change > 0 ? "+" : ""}${item.change}`}
                        </dd>
                        <dd className="text-xs text-content-muted">{item.change_basis_points_of_prior == null ? "Prior-period percentage unavailable" : `${item.change_basis_points_of_prior > 0 ? "+" : ""}${(item.change_basis_points_of_prior / 100).toFixed(1)}% of prior period`}</dd>
                      </div>
                    ))}
                  </dl>
                  <div className="mt-4 grid gap-3 lg:grid-cols-2">
                    <div>
                      <h4 className="text-sm font-semibold">Measured contribution drivers</h4>
                      <ol className="mt-2 space-y-2">
                        {ownerEconomics.data.driver_analysis.measured_drivers.map((driver) => (
                          <li className="rounded-md bg-surface-muted p-3" key={driver.component}>
                            <p className="font-semibold">{words(driver.component)}</p>
                            <p className="text-sm">Contribution effect {signedMinorMoney(driver.contribution_effect_minor, ownerEconomics.data.currency ?? "USD")}</p>
                            <p className="text-xs text-content-muted">Measured arithmetic effect · cause unproven</p>
                          </li>
                        ))}
                      </ol>
                    </div>
                    <div>
                      <h4 className="text-sm font-semibold">Interpretation boundary</h4>
                      {ownerEconomics.data.driver_analysis.possible_drivers.map((driver) => <p className="mt-2 text-sm" key={driver.driver}><span className="font-semibold">Possible:</span> {driver.reason}</p>)}
                      {ownerEconomics.data.driver_analysis.unproven_causes.map((cause) => <p className="mt-2 text-sm text-content-muted" key={cause.cause}><span className="font-semibold">Unproven:</span> {cause.reason}</p>)}
                      {ownerEconomics.data.driver_analysis.economic_health?.distance_from_break_even_basis_points != null ? (
                        <p className="mt-3 text-sm font-semibold">Economic Health is {Math.abs(ownerEconomics.data.driver_analysis.economic_health.distance_from_break_even_basis_points / 100).toFixed(1)} percentage points {ownerEconomics.data.driver_analysis.economic_health.distance_from_break_even_basis_points >= 0 ? "above" : "below"} break-even.</p>
                      ) : <p className="mt-3 text-sm text-content-muted">Distance from break-even remains unavailable until the same-period numerator and denominator are authoritative.</p>}
                    </div>
                  </div>
                  {ownerEconomics.data.driver_analysis.cash_health ? <p className="mt-3 text-xs text-content-muted">{ownerEconomics.data.driver_analysis.cash_health.reason}</p> : null}
                </>
              ) : <Alert variant="warning">{ownerEconomics.data.driver_analysis.reason ?? "A comparable prior equal period is not available."}</Alert>}
            </section>
            <section
              aria-labelledby="period-comparison-title"
              className="rounded-lg border border-stroke p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h3 className="font-semibold" id="period-comparison-title">
                    What changed from the prior equal period
                  </h3>
                  <p className="text-sm text-content-muted">
                    {ownerEconomics.data.period.start}–{ownerEconomics.data.period.end}
                    {ownerEconomics.data.prior_period
                      ? ` compared with ${ownerEconomics.data.prior_period.start}–${ownerEconomics.data.prior_period.end}`
                      : " · prior period unavailable"}
                  </p>
                </div>
                <span className="rounded-full bg-surface-muted px-2 py-1 text-xs font-semibold">
                  {words(ownerEconomics.data.trend_support.state)}
                </span>
              </div>
              {ownerEconomics.data.trend_support.state === "READY" &&
              ownerEconomics.data.trend_support.comparison ? (
                <dl className="mt-3 grid grid-cols-2 gap-3 text-sm lg:grid-cols-4">
                  <div><dt className="text-content-muted">Revenue change</dt><dd className="font-semibold">{signedMinorMoney(ownerEconomics.data.trend_support.comparison.revenue_change_minor ?? ownerEconomics.data.trend_support.comparison.invoiced_revenue_change_minor, ownerEconomics.data.trend_support.comparison.currency ?? "USD")}</dd></div>
                  <div><dt className="text-content-muted">Contribution change</dt><dd className="font-semibold">{signedMinorMoney(ownerEconomics.data.trend_support.comparison.contribution_change_minor, ownerEconomics.data.trend_support.comparison.currency ?? "USD")}</dd></div>
                  <div><dt className="text-content-muted">Labor-cost change</dt><dd className="font-semibold">{signedMinorMoney(ownerEconomics.data.trend_support.comparison.labor_change_minor, ownerEconomics.data.trend_support.comparison.currency ?? "USD")}</dd></div>
                  <div><dt className="text-content-muted">Material-cost change</dt><dd className="font-semibold">{signedMinorMoney(ownerEconomics.data.trend_support.comparison.materials_change_minor, ownerEconomics.data.trend_support.comparison.currency ?? "USD")}</dd></div>
                </dl>
              ) : (
                <p className="mt-3 text-sm text-content-muted">
                  {ownerEconomics.data.trend_support.comparison?.reason ??
                    "Both equal periods need comparable admitted evidence before ACP can describe a trend."}
                </p>
              )}
              <p className="mt-3 text-xs text-content-muted">
                Authority: {words(ownerEconomics.data.trend_support.authority)}. Mixed-authority periods are labeled and never combined.
              </p>
            </section>
            <section aria-labelledby="delta-explanation-title" className="rounded-lg border border-stroke p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h3 className="font-semibold" id="delta-explanation-title">Why the measured economics changed</h3>
                  <p className="mt-1 text-sm text-content-muted">{ownerEconomics.data.delta_explanation.headline ?? ownerEconomics.data.delta_explanation.reason ?? "No comparable explanation is available."}</p>
                </div>
                <span className="rounded-full bg-surface-muted px-2 py-1 text-xs font-semibold">{words(ownerEconomics.data.delta_explanation.state)}</span>
              </div>
              {ownerEconomics.data.delta_explanation.components.length ? (
                <dl className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  {ownerEconomics.data.delta_explanation.components.map((component) => (
                    <div className="rounded-md bg-surface-muted p-3" key={component.component}>
                      <dt className="text-xs font-semibold uppercase tracking-wide">{words(component.component)}</dt>
                      <dd className="text-sm font-semibold">Measured change {signedMinorMoney(component.change_minor, ownerEconomics.data.delta_explanation.currency ?? "USD")}</dd>
                      <dd className="text-xs text-content-muted">Contribution effect {signedMinorMoney(component.contribution_effect_minor ?? undefined, ownerEconomics.data.delta_explanation.currency ?? "USD")}</dd>
                      <dd className="mt-1 text-xs text-content-muted">{words(component.classification)}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}
              {ownerEconomics.data.delta_explanation.explanation ? <p className="mt-3 text-sm">{ownerEconomics.data.delta_explanation.explanation}</p> : null}
              {ownerEconomics.data.delta_explanation.state === "EXPLAINED" ? (
                <p className="mt-2 text-sm font-medium">
                  Explained contribution change {signedMinorMoney(ownerEconomics.data.delta_explanation.explained_change_minor, ownerEconomics.data.delta_explanation.currency ?? "USD")}
                  {ownerEconomics.data.delta_explanation.contribution_margin_change_basis_points != null
                    ? ` · Contribution margin ${ownerEconomics.data.delta_explanation.contribution_margin_change_basis_points > 0 ? "+" : ""}${(ownerEconomics.data.delta_explanation.contribution_margin_change_basis_points / 100).toFixed(2)} percentage points`
                    : ""}
                </p>
              ) : null}
              {ownerEconomics.data.delta_explanation.missing_evidence?.length ? (
                <p className="mt-3 text-sm text-content-muted">ACP cannot yet explain: {ownerEconomics.data.delta_explanation.missing_evidence.map(words).join(" · ")}.</p>
              ) : null}
              <p className="mt-3 text-xs text-content-muted">{ownerEconomics.data.delta_explanation.causality_boundary}</p>
              <details className="mt-3 text-xs text-content-muted">
                <summary className="cursor-pointer font-medium">Supporting period evidence</summary>
                <p className="mt-2">Scope: Company {ownerEconomics.data.delta_explanation.scope.company_id}{ownerEconomics.data.delta_explanation.scope.branch_id ? ` · Branch ${ownerEconomics.data.delta_explanation.scope.branch_id}` : " · Company-wide"}</p>
                <p>As of {new Date(ownerEconomics.data.delta_explanation.as_of).toLocaleString()} · {words(ownerEconomics.data.delta_explanation.freshness)}</p>
                <p>{(ownerEconomics.data.delta_explanation.evidence_references?.current?.length ?? 0)} current and {(ownerEconomics.data.delta_explanation.evidence_references?.prior?.length ?? 0)} prior immutable result reference(s).</p>
              </details>
            </section>
            <section aria-labelledby="measurement-freshness-title" className="rounded-lg border border-stroke p-4">
              <h3 className="font-semibold" id="measurement-freshness-title">Measurement freshness and authority</h3>
              <p className="mt-1 text-sm text-content-muted">Generated as of {new Date(ownerEconomics.data.generated_at).toLocaleString()} from admitted evidence for the selected period.</p>
              <dl className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {ownerEconomics.data.facts.map((fact) => (
                  <div className="rounded-md bg-surface-muted p-3" key={`${fact.family}:${fact.metric}`}>
                    <dt className="text-xs font-semibold uppercase tracking-wide">{words(fact.metric)}</dt>
                    <dd className="text-sm font-semibold">{fact.units === "minor_currency" ? minorMoney(fact.value, fact.currency ?? "USD") : fact.value ?? "Unavailable"}</dd>
                    <dd className="text-xs text-content-muted">{words(fact.prerequisite_completeness)} · {words(fact.authority)}</dd>
                  </div>
                ))}
              </dl>
            </section>
            <section aria-labelledby="job-economics-title" className="space-y-3">
              <div>
                <h3 className="font-semibold" id="job-economics-title">What ACP knows by Job</h3>
                <p className="text-sm text-content-muted">Invoiced revenue, accepted work, and actual material evidence stay distinct. Missing cost is not shown as zero.</p>
              </div>
              {ownerEconomics.data.job_economics.length ? (
                <div className="grid gap-3 lg:grid-cols-2">
                  {ownerEconomics.data.job_economics.map((job) => (
                    <article className="rounded-lg border border-stroke p-4" key={job.job_id}>
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div><h4 className="font-semibold">Job {job.job_number}</h4><p className="text-xs text-content-muted">{job.customer.name} · {job.branch.name} · {job.service_category ? words(job.service_category) : "Uncategorized"}</p></div>
                        <span className="rounded-full bg-surface-muted px-2 py-1 text-xs font-semibold">{words(job.readiness)} · {job.confidence_percent}%</span>
                      </div>
                      <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
                        <div><dt className="text-content-muted">Invoiced revenue</dt><dd className="font-semibold">{minorMoney(job.invoiced_revenue_minor, ownerEconomics.data.currency)}</dd></div>
                        <div><dt className="text-content-muted">Accepted work</dt><dd className="font-semibold">{job.accepted_worked_seconds == null ? "Not yet available" : `${(job.accepted_worked_seconds / 3600).toFixed(2)} hours`}</dd></div>
                        <div><dt className="text-content-muted">Direct wage cost</dt><dd className="font-semibold">{minorMoney(job.direct_wage_cost_minor, ownerEconomics.data.currency)}</dd></div>
                        <div><dt className="text-content-muted">Actual material cost</dt><dd className="font-semibold">{minorMoney(job.actual_material_cost_minor, ownerEconomics.data.currency)}</dd></div>
                        <div><dt className="text-content-muted">Direct contribution</dt><dd className="font-semibold">{minorMoney(job.direct_contribution_minor, ownerEconomics.data.currency)}</dd></div>
                        <div><dt className="text-content-muted">Fully loaded profit</dt><dd className="font-semibold">{minorMoney(job.fully_loaded_profit_minor, ownerEconomics.data.currency)}</dd></div>
                      </dl>
                      <div className="mt-3"><p className="text-xs font-semibold">What ACP does not know</p><p className="text-xs text-content-muted">{job.missing_prerequisites.length ? job.missing_prerequisites.map(words).join(" · ") : "No required direct-contribution input is missing."}</p></div>
                      <Link className="mt-3 inline-block text-sm font-semibold text-action-primary underline" to={`/jobs/${job.job_id}`}>
                        Open supporting Job evidence
                      </Link>
                    </article>
                  ))}
                </div>
              ) : <Alert variant="warning">No admitted Job evidence exists for this period. ACP did not convert that absence to zero.</Alert>}
            </section>
            <section aria-labelledby="service-economics-title" className="space-y-3">
              <div><h3 className="font-semibold" id="service-economics-title">What it means by service line</h3><p className="text-sm text-content-muted">Only canonical Job categories are grouped. Incomplete contribution stays unavailable.</p></div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {ownerEconomics.data.service_line_economics.map((service) => (
                  <article className="rounded-lg border border-stroke p-3" key={service.service_category}>
                    <h4 className="font-semibold capitalize">{words(service.service_category)}</h4>
                    <p className="text-xs text-content-muted">{service.job_count} Jobs · {service.contribution_ready_job_count} contribution-ready</p>
                    <p className="mt-2 text-sm">Invoiced {minorMoney(service.invoiced_revenue_minor, ownerEconomics.data.currency)}</p>
                    <p className="text-sm">Average ticket {minorMoney(service.average_invoiced_ticket_minor, ownerEconomics.data.currency)}</p>
                    <p className="text-sm">Direct contribution {minorMoney(service.direct_contribution_minor, ownerEconomics.data.currency)}</p>
                    <p className="mt-2 text-xs text-content-muted">{service.missing_prerequisites.length ? `Still needed: ${service.missing_prerequisites.map(words).join(" · ")}` : "Complete for direct contribution."}</p>
                  </article>
                ))}
              </div>
              {ownerEconomics.data.service_line_economics.length === 0 ? (
                <Alert variant="warning">
                  No authoritative service-category evidence exists for this period. ACP did not infer categories from Job descriptions.
                </Alert>
              ) : null}
            </section>
            {ownerEconomics.data.admitted_source_evidence ? (
              <section className="rounded-lg border border-stroke p-4" aria-labelledby="admitted-evidence-title">
                <h3 className="font-semibold" id="admitted-evidence-title">Admitted source evidence</h3>
                <p className="mt-1 text-sm text-content-muted">
                  {ownerEconomics.data.admitted_source_evidence.admitted_reference_count} accepted native reference(s). Source facts remain separate from calculated profitability.
                </p>
                {ownerEconomics.data.admitted_source_evidence.summary ? (
                  <p className="mt-2 text-sm">
                    Jobs {ownerEconomics.data.admitted_source_evidence.summary.job_count}
                    {ownerEconomics.data.admitted_source_evidence.summary.invoiced_revenue_minor !== null
                      ? ` · Invoiced revenue ${minorMoney(ownerEconomics.data.admitted_source_evidence.summary.invoiced_revenue_minor, ownerEconomics.data.admitted_source_evidence.summary.currency)}`
                      : " · Invoiced revenue unavailable"}
                    {ownerEconomics.data.admitted_source_evidence.summary.accepted_worked_seconds !== null
                      ? ` · Accepted worked hours ${(ownerEconomics.data.admitted_source_evidence.summary.accepted_worked_seconds / 3600).toFixed(2)}`
                      : " · Accepted worked hours unavailable"}
                  </p>
                ) : null}
                <dl className="mt-3 grid gap-2 sm:grid-cols-2">
                  {Object.entries(ownerEconomics.data.admitted_source_evidence.families).map(([family, item]) => (
                    <div className="rounded-md bg-surface-muted p-3" key={family}>
                      <dt className="text-xs font-semibold uppercase tracking-wide">{words(family)}</dt>
                      <dd className="text-sm">{words(item.state)} · {item.reference_count} reference(s)</dd>
                      <dd className="text-xs text-content-muted">{item.limitation}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            ) : null}
            <section className="rounded-lg border border-stroke p-4" aria-labelledby="scenario-title">
              <h3 className="font-semibold" id="scenario-title">Read-only scenario</h3>
              <p className="mt-1 text-sm text-content-muted">Hypothetical decision support only. Evaluating a scenario cannot change pricing or operations.</p>
              <form className="mt-3 grid gap-3 sm:grid-cols-[1fr_1fr_auto]" onSubmit={(event) => { event.preventDefault(); if (invalidScenarioChange) return; setScenario({ kind: scenarioKind, change: scenarioAcceptsChange ? parsedScenarioChange : undefined }); }}>
                <label>Assumption<select className="block w-full" value={scenarioKind} onChange={(event) => setScenarioKind(event.target.value)}><option value="PRICE_PERCENT">Price percent</option><option value="AVERAGE_TICKET_PERCENT">Average ticket percent</option><option value="LABOR_EFFICIENCY_PERCENT">Labor efficiency percent</option><option value="MATERIAL_COST_PERCENT">Material cost percent</option><option value="CLOSE_RATE_PERCENT">Close rate percent</option><option value="ADD_TRUCK">Add truck</option></select></label>
                <label>Change (basis points)<Input disabled={!scenarioAcceptsChange} max={10000} min={-10000} type="number" value={scenarioChange} onChange={(event) => setScenarioChange(event.target.value)} /></label>
                <Button type="submit">Evaluate scenario</Button>
              </form>
              {!scenarioAcceptsChange ? <p className="mt-2 text-xs text-content-muted">This scenario is evidence-gated. ACP will report the missing prerequisite without inventing a numeric change.</p> : null}
              {invalidScenarioChange ? <p className="mt-2 text-sm text-status-danger" role="alert">Enter a basis-point change between -10,000 and 10,000.</p> : null}
              {ownerEconomics.data.scenario ? <div className="mt-3 text-sm"><p>Scenario state: <strong>{words(ownerEconomics.data.scenario.state)}</strong></p>{ownerEconomics.data.scenario.missing_prerequisites.length ? <p className="text-content-muted">Missing evidence: {ownerEconomics.data.scenario.missing_prerequisites.map(words).join(" · ")}</p> : <p className="text-content-muted">Deterministic deltas: {Object.entries(ownerEconomics.data.scenario.deltas ?? {}).map(([key, value]) => `${words(key)} ${value}`).join(" · ")}</p>}<p className="text-content-muted">No operational action occurred.</p></div> : <p className="mt-3 text-sm text-content-muted">No hypothetical scenario selected.</p>}
            </section>
            {ownerEconomics.data.recommendation_candidates.length ? (
              ownerEconomics.data.recommendation_candidates.map((candidate) => (
                <article className="rounded-lg border border-stroke p-4" key={candidate.recommendation_id}>
                  <p className="text-xs font-semibold uppercase tracking-wide text-content-muted">{words(candidate.family)} · candidate only</p>
                  <h3 className="mt-1 font-semibold">{candidate.owner_decision_required}</h3>
                  <p className="mt-2 text-sm text-content-muted">{candidate.economic_mechanism}</p>
                  <p className="mt-2 text-xs text-content-muted">Confidence {candidate.confidence}% · {candidate.status}</p>
                </article>
              ))
            ) : (
              <Alert variant="warning">No recommendation is supported for this scope. Missing or conflicting evidence remains missing.</Alert>
            )}
            {ownerEconomics.data.evidence_priority_queue.length ? (
              <section aria-labelledby="evidence-priority-title" className="rounded-lg border border-stroke p-4">
                <h3 className="font-semibold" id="evidence-priority-title">What evidence would improve this answer?</h3>
                <ul className="mt-3 space-y-3">
                  {ownerEconomics.data.evidence_priority_queue.map((item) => (
                    <li className="rounded-md bg-surface-muted p-3" key={item.prerequisite}>
                      <p className="font-medium">{words(item.prerequisite)}</p>
                      <p className="text-sm text-content-muted">{item.affected_job_count} affected Job(s) · responsible domain: {item.responsible_domain}</p>
                      <p className="text-xs text-content-muted">Next safe step: {words(item.next_safe_step)}. Unlocks {words(item.economic_unlock)}.</p>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
            <p className="break-all text-xs text-content-muted">Read-only packet {ownerEconomics.data.packet_digest}</p>
          </CardContent>
        </Card>
      ) : (
        <Alert variant="warning">Read-only owner Economics is unavailable. No recommendation was generated.</Alert>
      )}
      {briefing.isPending ? (
        <Spinner label="Loading Luminary briefing" />
      ) : briefing.isError && !briefingMissing ? (
        <Alert variant="danger" title="Luminary is temporarily unavailable">
          <div className="space-y-3">
            <p>
              No briefing state was inferred. Retry the authorized read when the
              service recovers.
            </p>
            <Button onClick={() => briefing.refetch()}>Retry briefing</Button>
          </div>
        </Alert>
      ) : briefingMissing || !briefing.data ? (
        <Alert variant="warning" title="No accepted briefing for this period">
          <div className="space-y-3">
            <p>
              Luminary will not invent an interpretation. Analyze admitted
              Economics evidence for this scope.
            </p>
            {canAnalyze ? (
              <Button
                disabled={analyze.isPending}
                onClick={() => analyze.mutate()}
              >
                {analyze.isPending ? "Analyzing…" : "Analyze accepted evidence"}
              </Button>
            ) : (
              <p>An explicitly authorized analyst must create the briefing.</p>
            )}
            {analyze.isError ? (
              <p>
                Analysis could not be completed. Source evidence may be
                unavailable or conflicting.
              </p>
            ) : null}
          </div>
        </Alert>
      ) : (
        <>
          <Alert
            variant={
              briefing.data.completeness === "complete"
                ? "success"
                : briefing.data.completeness === "conflicting"
                  ? "danger"
                  : "warning"
            }
            title={`Evidence ${words(briefing.data.completeness)}`}
          >
            {briefing.data.summary}
          </Alert>
          <section
            aria-label="Owner briefing"
            className="grid gap-4 lg:grid-cols-2"
          >
            {briefing.data.findings.map((finding) => (
              <FindingCard finding={finding} key={finding.id} />
            ))}
          </section>
          <p className="break-all text-xs text-content-muted">
            Briefing {briefing.data.id} · digest {briefing.data.briefing_digest}
          </p>
        </>
      )}
    </div>
  );
}
