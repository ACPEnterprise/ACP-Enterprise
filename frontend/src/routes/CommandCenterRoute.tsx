import { useMemo, useState } from "react";
import {
  Banknote,
  CalendarDays,
  CircleDollarSign,
  Clock3,
  CreditCard,
  Gauge,
  ReceiptText,
  TrendingUp,
  Users,
} from "lucide-react";
import { Link } from "react-router";

import { useAuth } from "../auth/useAuth";
import { useEffectivePermissions } from "../auth/usePermissions";
import { JobsEvidenceGraph } from "../components/command-center/JobsEvidenceGraph";
import { useAnalyticsSummary } from "../hooks/useAnalyticsSummary";
import { useEconomicsMeasurementFoundation } from "../hooks/useBusinessEconomics";
import { useDispatchBoard } from "../hooks/useDispatch";
import { useReceivablesSummary } from "../hooks/useInvoices";
import { useCompletedJobTrend } from "../hooks/useJobs";
import { useMoneyPosition } from "../hooks/usePayments";
import type { DispatchBoardItem } from "../types/dispatch";
import type { JobTrendGranularity } from "../types/jobs";
import {
  Alert,
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Select,
} from "../ui";

type RangeKey = "day" | "week" | "month" | "12m" | "3y" | "5y" | "custom";
type JobMetric = "produced_value" | "job_count";
type BookedRange = "day" | "week" | "month";

const panelClass = "bg-surface";
const commandCenterObservedAt = new Date();
const commandCenterToday = new Date(
  commandCenterObservedAt.getFullYear(),
  commandCenterObservedAt.getMonth(),
  commandCenterObservedAt.getDate(),
);

function isoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function startOfMonth(value: Date): Date {
  return new Date(value.getFullYear(), value.getMonth(), 1);
}

function addMonths(value: Date, amount: number): Date {
  return new Date(value.getFullYear(), value.getMonth() + amount, 1);
}

function rangeFor(
  key: RangeKey,
  customStart: string,
  customEnd: string,
): { start: string; end: string; granularity: JobTrendGranularity } {
  const today = commandCenterToday;
  if (key === "day")
    return { start: isoDate(today), end: isoDate(today), granularity: "day" };
  if (key === "week")
    return {
      start: isoDate(new Date(today.getTime() - 6 * 86_400_000)),
      end: isoDate(today),
      granularity: "day",
    };
  if (key === "month")
    return {
      start: isoDate(startOfMonth(today)),
      end: isoDate(today),
      granularity: "day",
    };
  if (key === "12m")
    return {
      start: isoDate(addMonths(startOfMonth(today), -11)),
      end: isoDate(today),
      granularity: "month",
    };
  if (key === "3y")
    return {
      start: isoDate(addMonths(startOfMonth(today), -35)),
      end: isoDate(today),
      granularity: "month",
    };
  if (key === "5y")
    return {
      start: `${today.getFullYear() - 4}-01-01`,
      end: isoDate(today),
      granularity: "year",
    };
  const days = Math.max(
    0,
    (Date.parse(customEnd) - Date.parse(customStart)) / 86_400_000,
  );
  return {
    start: customStart,
    end: customEnd,
    granularity:
      days > 730 ? "year" : days > 120 ? "month" : days > 31 ? "week" : "day",
  };
}

function currency(
  value: string | null | undefined,
  code: string | null | undefined,
): string {
  if (value === null || value === undefined) return "Unavailable";
  if (!code) return Number(value) === 0 ? "Measured zero" : "Unavailable";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: code,
    maximumFractionDigits: 0,
  }).format(Number(value));
}

function moneyEvidence(
  amount: string | null | undefined,
  code: string | null | undefined,
  state: string | undefined,
): string {
  if (state === "MEASURED_ZERO") return code ? currency("0", code) : "Measured zero";
  if (state !== "AVAILABLE") return state === "INCOMPLETE" ? "Incomplete evidence" : "Unavailable";
  return currency(amount, code);
}

