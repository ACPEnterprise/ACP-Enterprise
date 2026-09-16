import { useMemo, useState } from "react";
import type {
  QboAccountingEvidenceWorkspace,
  QboAmount,
} from "../../api/qboAccountingEvidence";
import { useQboAccountingEvidence } from "../../hooks/useQboAccountingEvidence";
import { useQboSourceBackedProfitAndLoss } from "../../hooks/useQboAccountingEvidence";
import { useQboSourceBackedArSummary } from "../../hooks/useQboAccountingEvidence";
import { useQboSourceBackedGeneralLedger } from "../../hooks/useQboAccountingEvidence";
import { FinanceSourceCenter } from "./FinanceSourceCenter";
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

type PeriodPreset =
  "this-month" | "last-month" | "quarter" | "ytd" | "prior-year";

const isoDate = (value: Date) => value.toISOString().slice(0, 10);
const periodFor = (preset: PeriodPreset, now = new Date()) => {
  const year = now.getUTCFullYear();
  const month = now.getUTCMonth();
  if (preset === "this-month")
    return {
      start: isoDate(new Date(Date.UTC(year, month, 1))),
      end: isoDate(now),
    };
  if (preset === "last-month")
    return {
      start: isoDate(new Date(Date.UTC(year, month - 1, 1))),
      end: isoDate(new Date(Date.UTC(year, month, 0))),
    };
  if (preset === "quarter") {
    const quarterMonth = Math.floor(month / 3) * 3;
    return {
      start: isoDate(new Date(Date.UTC(year, quarterMonth, 1))),
      end: isoDate(now),
    };
  }
  if (preset === "prior-year")
    return { start: `${year - 1}-01-01`, end: `${year - 1}-12-31` };
  return { start: `${year}-01-01`, end: isoDate(now) };
};

const csvCell = (value: string) => `"${value.replaceAll('"', '""')}"`;

