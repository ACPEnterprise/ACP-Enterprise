import { useState } from "react";
import { Link } from "react-router";

import { useHasPermission } from "../auth";
import type {
  QboAccountingEvidenceWorkspace,
  QboAmount,
} from "../api/qboAccountingEvidence";
import type {
  QboReviewItem,
  QboSourceEvidenceReadiness,
} from "../api/qboNativeApplication";
import {
  useQboAccountingEvidence,
  useQboSourceBackedArSummary,
} from "../hooks/useQboAccountingEvidence";
import {
  useQboApplicationLedger,
  useQboReviewQueue,
} from "../hooks/useQboNativeApplication";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Spinner,
} from "../ui";

type Section =
  | "source"
  | "opening"
  | "ar"
  | "ap"
  | "payroll"
  | "inventory"
  | "reports"
  | "exceptions";

const sections: readonly [Section, string][] = [
  ["source", "Source"],
  ["opening", "Opening Balances"],
  ["ar", "A/R"],
  ["ap", "A/P"],
  ["payroll", "Payroll"],
  ["inventory", "Inventory"],
  ["reports", "Report Parity"],
  ["exceptions", "Exceptions"],
];
const label = (value: string) =>
  value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/^./, (letter) => letter.toUpperCase());
const when = (value: string | null | undefined) =>
  value ? new Date(value).toLocaleString() : "Unavailable";
const money = (value: QboAmount) =>
  value.amount === null || !value.currency
    ? "Unavailable"
    : new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: value.currency,
      }).format(Number(value.amount));

export function QboCutoverRoute() {
  const canRead = useHasPermission("COMPANY_ACCOUNTING_REPORT_READ");
  const canReconcile = useHasPermission("COMPANY_ACCOUNTING_RECONCILE");
  const evidence = useQboAccountingEvidence("accrual", canRead);
  const ledger = useQboApplicationLedger(canRead);
  const review = useQboReviewQueue(canReconcile);
  const reportDate = evidence.data?.as_of?.slice(0, 10) ?? "";
  const arSummary = useQboSourceBackedArSummary(
    reportDate,
    canRead && Boolean(reportDate),
  );
  const [section, setSection] = useState<Section>("source");

  if (!canRead)
    return (
      <Alert variant="danger">
        Accounting report permission is required to review QuickBooks cutover
        evidence.
      </Alert>
    );
  if (evidence.isLoading || ledger.isLoading)
    return <Spinner label="Loading QuickBooks cutover evidence" />;
  if (evidence.isError || ledger.isError || !evidence.data || !ledger.data)
    return (
      <Alert variant="danger">
        QuickBooks cutover evidence is unavailable. No missing balance has been
        treated as zero.
      </Alert>
    );
  const source = evidence.data;
  const custody = ledger.data.source_evidence;

  return (
    <div className="mx-auto max-w-7xl space-y-6 pb-12">
      <header>
        <p className="text-sm font-semibold text-action-primary">Accounting</p>
        <h1 className="text-2xl font-bold sm:text-3xl">QuickBooks Cutover</h1>
        <p className="mt-2 text-content-muted">
          Review source custody, opening-state readiness, control differences,
          and accountant exceptions without changing QuickBooks or posting
          Accounting.
        </p>
      </header>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatusCard
          title="Source package"
          state={custody.available ? "available" : "unavailable"}
          detail={
            custody.available
              ? `${custody.total_source_records ?? 0} records acquired`
              : (custody.reason ?? "Source package unavailable")
          }
        />
        <StatusCard
          title="Opening balances"
          state="unavailable"
          detail="Opening-package review contract required"
        />
        <StatusCard
          title="A/R control"
          state={arSummary.data ? "source available" : "incomplete"}
          detail="Control-to-subledger result required"
        />
        <StatusCard
          title="A/P control"
          state={source.bills.length ? "source available" : "incomplete"}
          detail="Control-to-subledger result required"
        />
      </div>
      <nav
        aria-label="QuickBooks cutover sections"
        className="flex flex-wrap gap-2"
      >
        {sections.map(([value, text]) => (
          <Button
            key={value}
            variant={section === value ? "primary" : "secondary"}
            onClick={() => setSection(value)}
          >
            {text}
          </Button>
        ))}
      </nav>
      {section === "source" && (
        <SourceReview source={source} custody={custody} />
      )}
      {section === "opening" && <OpeningReview accounts={source.accounts} />}
      {section === "ar" && (
        <ArReview
          source={source}
          netOpenAr={arSummary.data?.net_open_ar ?? null}
          currency={arSummary.data?.currency ?? null}
          loading={arSummary.isLoading}
        />
      )}
      {section === "ap" && <ApReview source={source} />}
      {section === "payroll" && (
        <GatedSection
          title="Payroll accounting review"
          message="The current QBO cutover contract does not expose Payroll opening-liability reconciliation here."
          destination="/payroll"
          destinationLabel="Open Payroll readiness"
        />
      )}
      {section === "inventory" && (
        <GatedSection
          title="Inventory and Job Cost review"
          message="The current QBO cutover contract does not expose inventory opening-value or Job Cost reconciliation here."
          destination="/inventory"
          destinationLabel="Open Inventory"
        />
      )}
      {section === "reports" && (
        <GatedSection
          title="Report parity"
          message="Use Financial Reports for native posted reports. A cutoff-matched QBO-to-ACP parity result is not yet exposed."
          destination="/financial-reports"
          destinationLabel="Open Financial Reports"
        />
      )}
      {section === "exceptions" && (
        <ExceptionReview
          canReconcile={canReconcile}
          loading={review.isLoading}
          failed={review.isError}
          items={review.data ?? []}
        />
      )}
    </div>
  );
}

