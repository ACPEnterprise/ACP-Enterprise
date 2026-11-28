import { useState } from "react";
import type {
  QboAccountingEvidenceWorkspace,
  QboAmount,
} from "../../api/qboAccountingEvidence";
import { useQboAccountingEvidence } from "../../hooks/useQboAccountingEvidence";
import { useQboSourceBackedProfitAndLoss } from "../../hooks/useQboAccountingEvidence";
import { useQboSourceBackedArSummary } from "../../hooks/useQboAccountingEvidence";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Select,
  Spinner,
  Input,
} from "../../ui";
import { QboHistoricalArchive } from "./QboHistoricalArchive";

const money = (value: QboAmount) => {
  if (value.amount === null || value.state === "unavailable")
    return "Unavailable";
  const parsed = Number(value.amount);
  return value.currency && Number.isFinite(parsed)
    ? new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: value.currency,
      }).format(parsed)
    : value.amount;
};
const when = (value: string | null) =>
  value === null ? "Unavailable" : new Date(value).toLocaleString();

function Workspace({ value }: { value: QboAccountingEvidenceWorkspace }) {
  const [invoiceFilter, setInvoiceFilter] = useState<"open" | "closed" | "all">(
    "open",
  );
  const [selectedReportKey, setSelectedReportKey] = useState<string | null>(null);
  const selectedReport = value.reports.find((row) => row.report_key === selectedReportKey);
  const arSummary = useQboSourceBackedArSummary(value.as_of ?? "", Boolean(value.as_of));
  const filteredInvoices = value.invoices.filter((invoice) => {
    const amount = Number(invoice.open_balance.amount ?? 0);
    if (invoiceFilter === "open") return amount > 0;
    if (invoiceFilter === "closed") return amount === 0;
    return true;
  });
  const netOpenAr = arSummary.data
    ? ({
        amount: arSummary.data.net_open_ar,
        currency: arSummary.data.currency,
        state: "available" as const,
      } satisfies QboAmount)
    : ({ amount: null, currency: null, state: "unavailable" as const } satisfies QboAmount);
  const grossAmount = Number(value.ar.total_open.amount);
  const netAmount = Number(arSummary.data?.net_open_ar);
  const arSummaryLabel = !arSummary.data
    ? "Net open A/R unavailable"
    : arSummary.data.includes_customer_credits_and_unapplied_payments
      ? "Real total open A/R"
      : "Archive open invoice balance";
  const arSummaryDescription = !arSummary.data
    ? "No source-backed A/R summary was available; no value was inferred"
    : arSummary.data.includes_customer_credits_and_unapplied_payments
      ? "QBO A/R Aging Summary · net of customer credits and unapplied payments"
      : "Sealed invoice Balance fields · credits and unapplied payments require the disclosed A/R bridge";
  const creditOffset =
    arSummary.data?.includes_customer_credits_and_unapplied_payments &&
    Number.isFinite(grossAmount) && Number.isFinite(netAmount)
      ? ({
          amount: (grossAmount - netAmount).toFixed(2),
          currency: value.ar.total_open.currency ?? arSummary.data?.currency ?? null,
          state: "available" as const,
        } satisfies QboAmount)
      : ({ amount: null, currency: null, state: "unavailable" as const } satisfies QboAmount);
  return (
    <div className="space-y-6">
      <Alert
        variant={
          value.refresh_state === "available"
            ? "success"
            : value.refresh_state === "unavailable"
              ? "danger"
              : "warning"
        }
        title={`Source snapshot ${value.refresh_state}`}
      >
        <p>
          QuickBooks Online {value.mode} source-reported evidence ·{" "}
          {value.accounting_basis} basis · as of {when(value.as_of)} · acquired{" "}
          {when(value.acquired_at)}.
        </p>
        <p className="mt-2">
          This is a sealed snapshot, not live synchronization and not posted ACP
          General Ledger truth.
        </p>
      </Alert>
      <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-content-muted">Source company</dt>
          <dd>
            {value.company_identity_sha256
              ? `${value.mode === "live" ? "Verified real company" : "Historical company evidence"} · ${value.company_identity_sha256.slice(0, 12)}`
              : "Company identity unavailable"}
          </dd>
        </div>
        <div>
          <dt className="text-content-muted">Basis</dt>
          <dd className="capitalize">{value.accounting_basis}</dd>
        </div>
        <div>
          <dt className="text-content-muted">As-of time</dt>
          <dd>{when(value.as_of)}</dd>
        </div>
        <div>
          <dt className="text-content-muted">Completeness / refresh</dt>
          <dd className="capitalize">
            {value.completeness} · {value.refresh_state}
          </dd>
        </div>
      </dl>
      {value.limitations.length ? (
        <Alert variant="warning" title="Evidence limitations">
          <ul className="list-disc space-y-1 pl-5">
            {value.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </Alert>
      ) : null}
      {value.historical_reconciliation ? (
        <Card>
          <CardHeader>
            <CardTitle>Historical accounting reconciliation</CardTitle>
            <CardDescription>
              Sealed, read-only source evidence reconciled with disclosed
              exceptions. No records were posted to TwelveHats or QuickBooks.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-3 text-sm sm:grid-cols-3 lg:grid-cols-6">
              <div>
                <dt className="text-content-muted">Source records</dt>
                <dd>{value.historical_reconciliation.source_record_count.toLocaleString()}</dd>
              </div>
              <div>
                <dt className="text-content-muted">Relationships</dt>
                <dd>{value.historical_reconciliation.relationship_id_count.toLocaleString()}</dd>
              </div>
              <div>
                <dt className="text-content-muted">Customers</dt>
                <dd>{value.historical_reconciliation.customer_count.toLocaleString()}</dd>
              </div>
              <div>
                <dt className="text-content-muted">Invoices / lines</dt>
                <dd>{value.historical_reconciliation.invoice_count.toLocaleString()} / {value.historical_reconciliation.invoice_line_count.toLocaleString()}</dd>
              </div>
              <div>
                <dt className="text-content-muted">Payment→invoice links</dt>
                <dd>{value.historical_reconciliation.payment_invoice_links.toLocaleString()} · {value.historical_reconciliation.missing_payment_invoice_links} missing</dd>
              </div>
              <div>
                <dt className="text-content-muted">Disclosed conflicts</dt>
                <dd>{value.historical_reconciliation.conflict_count}</dd>
              </div>
            </dl>
          </CardContent>
        </Card>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle>Accounts and source balances</CardTitle>
          <CardDescription>
            Missing balances remain unavailable; QBO balances are never
            presented as ACP-posted balances.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {value.accounts.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left">
                    <th>Account</th>
                    <th>Type</th>
                    <th>Source balance</th>
                    <th>Evidence state</th>
                    <th>Source ID</th>
                  </tr>
                </thead>
                <tbody>
                  {value.accounts.map((row) => (
                    <tr className="border-b border-stroke" key={row.source_id}>
                      <td className="py-2">{row.name}</td>
                      <td>
                        {row.account_type}
                        {row.account_subtype ? ` · ${row.account_subtype}` : ""}
                      </td>
                      <td>{money(row.balance)}</td>
                      <td className="capitalize">{row.balance.state}</td>
                      <td className="font-mono text-xs">{row.source_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-content-muted">
              Account evidence is unavailable. No zero balance was inferred.
            </p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Bills and AP evidence</CardTitle>
          <CardDescription>
            QBO source obligations only. They are not posted ACP AP or proof of
            disbursement.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {value.bills.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left">
                    <th>Document</th>
                    <th>Vendor</th>
                    <th>Date / due</th>
                    <th>Provider workflow</th>
                    <th>Total</th>
                    <th>Open</th>
                    <th>Source ID</th>
                  </tr>
                </thead>
                <tbody>
                  {value.bills.map((row) => (
                    <tr className="border-b border-stroke" key={row.source_id}>
                      <td className="py-2">
                        {row.document_number ?? "Unavailable"}
                      </td>
                      <td>{row.vendor_label ?? "Unavailable"}</td>
                      <td>
                        {row.transaction_date ?? "Unavailable"} /{" "}
                        {row.due_date ?? "Unavailable"}
                      </td>
                      <td>{row.source_status ?? "Unavailable"}</td>
                      <td>{money(row.total)}</td>
                      <td>{money(row.open_balance)}</td>
                      <td className="font-mono text-xs">{row.source_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-content-muted">
              Bill/AP evidence is unavailable. No obligation was inferred.
            </p>
          )}
        </CardContent>
      </Card>
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader><CardTitle>Actually open invoices</CardTitle></CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{value.ar.open_invoice_count}</p>
            <p className="text-sm text-content-muted">QBO invoices with Balance &gt; $0</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Gross open invoice balances</CardTitle></CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{money(value.ar.total_open)}</p>
            <p className="text-sm text-content-muted">Sum of positive QBO Invoice Balance fields</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>{arSummaryLabel}</CardTitle></CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{arSummary.isLoading ? "Loading…" : money(netOpenAr)}</p>
            <p className="text-sm text-content-muted">{arSummaryDescription}</p>
            {arSummary.isError ? (
              <div className="mt-3 space-y-2">
                <p className="text-sm text-status-warning">
                  The read-only source A/R projection is unavailable. No balance
                  was inferred and no native Accounting record was changed.
                </p>
                <Button
                  onClick={() => void arSummary.refetch()}
                  size="small"
                  type="button"
                  variant="secondary"
                >
                  Retry read-only A/R
                </Button>
              </div>
            ) : null}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Credits/payment offset</CardTitle></CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{money(creditOffset)}</p>
            <p className="text-sm text-content-muted">Gross invoice balances minus QBO net A/R</p>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>QBO source invoice history</CardTitle>
          <CardDescription>
            This is the complete acquired invoice population, not a list of open
            invoices. Default view shows only invoices with a positive QBO Balance.
            Provider workflow reflects print/email delivery state, not whether an
            invoice is paid.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {value.invoices.length ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-end gap-3">
                <label>
                  <span className="mb-1 block text-sm text-content-muted">Invoice view</span>
                  <Select value={invoiceFilter} onChange={(event) => setInvoiceFilter(event.target.value as "open" | "closed" | "all")}>
                    <option value="open">Open only ({value.ar.open_invoice_count})</option>
                    <option value="closed">Paid/closed ({value.ar.closed_invoice_count})</option>
                    <option value="all">All source invoices ({value.ar.invoice_evidence_count})</option>
                  </Select>
                </label>
                <p className="text-sm text-content-muted">Showing {filteredInvoices.length} invoices</p>
              </div>
              <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left">
                    <th>Document</th>
                    <th>Customer</th>
                    <th>Date / due</th>
                    <th>Provider workflow</th>
                    <th>Total</th>
                    <th>Open</th>
                    <th>Source ID</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredInvoices.map((row) => (
                    <tr className="border-b border-stroke" key={row.source_id}>
                      <td className="py-2">
                        {row.document_number ?? "Unavailable"}
                      </td>
                      <td>{row.customer_label ?? "Unavailable"}</td>
                      <td>
                        {row.transaction_date ?? "Unavailable"} /{" "}
                        {row.due_date ?? "Unavailable"}
                      </td>
                      <td>{row.source_status ?? "Unavailable"}</td>
                      <td>{money(row.total)}</td>
                      <td>{money(row.open_balance)}</td>
                      <td className="font-mono text-xs">{row.source_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </div>
          ) : (
            <p className="text-content-muted">
              Invoice/AR evidence is unavailable. No amount was inferred.
            </p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Cross-source conflicts</CardTitle>
          <CardDescription>
            QBO, HCP, and ACP assertions remain separate. This workspace never
            chooses a winner or combines conflicting values.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {value.conflicts.length ? (
            <ul className="divide-y divide-stroke">
              {value.conflicts.map((conflict) => (
                <li className="space-y-1 py-3" key={conflict.conflict_id}>
                  <p className="font-medium">
                    {conflict.subject_label} · {conflict.fact_name} ·{" "}
                    <span className="capitalize">{conflict.state}</span>
                  </p>
                  {conflict.source_assertions.map((assertion) => (
                    <p
                      className="text-sm text-content-muted"
                      key={`${conflict.conflict_id}-${assertion.source}`}
                    >
                      {assertion.source.toUpperCase()}:{" "}
                      {assertion.value ?? "Unavailable"} · source date{" "}
                      {assertion.source_date ?? "Unavailable"}
                    </p>
                  ))}
                  <p className="text-sm text-content-muted">
                    {conflict.limitation}
                  </p>
                  {conflict.evidence?.length ? (
                    <p className="text-sm text-content-muted">
                      Evidence: {conflict.evidence.map((item) => `${item.name}=${item.value}`).join(" · ")}
                    </p>
                  ) : null}
                  {conflict.next_action ? (
                    <p className="text-sm">
                      <strong>Next action:</strong> {conflict.next_action}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-content-muted">
              No cross-source conflict packet is available for this snapshot.
              Absence does not prove reconciliation.
            </p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Payment and application evidence</CardTitle>
          <CardDescription>
            Payment evidence does not imply funds settled, moved, or were posted
            in ACP.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {value.payments.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left">
                    <th>Date</th>
                    <th>Customer</th>
                    <th>Amount</th>
                    <th>Status</th>
                    <th>Application</th>
                    <th>Source ID</th>
                  </tr>
                </thead>
                <tbody>
                  {value.payments.map((row) => (
                    <tr className="border-b border-stroke" key={row.source_id}>
                      <td className="py-2">
                        {row.transaction_date ?? "Unavailable"}
                      </td>
                      <td>{row.customer_label ?? "Unavailable"}</td>
                      <td>{money(row.amount)}</td>
                      <td>{row.source_status ?? "Unavailable"}</td>
                      <td>
                        {row.application_state}
                        {row.applied_document_ids.length
                          ? ` · ${row.applied_document_ids.length} document(s)`
                          : ""}
                      </td>
                      <td className="font-mono text-xs">{row.source_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-content-muted">
              Payment evidence is unavailable. No receipt or settlement was
              inferred.
            </p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Available source reports</CardTitle>
          <CardDescription>
            Each report retains its basis, as-of time, and readiness.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {value.reports.length ? (
            <ul className="divide-y divide-stroke">
              {value.reports.map((row) => (
                <li className="py-3" key={row.report_key}>
                  <button className="min-h-11 text-left font-medium text-action-primary" type="button" onClick={() => setSelectedReportKey(row.report_key)}>Open {row.label}</button>
                  <p className="text-sm text-content-muted">
                    {row.basis ?? "Basis unavailable"} · as of {when(row.as_of)}{" "}
                    · {row.state}
                    {row.limitation ? ` · ${row.limitation}` : ""}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-content-muted">
              No QBO source reports are available in this snapshot.
            </p>
          )}
          {selectedReport && <section aria-label="QBO historical report detail" className="mt-4 rounded-lg border border-stroke bg-surface-subtle p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="font-semibold">{selectedReport.label}</h4><span className="rounded-full bg-status-info/15 px-2 py-1 text-xs text-status-info">QBO SOURCE BACKED</span></div><dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2"><div><dt className="text-content-muted">Report source key</dt><dd className="font-mono">{selectedReport.report_key}</dd></div><div><dt className="text-content-muted">Basis</dt><dd>{selectedReport.basis ?? "Unavailable"}</dd></div><div><dt className="text-content-muted">As of</dt><dd>{when(selectedReport.as_of)}</dd></div><div><dt className="text-content-muted">Evidence state</dt><dd>{selectedReport.state}</dd></div></dl><p className="mt-3 text-sm text-content-muted">{selectedReport.limitation ?? "No report-specific limitation was supplied; snapshot-level limitations still apply."}</p><p className="mt-2 text-xs text-content-muted">Read-only · accepted as ACP Accounting: no · no posting authority</p></section>}
        </CardContent>
      </Card>
      <p className="break-all text-xs text-content-muted">
        Contract {value.contract_version} · snapshot{" "}
        {value.snapshot_id ?? "unavailable"} · digest{" "}
        {value.snapshot_digest ?? "unavailable"} · source manifest{" "}
        {value.source_manifest_sha256 ?? "unavailable"} · read-only evidence
      </p>
    </div>
  );
}

export function QboSourceEvidence({ enabled }: { enabled: boolean }) {
  const [basis, setBasis] = useState<"cash" | "accrual">("cash");
  const [startDate, setStartDate] = useState("2026-05-01");
  const [endDate, setEndDate] = useState("2026-05-31");
  const [reportRequest, setReportRequest] = useState<{
    startDate: string;
    endDate: string;
    basis: "cash" | "accrual";
  }>({
    startDate: "2026-05-01",
    endDate: "2026-05-31",
    basis: "cash",
  });
  const evidence = useQboAccountingEvidence(basis, enabled);
  const sourceReport = useQboSourceBackedProfitAndLoss(reportRequest, enabled);
  return (
    <section aria-label="QuickBooks source evidence" className="space-y-4">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
        <div>
          <h2 className="text-xl font-semibold">QuickBooks source evidence</h2>
          <p className="text-sm text-content-muted">
            Verified real-company, read-only snapshot evidence. Kept separate
            from ACP native Accounting and HCP operational evidence.
          </p>
        </div>
        <Select
          aria-label="QBO report basis"
          className="sm:w-44"
          value={basis}
          onChange={(event) =>
            setBasis(event.target.value as "cash" | "accrual")
          }
        >
          <option value="cash">Cash basis</option>
          <option value="accrual">Accrual basis</option>
        </Select>
      </div>
      {evidence.isPending ? (
        <Spinner label="Loading QuickBooks source evidence" />
      ) : evidence.isError || !evidence.data ? (
        <Alert variant="warning" title="QuickBooks evidence unavailable">
          <div className="space-y-3">
            <p>
              The verified source snapshot could not be loaded. ACP did not
              infer zeros or substitute native/HCP data.
            </p>
            <Button
              variant="secondary"
              type="button"
              onClick={() => void evidence.refetch()}
            >
              Retry source evidence
            </Button>
          </div>
        </Alert>
      ) : (
        <Workspace value={evidence.data} />
      )}
      <QboHistoricalArchive enabled={enabled} />
      <Card>
        <CardHeader>
          <CardTitle>Real-company Profit &amp; Loss</CardTitle>
          <CardDescription>
            GET-only QuickBooks Production report. This remains QBO
            source-backed evidence and is never represented as an ACP-posted
            financial statement.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form
            className="grid gap-3 sm:grid-cols-4"
            onSubmit={(event) => {
              event.preventDefault();
              setReportRequest({ startDate, endDate, basis });
            }}
          >
            <Input
              aria-label="QBO report start date"
              type="date"
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
            />
            <Input
              aria-label="QBO report end date"
              type="date"
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
            />
            <Select
              aria-label="QBO Profit and Loss basis"
              value={basis}
              onChange={(event) =>
                setBasis(event.target.value as "cash" | "accrual")
              }
            >
              <option value="cash">Cash basis</option>
              <option value="accrual">Accrual basis</option>
            </Select>
            <Button type="submit">Run source-backed report</Button>
          </form>
          {sourceReport.isPending ? (
            <Spinner label="Loading QBO Profit and Loss" />
          ) : sourceReport.isError || !sourceReport.data ? (
            <Alert variant="warning" title="QBO Profit & Loss unavailable">
              The requested provider report could not be read. No ACP-native
              statement or inferred value was substituted.
            </Alert>
          ) : (
            <div className="space-y-4">
              <Alert variant="success" title="QBO_SOURCE_BACKED">
                {sourceReport.data.source_company} · Production realm{" "}
                {sourceReport.data.realm_id}
                {" · "}
                {sourceReport.data.start_date}–{sourceReport.data.end_date}
                {" · "}
                {sourceReport.data.accounting_basis} basis · acquired{" "}
                {when(sourceReport.data.acquired_at)}.
              </Alert>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left">
                      {sourceReport.data.columns.map((column, index) => (
                        <th key={`${column}-${index}`}>{column || "Value"}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sourceReport.data.rows.map((row, rowIndex) => (
                      <tr
                        className={
                          row.kind === "summary"
                            ? "border-t border-stroke font-semibold"
                            : "border-b border-stroke"
                        }
                        key={`${row.kind}-${rowIndex}`}
                      >
                        {sourceReport.data.columns.map((_, columnIndex) => (
                          <td
                            className="py-2"
                            key={columnIndex}
                            style={
                              columnIndex === 0
                                ? { paddingLeft: `${row.depth * 1.25}rem` }
                                : undefined
                            }
                          >
                            {row.values[columnIndex] ?? ""}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="break-all text-xs text-content-muted">
                Source as-of{" "}
                {sourceReport.data.source_as_of ??
                  "provider response time unavailable"}
                {" · digest "}
                {sourceReport.data.source_digest}
                {" · accepted as ACP Accounting: no · mutation authority: none"}
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
