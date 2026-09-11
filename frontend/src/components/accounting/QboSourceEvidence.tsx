import { useState } from "react";
import type {
  QboAccountingEvidenceWorkspace,
  QboAmount,
} from "../../api/qboAccountingEvidence";
import { useQboAccountingEvidence } from "../../hooks/useQboAccountingEvidence";
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

function Workspace({ value }: { value: QboAccountingEvidenceWorkspace }) {
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
          QuickBooks Online source-reported evidence · {value.accounting_basis}{" "}
          basis · as of {when(value.as_of)} · acquired {when(value.acquired_at)}
          .
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
            {value.source_company_label} · {value.source_company_id_masked}
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
          <dt className="text-content-muted">Refresh state</dt>
          <dd className="capitalize">{value.refresh_state}</dd>
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
      <div className="grid gap-4 md:grid-cols-3">
        {[
          ["Open AR", value.ar.total_open],
          ["Current", value.ar.current],
          ["Overdue", value.ar.overdue],
        ].map(([label, total]) => (
          <Card key={label as string}>
            <CardHeader>
              <CardTitle>{label as string}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{money(total as QboAmount)}</p>
              <p className="text-sm text-content-muted">
                QBO source-reported balance
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Invoice and AR evidence</CardTitle>
          <CardDescription>
            Provider assertions only. HCP and ACP records are not added to these
            totals.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {value.invoices.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left">
                    <th>Document</th>
                    <th>Customer</th>
                    <th>Date / due</th>
                    <th>Status</th>
                    <th>Total</th>
                    <th>Open</th>
                  </tr>
                </thead>
                <tbody>
                  {value.invoices.map((row) => (
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
                    </tr>
                  ))}
                </tbody>
              </table>
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
        {value.snapshot_digest ?? "unavailable"} · read-only evidence
      </p>
    </div>
  );
}

export function QboSourceEvidence({ enabled }: { enabled: boolean }) {
  const [basis, setBasis] = useState<"cash" | "accrual">("cash");
  const evidence = useQboAccountingEvidence(basis, enabled);
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
    </section>
  );
}