function StatusCard({
  title,
  state,
  detail,
}: {
  title: string;
  state: string;
  detail: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <Badge
          variant={
            state === "available"
              ? "success"
              : state === "unavailable"
                ? "warning"
                : "neutral"
          }
        >
          {label(state)}
        </Badge>
        <p className="mt-2 text-sm text-content-muted">{detail}</p>
      </CardContent>
    </Card>
  );
}

function SourceReview({
  source,
  custody,
}: {
  source: QboAccountingEvidenceWorkspace;
  custody: QboSourceEvidenceReadiness;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Source and cutoff review</CardTitle>
        <CardDescription>
          Sealed, read-only QuickBooks evidence. Credentials and provider
          secrets are never shown.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Fact
            name="Source company"
            value={
              source.company_identity_sha256
                ? `Verified identity ${source.company_identity_sha256.slice(0, 12)}`
                : "Unavailable"
            }
          />
          <Fact
            name="Provider environment"
            value={label(source.provider_environment)}
          />
          <Fact name="Source as of" value={when(source.as_of)} />
          <Fact name="Acquired" value={when(source.acquired_at)} />
          <Fact
            name="Cutoff"
            value={source.as_of?.slice(0, 10) ?? "Unavailable"}
          />
          <Fact
            name="Package status"
            value={custody.available ? "Available" : "Unavailable"}
          />
          <Fact name="Completeness" value={label(source.completeness)} />
          <Fact
            name="Replay / digest"
            value={
              source.snapshot_digest
                ? `Digest verified · ${source.snapshot_digest.slice(0, 12)}`
                : "Unavailable"
            }
          />
        </dl>
        {source.limitations.length ? (
          <Alert variant="warning" title="Unresolved source gaps">
            <ul className="list-disc pl-5">
              {source.limitations.map((item) => (
                <li key={item}>{label(item)}</li>
              ))}
            </ul>
          </Alert>
        ) : (
          <Alert variant="success">
            No limitation is reported by the current source projection.
          </Alert>
        )}
        <details>
          <summary>Technical provenance</summary>
          <p className="break-all text-xs">
            Manifest {source.source_manifest_sha256 ?? "unavailable"} · Snapshot{" "}
            {source.snapshot_id ?? "unavailable"}
          </p>
        </details>
      </CardContent>
    </Card>
  );
}