function GeneralLedgerEvidence({ enabled }: { enabled: boolean }) {
  const [startDate, setStartDate] = useState("2026-05-01");
  const [endDate, setEndDate] = useState("2026-05-31");
  const [basis, setBasis] = useState<"cash" | "accrual">("accrual");
  const [offset, setOffset] = useState(0);
  const [request, setRequest] = useState({
    startDate,
    endDate,
    basis,
    limit: 50,
    offset: 0,
  });
  const ledger = useQboSourceBackedGeneralLedger(request, enabled);
  const page = (nextOffset: number) => {
    setOffset(nextOffset);
    setRequest((current) => ({ ...current, offset: nextOffset }));
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>Sealed General Ledger evidence</CardTitle>
        <CardDescription>
          Bounded rows from a digest-verified acquired QBO report. No provider
          call and no ACP posting.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          className="grid gap-3 sm:grid-cols-4"
          onSubmit={(event) => {
            event.preventDefault();
            setOffset(0);
            setRequest({ startDate, endDate, basis, limit: 50, offset: 0 });
          }}
        >
          <Input
            aria-label="General Ledger start date"
            type="date"
            required
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
          />
          <Input
            aria-label="General Ledger end date"
            type="date"
            min={startDate}
            required
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
          />
          <Select
            aria-label="General Ledger basis"
            value={basis}
            onChange={(event) =>
              setBasis(event.target.value as "cash" | "accrual")
            }
          >
            <option value="accrual">Accrual basis</option>
            <option value="cash">Cash basis</option>
          </Select>
          <Button type="submit">Open ledger evidence</Button>
        </form>
        {ledger.isPending ? (
          <Spinner label="Loading General Ledger evidence" />
        ) : ledger.isError || !ledger.data ? (
          <Alert variant="warning" title="General Ledger evidence unavailable">
            ACP has no sealed General Ledger control covering{" "}
            {request.startDate}–{request.endDate} on the {request.basis} basis,
            or the evidence failed digest validation. Acquire the required
            source report; no rows or zero totals were inferred.
          </Alert>
        ) : (
          <>
            <Alert
              variant="information"
              title="QBO SOURCE EVIDENCE — not ACP-native"
            >
              Showing {ledger.data.offset + 1}–
              {Math.min(
                ledger.data.offset + ledger.data.rows.length,
                ledger.data.total_count,
              )}{" "}
              of {ledger.data.total_count} rows ·{" "}
              {ledger.data.period.start_date}–{ledger.data.period.end_date} ·{" "}
              {ledger.data.accounting_basis} basis.
            </Alert>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[58rem] text-sm">
                <thead>
                  <tr className="text-left">
                    <th>Date</th>
                    <th>Account</th>
                    <th>Type</th>
                    <th>Counterparty</th>
                    <th>Number</th>
                    <th>Description</th>
                    <th className="text-right">Source amount</th>
                  </tr>
                </thead>
                <tbody>
                  {ledger.data.rows.map((row, index) => (
                    <tr
                      className="border-b border-stroke"
                      key={`${row.date}-${row.account}-${row.transaction_number ?? index}`}
                    >
                      <td className="py-2">{row.date}</td>
                      <td>{row.account}</td>
                      <td>{row.transaction_type}</td>
                      <td>{row.counterparty ?? "Not supplied"}</td>
                      <td>{row.transaction_number ?? "Not supplied"}</td>
                      <td>{row.description ?? "Not supplied"}</td>
                      <td className="text-right tabular-nums">{row.amount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between gap-3">
              <Button
                type="button"
                variant="secondary"
                disabled={offset === 0}
                onClick={() => page(Math.max(0, offset - 50))}
              >
                Previous
              </Button>
              <span className="text-sm text-content-muted">
                At most 50 source rows per page
              </span>
              <Button
                type="button"
                variant="secondary"
                disabled={offset + 50 >= ledger.data.total_count}
                onClick={() => page(offset + 50)}
              >
                Next
              </Button>
            </div>
            <p className="break-all text-xs text-content-muted">
              Control {ledger.data.control_id} · registration{" "}
              {ledger.data.registration_sha256} · source digest{" "}
              {ledger.data.raw_sha256} · mutation authority: none
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function Workspace({ value }: { value: QboAccountingEvidenceWorkspace }) {
  const [invoiceFilter, setInvoiceFilter] = useState<"open" | "closed" | "all">(
    "open",
  );
  const [accountSearch, setAccountSearch] = useState("");
  const [accountType, setAccountType] = useState("all");
  const arSummary = useQboSourceBackedArSummary(
    value.as_of ?? "",
    Boolean(value.as_of),
  );
  const filteredInvoices = value.invoices.filter((invoice) => {
    const amount = Number(invoice.open_balance.amount ?? 0);
    if (invoiceFilter === "open") return amount > 0;
    if (invoiceFilter === "closed") return amount === 0;
    return true;
  });
  const accountTypes = useMemo(
    () =>
      [
        ...new Set(value.accounts.map((account) => account.account_type)),
      ].sort(),
    [value.accounts],
  );
  const filteredAccounts = useMemo(() => {
    const query = accountSearch.trim().toLocaleLowerCase();
    return value.accounts.filter(
      (account) =>
        (accountType === "all" || account.account_type === accountType) &&
        (!query ||
          [
            account.name,
            account.account_number,
            account.fully_qualified_name,
            account.account_type,
            account.account_subtype,
            account.source_id,
          ].some((item) => item?.toLocaleLowerCase().includes(query))),
    );
  }, [accountSearch, accountType, value.accounts]);
  const netOpenAr = arSummary.data
    ? ({
        amount: arSummary.data.net_open_ar,
        currency: arSummary.data.currency,
        state: "available" as const,
      } satisfies QboAmount)
    : ({
        amount: null,
        currency: null,
        state: "unavailable" as const,
      } satisfies QboAmount);
  const grossAmount = Number(value.ar.total_open.amount);
  const netAmount = Number(arSummary.data?.net_open_ar);
  const creditOffset =
    Number.isFinite(grossAmount) && Number.isFinite(netAmount)
      ? ({
          amount: (grossAmount - netAmount).toFixed(2),
          currency:
            value.ar.total_open.currency ?? arSummary.data?.currency ?? null,
          state: "available" as const,
        } satisfies QboAmount)
      : ({
          amount: null,
          currency: null,
          state: "unavailable" as const,
        } satisfies QboAmount);
  return (
    <div className="space-y-6">
      <FinanceSourceCenter value={value} />
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
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <Input
                  aria-label="Search source accounts"
                  placeholder="Search name, number, type, or source ID"
                  value={accountSearch}
                  onChange={(event) => setAccountSearch(event.target.value)}
                />
                <Select
                  aria-label="Filter source accounts by type"
                  value={accountType}
                  onChange={(event) => setAccountType(event.target.value)}
                >
                  <option value="all">All account types</option>
                  {accountTypes.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </Select>
              </div>
              <p className="text-sm text-content-muted">
                Showing {filteredAccounts.length} of {value.accounts.length}{" "}
                source accounts.
              </p>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[46rem] text-sm">
                  <thead>
                    <tr className="text-left">
                      <th>Account</th>
                      <th>Number</th>
                      <th>Type</th>
                      <th>Source balance</th>
                      <th>Source ID</th>
                      <th>Source/native state</th>
                      <th>Evidence state</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredAccounts.map((row) => (
                      <tr
                        className="border-b border-stroke"
                        key={row.source_id}
                      >
                        <td className="py-2">{row.name}</td>
                        <td>{row.account_number ?? "Not supplied"}</td>
                        <td>
                          {row.account_type}
                          {row.account_subtype
                            ? ` · ${row.account_subtype}`
                            : ""}
                        </td>
                        <td>{money(row.balance)}</td>
                        <td className="font-mono text-xs">{row.source_id}</td>
                        <td>QBO source only · not reconciled to ACP native</td>
                        <td className="capitalize">{row.balance.state}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
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
          <CardHeader>
            <CardTitle>Actually open invoices</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{value.ar.open_invoice_count}</p>
            <p className="text-sm text-content-muted">
              QBO invoices with Balance &gt; $0
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Gross open invoice balances</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{money(value.ar.total_open)}</p>
            <p className="text-sm text-content-muted">
              Sum of positive QBO Invoice Balance fields
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Real total open A/R</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">
              {arSummary.isLoading ? "Loading…" : money(netOpenAr)}
            </p>
            <p className="text-sm text-content-muted">
              QBO A/R Aging Summary · net of customer credits and unapplied
              payments
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Credits/payment offset</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{money(creditOffset)}</p>
            <p className="text-sm text-content-muted">
              Gross invoice balances minus QBO net A/R
            </p>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>QBO source invoice history</CardTitle>
          <CardDescription>
            This is the complete acquired invoice population, not a list of open
            invoices. Default view shows only invoices with a positive QBO
            Balance. Provider workflow reflects print/email delivery state, not
            whether an invoice is paid.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {value.invoices.length ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-end gap-3">
                <label>
                  <span className="mb-1 block text-sm text-content-muted">
                    Invoice view
                  </span>
                  <Select
                    value={invoiceFilter}
                    onChange={(event) =>
                      setInvoiceFilter(
                        event.target.value as "open" | "closed" | "all",
                      )
                    }
                  >
                    <option value="open">
                      Open only ({value.ar.open_invoice_count})
                    </option>
                    <option value="closed">
                      Paid/closed ({value.ar.closed_invoice_count})
                    </option>
                    <option value="all">
                      All source invoices ({value.ar.invoice_evidence_count})
                    </option>
                  </Select>
                </label>
                <p className="text-sm text-content-muted">
                  Showing {filteredInvoices.length} invoices
                </p>
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
                    </tr>
                  </thead>
                  <tbody>
                    {filteredInvoices.map((row) => (
                      <tr
                        className="border-b border-stroke"
                        key={row.source_id}
                      >
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
                  <p className="font-medium">{row.label}</p>
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
  const selectPreset = (preset: PeriodPreset) => {
    const period = periodFor(preset);
    setStartDate(period.start);
    setEndDate(period.end);
  };
  const exportReport = () => {
    if (!sourceReport.data) return;
    const csv = [
      sourceReport.data.columns.map(csvCell).join(","),
      ...sourceReport.data.rows.map((row) =>
        sourceReport
          .data!.columns.map((_, index) => csvCell(row.values[index] ?? ""))
          .join(","),
      ),
    ].join("\n");
    const url = URL.createObjectURL(
      new Blob([csv], { type: "text/csv;charset=utf-8" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `qbo-profit-and-loss-${sourceReport.data.start_date}-${sourceReport.data.end_date}-${sourceReport.data.accounting_basis}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };
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
          <div
            className="flex flex-wrap gap-2"
            aria-label="Report period shortcuts"
          >
            <Button
              type="button"
              variant="secondary"
              onClick={() => selectPreset("this-month")}
            >
              This month
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => selectPreset("last-month")}
            >
              Last month
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => selectPreset("quarter")}
            >
              This quarter
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => selectPreset("ytd")}
            >
              Year to date
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => selectPreset("prior-year")}
            >
              Prior year
            </Button>
          </div>
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
              required
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
            />
            <Input
              aria-label="QBO report end date"
              type="date"
              min={startDate}
              required
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
              ACP requested a {basis} Profit &amp; Loss for{" "}
              {reportRequest.startDate}–{reportRequest.endDate}. The exact
              provider report could not be read from the verified QuickBooks
              Production company. The sealed source center above remains
              available; retry after provider access or acquisition is restored.
              No ACP-native statement or zero value was substituted.
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
                <span className="mt-1 block">
                  QuickBooks supplied these values. ACP has not accepted them as
                  posted ACP Accounting.
                </span>
              </Alert>
              <div className="flex flex-wrap gap-2 print:hidden">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={exportReport}
                >
                  Export CSV
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => window.print()}
                >
                  Print report
                </Button>
              </div>
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
      <GeneralLedgerEvidence enabled={enabled} />
    </section>
  );
}