function Panel({
  title,
  description,
  icon: Icon,
  children,
  className = "",
}: {
  readonly title: string;
  readonly description: string;
  readonly icon: typeof Banknote;
  readonly children: React.ReactNode;
  readonly className?: string;
}) {
  return (
    <Card className={`${panelClass} ${className}`}>
      <CardHeader>
        <div className="flex items-center gap-2 text-action-primary">
          <Icon aria-hidden="true" size={20} />
          <CardTitle className="text-action-primary">{title}</CardTitle>
        </div>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function Unavailable({ children }: { readonly children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-stroke-strong bg-surface-muted p-4 text-sm text-content-muted">
      <strong className="block text-content">Unavailable</strong>
      {children}
    </div>
  );
}

function MoneyValue({
  label,
  value,
  detail,
  unavailable = false,
}: {
  readonly label: string;
  readonly value: string;
  readonly detail: string;
  readonly unavailable?: boolean;
}) {
  return (
    <div className="rounded-lg bg-surface-muted p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-content-muted">
        {label}
      </p>
      <p
        className={`mt-2 text-2xl font-bold ${unavailable ? "text-content-muted" : "text-action-primary"}`}
      >
        {value}
      </p>
      <p className="mt-1 text-xs text-content-muted">{detail}</p>
    </div>
  );
}

function dateWindow(offsetDays: number) {
  const start = new Date(commandCenterToday);
  start.setDate(start.getDate() + offsetDays);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  return { start: start.toISOString(), end: end.toISOString() };
}

function bookedDateWindow(range: BookedRange) {
  const start = new Date(commandCenterToday);
  if (range === "week") start.setDate(start.getDate() - start.getDay());
  if (range === "month") start.setDate(1);
  const end = new Date(start);
  if (range === "day") end.setDate(end.getDate() + 1);
  if (range === "week") end.setDate(end.getDate() + 7);
  if (range === "month") end.setMonth(end.getMonth() + 1);
  return { start: start.toISOString(), end: end.toISOString() };
}

function groupEmployeeItems(items: readonly DispatchBoardItem[]) {
  const grouped = new Map<
    string,
    { name: string; items: DispatchBoardItem[] }
  >();
  for (const item of items) {
    const id = item.assignment?.primary_employee_id ?? "unassigned";
    const existing = grouped.get(id) ?? {
      name: item.assignment?.primary_employee_name ?? "Unassigned",
      items: [],
    };
    grouped.set(id, { ...existing, items: [...existing.items, item] });
  }
  return [...grouped.entries()];
}

export function CommandCenterRoute() {
  const { activeCompany } = useAuth();
  const permissions = useEffectivePermissions();
  const [branchId, setBranchId] = useState("");
  const [rangeKey, setRangeKey] = useState<RangeKey>("month");
  const [jobMetric, setJobMetric] = useState<JobMetric>("produced_value");
  const [customStart, setCustomStart] = useState(
    isoDate(new Date(commandCenterToday.getTime() - 30 * 86_400_000)),
  );
  const [customEnd, setCustomEnd] = useState(isoDate(commandCenterToday));
  const [employeeDay, setEmployeeDay] = useState<"today" | "tomorrow">("today");
  const [bookedRange, setBookedRange] = useState<BookedRange>("day");
  const today = isoDate(commandCenterToday);
  const selectedRange = useMemo(
    () => rangeFor(rangeKey, customStart, customEnd),
    [rangeKey, customStart, customEnd],
  );
  const canReadInvoices = permissions.has("COMPANY_INVOICE_READ");
  const canReadJobs = permissions.has("COMPANY_JOB_READ");
  const canReadDispatch = permissions.has("COMPANY_DISPATCH_READ");
  const canReadPayments = permissions.has("COMPANY_PAYMENT_READ");
  const canReadAnalytics = permissions.has("COMPANY_ANALYTICS_READ");
  const canReadEconomics = permissions.has(
    "COMPANY_ECONOMICS_MEASUREMENT_READ",
  );
  const ar = useReceivablesSummary(
    today,
    branchId || undefined,
    canReadInvoices,
  );
  const jobs = useCompletedJobTrend(
    selectedRange.start,
    selectedRange.end,
    selectedRange.granularity,
    branchId || undefined,
    canReadJobs,
  );
  const employeeWindow = dateWindow(employeeDay === "today" ? 0 : 1);
  const dispatch = useDispatchBoard(
    employeeWindow.start,
    employeeWindow.end,
    branchId || undefined,
    canReadDispatch,
  );
  const bookedWindow = bookedDateWindow(bookedRange);
  const booked = useDispatchBoard(
    bookedWindow.start,
    bookedWindow.end,
    branchId || undefined,
    canReadDispatch,
  );
  const analytics = useAnalyticsSummary(canReadAnalytics && !branchId);
  const economics = useEconomicsMeasurementFoundation(canReadEconomics);
  const money = useMoneyPosition(
    today,
    today,
    today,
    branchId || undefined,
    canReadPayments,
  );
  const buckets = ar.data?.buckets ?? [];
  const groupedEmployees = useMemo(
    () => groupEmployeeItems(dispatch.data?.items ?? []),
    [dispatch.data?.items],
  );
  const todayPoint = jobs.data?.points.find(
    (point) => point.period_start === today,
  );

  if (!activeCompany)
    return (
      <Alert variant="warning">
        Select a Company before opening Command Center.
      </Alert>
    );

  return (
    <div className="mx-auto max-w-[96rem] space-y-6 pb-14">
      <header className="flex flex-col gap-4 border-b border-stroke pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wider text-accent">
            Twelve Hats owner operations
          </p>
          <h1 className="mt-1 text-3xl font-bold text-action-primary sm:text-4xl">
            Command Center
          </h1>
          <p className="mt-2 max-w-3xl text-content-muted">
            Money first, operations second, every authoritative aggregate
            connected to its evidence.
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

      <Panel
        title="Money / Cash Position"
        description={`Company/Branch scope as of ${today}. Scheduled revenue is never represented as expected cash.`}
        icon={Banknote}
      >
        <div className="grid gap-3 sm:grid-cols-3">
          <MoneyValue
            label="Bank cash / available"
            value={
              money.data?.bank_balance.connection_state === "NOT_CONNECTED"
                ? "Not connected"
                : moneyEvidence(
                    money.data?.bank_balance.amount,
                    money.data?.bank_balance.currency,
                    money.data?.bank_balance.evidence_state,
                  )
            }
            detail={money.data?.bank_balance.limitation ?? "No authoritative bank balance evidence is available."}
            unavailable={money.data?.bank_balance.evidence_state !== "AVAILABLE"}
          />
          <MoneyValue
            label="Total open receivables"
            value={
              ar.isError || !canReadInvoices
                ? "Unavailable"
                : currency(ar.data?.total_open_amount, ar.data?.currency)
            }
            detail={
              ar.data
                ? `${ar.data.open_invoice_count} open Invoices · as of ${ar.data.as_of}`
                : "Invoice authority did not provide current evidence."
            }
            unavailable={!ar.data || ar.data.total_open_amount === null}
          />
          <MoneyValue
            label="Expected cash today"
            value={moneyEvidence(
              money.data?.expected_collections_today.amount,
              money.data?.expected_collections_today.currency,
              money.data?.expected_collections_today.evidence_state,
            )}
            detail={
              money.data
                ? `Due-today AR: ${moneyEvidence(
                    money.data.accounts_receivable_due_today.amount,
                    money.data.accounts_receivable_due_today.currency,
                    money.data.accounts_receivable_due_today.evidence_state,
                  )}. ${money.data.expected_collections_today.limitation ?? "COD and due-today evidence are complete."}`
                : "Payment authority did not provide current collection evidence."
            }
            unavailable={money.data?.expected_collections_today.evidence_state !== "AVAILABLE" && money.data?.expected_collections_today.evidence_state !== "MEASURED_ZERO"}
          />
        </div>
      </Panel>

      <div className="grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
        <Panel
          title="Jobs — Produced Work"
          description="Completed Job count and sold-snapshot produced value. Every graph point opens its exact underlying Job population."
          icon={TrendingUp}
        >
          <div className="mb-4 flex flex-wrap gap-2">
            {(
              [
                "day",
                "week",
                "month",
                "12m",
                "3y",
                "5y",
                "custom",
              ] as RangeKey[]
            ).map((key) => (
              <button
                className={`min-h-11 rounded-md px-3 text-sm font-semibold ${rangeKey === key ? "bg-action-primary text-content-inverse" : "border border-stroke text-action-primary"}`}
                key={key}
                onClick={() => setRangeKey(key)}
                type="button"
              >
                {key === "12m"
                  ? "12 Months"
                  : key === "3y"
                    ? "3 Years"
                    : key === "5y"
                      ? "5 Years"
                      : key[0].toUpperCase() + key.slice(1)}
              </button>
            ))}
          </div>
          {rangeKey === "custom" && (
            <div className="mb-4 grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1 text-sm">
                Start
                <input
                  aria-label="Custom range start"
                  className="min-h-11 rounded-md border border-stroke bg-surface px-3"
                  type="date"
                  value={customStart}
                  onChange={(event) => setCustomStart(event.target.value)}
                />
              </label>
              <label className="grid gap-1 text-sm">
                End
                <input
                  aria-label="Custom range end"
                  className="min-h-11 rounded-md border border-stroke bg-surface px-3"
                  type="date"
                  value={customEnd}
                  onChange={(event) => setCustomEnd(event.target.value)}
                />
              </label>
            </div>
          )}
          <div className="mb-4 flex gap-2">
            <button
              className={`min-h-11 rounded-md px-3 text-sm font-semibold ${jobMetric === "produced_value" ? "bg-action-primary text-white" : "border border-stroke"}`}
              onClick={() => setJobMetric("produced_value")}
              type="button"
            >
              Produced value
            </button>
            <button
              className={`min-h-11 rounded-md px-3 text-sm font-semibold ${jobMetric === "job_count" ? "bg-action-primary text-white" : "border border-stroke"}`}
              onClick={() => setJobMetric("job_count")}
              type="button"
            >
              Job count
            </button>
          </div>
          {jobs.isPending ? (
            <p className="p-8 text-center text-content-muted">
              Loading completed Job evidence…
            </p>
          ) : jobs.isError || !jobs.data ? (
            <Unavailable>
              Completed Job reporting could not be loaded.
            </Unavailable>
          ) : (
            <JobsEvidenceGraph
              branchId={branchId || undefined}
              currency={jobs.data.currency}
              metric={jobMetric}
              points={jobs.data.points}
            />
          )}
        </Panel>

        <Panel
          title="Economic Health"
          description="100% will represent break-even only after the owner's authoritative break-even model is approved."
          icon={Gauge}
        >
          <div
            className="rounded-xl border-2 border-dashed border-stroke-strong bg-surface-muted p-5 data-[economic-status=RED]:border-solid data-[economic-status=RED]:border-status-danger data-[economic-status=RED]:bg-status-danger/15 data-[economic-status=RED]:text-status-danger"
            data-economic-status="UNAVAILABLE"
          >
            <Badge variant="warning">INCOMPLETE EVIDENCE</Badge>
            <p className="mt-4 text-2xl font-bold text-action-primary">
              Economic Health unavailable
            </p>
            <p className="mt-2 text-sm text-content-muted">
              {economics.data?.canonical_efficiency_kpi === null
                ? "The existing economics contract explicitly has no canonical efficiency KPI. Break-even inputs and allocation policy remain prerequisites."
                : economics.isError
                  ? "Economics readiness could not be loaded."
                  : "Loading economics readiness…"}
            </p>
          </div>
          <p className="mt-3 text-xs text-content-muted">
            A future RED condition uses a dedicated danger badge, icon, and
            strong status background; the thin red card border is decorative
            only.
          </p>
          <Link
            className="mt-4 inline-flex min-h-11 items-center font-semibold text-action-primary hover:underline"
            to="/business-economics"
          >
            Inspect economics evidence
          </Link>
        </Panel>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel
          title="Pipeline"
          description="Every inbound opportunity belongs to one Lead lifecycle. ACP does not yet have a qualified first-class Lead authority."
          icon={Users}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Unavailable>
              Scheduled / moving forward is unavailable until Lead stage and
              next-action evidence exist.
            </Unavailable>
            <Unavailable>
              Needs attention is unavailable until callback, stale-opportunity,
              and ownership evidence exist.
            </Unavailable>
          </div>
          <div className="mt-4 flex flex-wrap gap-4">
            <Link
              className="font-semibold text-action-primary hover:underline"
              to="/estimates"
            >
              Open Estimates
            </Link>
            <Link
              className="font-semibold text-action-primary hover:underline"
              to="/customers"
            >
              Open Customers
            </Link>
          </div>
        </Panel>

        <Panel
          title="Employee Status"
          description="Authoritative scheduled/confirmed Appointment and Dispatch assignment evidence."
          icon={CalendarDays}
        >
          <div className="mb-4 flex gap-2">
            <button
              className={`min-h-11 rounded-md px-4 font-semibold ${employeeDay === "today" ? "bg-action-primary text-white" : "border border-stroke"}`}
              onClick={() => setEmployeeDay("today")}
              type="button"
            >
              Today
            </button>
            <button
              className={`min-h-11 rounded-md px-4 font-semibold ${employeeDay === "tomorrow" ? "bg-action-primary text-white" : "border border-stroke"}`}
              onClick={() => setEmployeeDay("tomorrow")}
              type="button"
            >
              Tomorrow
            </button>
          </div>
          {dispatch.isPending ? (
            <p className="text-content-muted">Loading employee work…</p>
          ) : dispatch.isError || !canReadDispatch ? (
            <Unavailable>Dispatch board evidence is unavailable.</Unavailable>
          ) : groupedEmployees.length === 0 ? (
            <p className="text-sm text-content-muted">
              Measured zero scheduled/confirmed Appointments for this scope.
            </p>
          ) : (
            <div className="space-y-3">
              {groupedEmployees.map(([id, group]) => (
                <section className="rounded-lg bg-surface-muted p-3" key={id}>
                  <div className="flex items-center justify-between">
                    <h3 className="font-bold text-action-primary">
                      {group.name}
                    </h3>
                    <span className="text-xs text-content-muted">
                      {group.items.length} stops
                    </span>
                  </div>
                  <ol className="mt-2 space-y-2">
                    {group.items.map((item, index) => (
                      <li
                        className="flex items-center justify-between gap-3 text-sm"
                        key={item.appointment_id}
                      >
                        <span>
                          {index + 1}. {item.customer_display_name ?? item.appointment_number}
                          <span className="block text-xs text-content-muted">
                            {item.job_number ? `${item.job_number} · ` : ""}
                            {new Date(item.window_start_at).toLocaleTimeString(
                              [],
                              { hour: "numeric", minute: "2-digit" },
                            )}{" "}
                            · {item.status}
                          </span>
                        </span>
                        {item.job_id ? (
                          <Link
                            className="font-semibold text-action-primary hover:underline"
                            to={`/jobs/${item.job_id}`}
                          >
                            Open Job
                          </Link>
                        ) : (
                          <Link
                            className="font-semibold text-action-primary hover:underline"
                            to={`/appointments/${item.appointment_id}`}
                          >
                            Open
                          </Link>
                        )}
                      </li>
                    ))}
                  </ol>
                </section>
              ))}
            </div>
          )}
          <Link
            className="mt-4 inline-flex min-h-11 items-center font-semibold text-action-primary hover:underline"
            to="/dispatch"
          >
            Open Dispatch
          </Link>
        </Panel>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
        <Panel
          title="Open Invoices"
          description="Open accounts receivable by exact contractual due state. Paid Invoices are intentionally excluded."
          icon={ReceiptText}
        >
          {!canReadInvoices || ar.isError ? (
            <Unavailable>Receivables authority is unavailable.</Unavailable>
          ) : (
            <div className="space-y-2">
              {buckets.map((bucket) => {
                const query = new URLSearchParams({
                  state: "open",
                  agingBucket: bucket.key,
                  asOf: today,
                });
                if (branchId) query.set("branchId", branchId);
                return (
                  <Link
                    className="grid min-h-14 grid-cols-[1fr_auto] items-center gap-3 rounded-lg border border-stroke p-3 hover:border-action-primary hover:bg-surface-muted"
                    key={bucket.key}
                    to={`/invoices?${query.toString()}`}
                  >
                    <span>
                      <strong className="text-action-primary">
                        {bucket.label}
                      </strong>
                      <span className="block text-xs text-content-muted">
                        {bucket.invoice_count} Invoices
                      </span>
                    </span>
                    <strong>
                      {currency(bucket.amount, ar.data?.currency)}
                    </strong>
                  </Link>
                );
              })}
            </div>
          )}
        </Panel>

        <Panel
          title="Today's Scorecard"
          description="Live operating facts for the current day. Collected and deposited remain distinct states."
          icon={CircleDollarSign}
        >
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MoneyValue
              label="Jobs completed"
              value={todayPoint ? String(todayPoint.job_count) : "Unavailable"}
              detail={
                todayPoint
                  ? "Authoritative completed Jobs today"
                  : "Job reporting evidence unavailable"
              }
              unavailable={!todayPoint}
            />
            <MoneyValue
              label="Produced value"
              value={
                todayPoint
                  ? currency(todayPoint.produced_value, jobs.data?.currency)
                  : "Unavailable"
              }
              detail={
                todayPoint?.missing_value_count
                  ? `${todayPoint.missing_value_count} completed Jobs lack sold-snapshot value`
                  : "Completed sold-snapshot value"
              }
              unavailable={!todayPoint?.produced_value}
            />
            <MoneyValue
              label="Collected"
              value={moneyEvidence(
                money.data?.collection_state.collected.amount,
                money.data?.collection_state.collected.currency,
                money.data?.collection_state.collected.evidence_state,
              )}
              detail="Captured provider receipts plus separately evidenced manual collections; settlement is not implied."
              unavailable={money.data?.collection_state.collected.evidence_state !== "AVAILABLE" && money.data?.collection_state.collected.evidence_state !== "MEASURED_ZERO"}
            />
            <MoneyValue
              label="Deposited"
              value={moneyEvidence(
                money.data?.collection_state.deposited.amount,
                money.data?.collection_state.deposited.currency,
                money.data?.collection_state.deposited.evidence_state,
              )}
              detail={money.data?.collection_state.deposited.limitation ?? "No authoritative bank-confirmed deposit evidence."}
              unavailable={money.data?.collection_state.deposited.evidence_state !== "AVAILABLE" && money.data?.collection_state.deposited.evidence_state !== "MEASURED_ZERO"}
            />
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <MoneyValue
              label="New customers"
              value={
                !branchId && analytics.data
                  ? String(analytics.data.new_customers.value)
                  : "Unavailable"
              }
              detail="Company analytics Business Events"
              unavailable={!analytics.data || Boolean(branchId)}
            />
            <MoneyValue
              label="Booked appointments"
              value={
                !branchId && analytics.data
                  ? String(analytics.data.appointments_booked.value)
                  : "Unavailable"
              }
              detail="Company analytics Business Events"
              unavailable={!analytics.data || Boolean(branchId)}
            />
          </div>
        </Panel>
      </div>

      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        <Panel
          title="Booked Jobs"
          description="Scheduled/confirmed Appointment count. Scheduled value awaits complete sold-snapshot linkage."
          icon={CalendarDays}
        >
          <div className="mb-3 flex gap-2">
            {(["day", "week", "month"] as BookedRange[]).map((range) => (
              <button
                className={`min-h-11 rounded-md px-3 text-sm font-semibold ${bookedRange === range ? "bg-action-primary text-white" : "border border-stroke"}`}
                key={range}
                onClick={() => setBookedRange(range)}
                type="button"
              >
                {range[0].toUpperCase() + range.slice(1)}
              </button>
            ))}
          </div>
          <p className="text-3xl font-bold text-action-primary">
            {booked.data?.total_count ?? "Unavailable"}
          </p>
          <p className="mt-1 text-sm text-content-muted">
            Scheduled/confirmed count · value unavailable
          </p>
          <Link
            className="mt-3 inline-flex min-h-11 items-center font-semibold text-action-primary hover:underline"
            to={`/scheduling?date=${today}&view=${bookedRange}&branch=${encodeURIComponent(branchId)}`}
          >
            Open exact schedule
          </Link>
        </Panel>
        <Panel
          title="Card Processing"
          description={`Authoritative captured and provider-settlement evidence for ${today}.`}
          icon={CreditCard}
        >
          {money.isError || !canReadPayments || !money.data ? (
            <Unavailable>Payment authority did not provide current card evidence.</Unavailable>
          ) : (
            <div className="grid gap-3">
              <MoneyValue
                label="Transactions"
                value={String(money.data.card_processing.transaction_count)}
                detail="Captured provider receipts"
              />
              <MoneyValue
                label="Charged"
                value={moneyEvidence(
                  money.data.card_processing.amount_charged.amount,
                  money.data.card_processing.amount_charged.currency,
                  money.data.card_processing.amount_charged.evidence_state,
                )}
                detail="Captured amount; refunds and chargebacks remain separate evidence."
                unavailable={money.data.card_processing.amount_charged.evidence_state !== "AVAILABLE" && money.data.card_processing.amount_charged.evidence_state !== "MEASURED_ZERO"}
              />
              <MoneyValue
                label="Fees"
                value={moneyEvidence(
                  money.data.card_processing.fees_paid.amount,
                  money.data.card_processing.fees_paid.currency,
                  money.data.card_processing.fees_paid.evidence_state,
                )}
                detail={money.data.card_processing.fees_paid.limitation ?? money.data.card_processing.limitation}
                unavailable={money.data.card_processing.fees_paid.evidence_state !== "AVAILABLE" && money.data.card_processing.fees_paid.evidence_state !== "MEASURED_ZERO"}
              />
            </div>
          )}
          <Link
            className="mt-3 inline-flex min-h-11 items-center font-semibold text-action-primary hover:underline"
            to={`/payments?periodStart=${today}&periodEnd=${today}`}
          >
            Open Payments
          </Link>
        </Panel>
        <Panel
          title="Sales Leaderboard"
          description="Only reliable denominators and sales/production lineage may be ranked."
          icon={TrendingUp}
        >
          <Unavailable>
            No qualified salesperson attribution contract is available. ACP will
            not infer performance from incomplete records.
          </Unavailable>
        </Panel>
        <Panel
          title="Timesheet"
          description="Labor consumption belongs beside economic productivity, but Company aggregates require a qualified reporting projection."
          icon={Clock3}
        >
          <Unavailable>
            Today, week, and overtime totals are not available from an
            authoritative Company-level time projection.
          </Unavailable>
          <Link
            className="mt-3 inline-flex min-h-11 items-center font-semibold text-action-primary hover:underline"
            to="/employees"
          >
            Open Time &amp; Attendance
          </Link>
        </Panel>
      </div>

      <footer className="text-xs text-content-muted">
        Scope:{" "}
        {branchId
          ? activeCompany.branches.find((branch) => branch.id === branchId)
              ?.name
          : `${activeCompany.name} · all accessible Branches`}{" "}
        · AR as of{" "}
        {ar.data?.generated_at
          ? new Date(ar.data.generated_at).toLocaleString()
          : "unavailable"}{" "}
        · Jobs as of{" "}
        {jobs.data?.generated_at
          ? new Date(jobs.data.generated_at).toLocaleString()
          : "unavailable"}
        .
      </footer>
    </div>
  );
}