function OpeningReview({
  accounts,
}: {
  accounts: QboAccountingEvidenceWorkspace["accounts"];
}) {
  return (
    <div className="space-y-4">
      <Alert
        variant="warning"
        title="Opening Trial Balance review is not yet authoritative"
      >
        The server does not expose a cutoff-scoped opening package with debit,
        credit, equity classification, exceptions, balance status, or approval
        state. Approval remains unavailable.
      </Alert>
      <Card>
        <CardHeader>
          <CardTitle>Source account balances</CardTitle>
          <CardDescription>
            Reference-only QBO balances. These are not an opening Trial Balance
            and are not converted into debits or credits in the browser.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[42rem] text-left text-sm">
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Type</th>
                  <th>Source balance</th>
                  <th>Evidence state</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((account) => (
                  <tr
                    className="border-t border-stroke"
                    key={account.source_id}
                  >
                    <td>{account.name}</td>
                    <td>
                      {account.account_type}
                      {account.account_subtype
                        ? ` · ${account.account_subtype}`
                        : ""}
                    </td>
                    <td>{money(account.balance)}</td>
                    <td>{label(account.balance.state)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!accounts.length && (
            <p className="py-6 text-content-muted">
              Account evidence is unavailable. No zero balance was inferred.
            </p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Opening equity</CardTitle>
          <CardDescription>
            Retained earnings, owner equity, legitimate opening-balance equity,
            and unexplained difference require canonical classification.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Badge variant="warning">Needs server projection</Badge>
          <p className="mt-2 text-sm">
            No plug or unexplained difference is hidden or calculated locally.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function ArReview({
  source,
  netOpenAr,
  currency,
  loading,
}: {
  source: QboAccountingEvidenceWorkspace;
  netOpenAr: string | null;
  currency: string | null;
  loading: boolean;
}) {
  return (
    <div className="space-y-4">
      <Alert variant="warning" title="A/R control reconciliation is incomplete">
        QBO source invoices and net aged A/R are available, but the server does
        not expose the native A/R control balance, Customer subledger total,
        difference, or canonical exception dispositions.
      </Alert>
      <div className="grid gap-3 sm:grid-cols-3">
        <Metric
          name="QBO net open A/R"
          value={
            loading
              ? "Loading…"
              : netOpenAr !== null && currency
                ? new Intl.NumberFormat(undefined, {
                    style: "currency",
                    currency,
                  }).format(Number(netOpenAr))
                : "Unavailable"
          }
        />
        <Metric
          name="Open source invoices"
          value={String(source.ar.open_invoice_count)}
        />
        <Metric
          name="Source evidence count"
          value={String(source.ar.invoice_evidence_count)}
        />
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Customer invoice evidence</CardTitle>
          <CardDescription>
            Source drill-down only; this is not an ACP control-account tie.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[58rem] text-left text-sm">
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Invoice</th>
                  <th>Date</th>
                  <th>Due</th>
                  <th>Total</th>
                  <th>Open balance</th>
                  <th>Source status</th>
                </tr>
              </thead>
              <tbody>
                {source.invoices.map((row) => (
                  <tr className="border-t border-stroke" key={row.source_id}>
                    <td>{row.customer_label ?? "Unavailable"}</td>
                    <td>{row.document_number ?? "Unavailable"}</td>
                    <td>{row.transaction_date ?? "Unavailable"}</td>
                    <td>{row.due_date ?? "Unavailable"}</td>
                    <td>{money(row.total)}</td>
                    <td>{money(row.open_balance)}</td>
                    <td>{row.source_status ?? "Unavailable"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!source.invoices.length && (
            <p className="py-6 text-content-muted">
              Invoice evidence is unavailable. No receivable was inferred.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function ApReview({
  source,
}: {
  source: QboAccountingEvidenceWorkspace;
}) {
  return (
    <div className="space-y-4">
      <Alert
        variant="warning"
        title="A/P control reconciliation is unavailable"
      >
        The source projection includes bills, but no canonical A/P control
        balance, Vendor subledger total, difference, or exception result.
      </Alert>
      <Card>
        <CardHeader>
          <CardTitle>Vendor bill evidence</CardTitle>
          <CardDescription>
            Source drill-down only; no missing bill or balance is treated as
            zero.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[58rem] text-left text-sm">
              <thead>
                <tr>
                  <th>Vendor</th>
                  <th>Bill</th>
                  <th>Date</th>
                  <th>Due</th>
                  <th>Total</th>
                  <th>Open balance</th>
                  <th>Source status</th>
                </tr>
              </thead>
              <tbody>
                {source.bills.map((row) => (
                  <tr className="border-t border-stroke" key={row.source_id}>
                    <td>{row.vendor_label ?? "Unavailable"}</td>
                    <td>{row.document_number ?? "Unavailable"}</td>
                    <td>{row.transaction_date ?? "Unavailable"}</td>
                    <td>{row.due_date ?? "Unavailable"}</td>
                    <td>{money(row.total)}</td>
                    <td>{money(row.open_balance)}</td>
                    <td>{row.source_status ?? "Unavailable"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!source.bills.length && (
            <p className="py-6 text-content-muted">
              Bill evidence is unavailable. No payable was inferred.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function ExceptionReview({
  canReconcile,
  loading,
  failed,
  items,
}: {
  canReconcile: boolean;
  loading: boolean;
  failed: boolean;
  items: QboReviewItem[];
}) {
  if (!canReconcile)
    return (
      <Alert variant="warning">
        Accounting reconciliation permission is required to inspect the
        accountant exception queue.
      </Alert>
    );
  if (loading) return <Spinner label="Loading accountant exceptions" />;
  if (failed)
    return <Alert variant="danger">The exception queue is unavailable.</Alert>;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Accountant review queue</CardTitle>
        <CardDescription>
          Specific source conflicts from the canonical review service. Approval
          and resolution remain in the governed QuickBooks Migration workflow.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.map((item) => (
          <article
            className="rounded-lg border border-stroke p-3"
            key={item.id}
          >
            <div className="flex flex-wrap justify-between gap-2">
              <strong>
                {label(item.source_family)} ·{" "}
                {item.reference_number ?? item.provider_record_id}
              </strong>
              <Badge variant="warning">{label(item.state)}</Badge>
            </div>
            <p className="mt-2 text-sm">{item.exact_conflict}</p>
            <p className="mt-1 text-xs text-content-muted">
              Required authority:{" "}
              {item.allowed_actions
                .map((action) => label(action.required_authority))
                .join(", ") || "Unavailable"}{" "}
              · unlocks {item.unlocks} records
            </p>
          </article>
        ))}
        {!items.length && (
          <p>No source reconciliation exceptions are currently reported.</p>
        )}
        <Link
          className="inline-flex font-semibold text-action-primary"
          to="/accounting/quickbooks-migration"
        >
          Open governed exception decisions
        </Link>
      </CardContent>
    </Card>
  );
}

function GatedSection({
  title,
  message,
  destination,
  destinationLabel,
}: {
  title: string;
  message: string;
  destination: string;
  destinationLabel: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <Alert variant="warning">{message}</Alert>
        <Link
          className="mt-4 inline-flex font-semibold text-action-primary"
          to={destination}
        >
          {destinationLabel}
        </Link>
      </CardContent>
    </Card>
  );
}
function Fact({ name, value }: { name: string; value: string }) {
  return (
    <div>
      <dt className="text-content-muted">{name}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}
function Metric({ name, value }: { name: string; value: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{name}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-bold tabular-nums">{value}</p>
      </CardContent>
    </Card>
  );
}
