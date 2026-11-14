import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import {
  approveAccountingJournal,
  evidenceDigest,
  postAccountingJournal,
  prepareAccountingJournal,
  type AccountingJournal,
  type AccountingOperation,
} from "../api/accountingOperations";
import { useHasPermission } from "../auth";
import {
  useAccountingAccounts,
  useAccountingDashboard,
  useAccountingJournals,
  useAccountingMutations,
  useAccountingOperations,
  useAccountingPeriods,
} from "../hooks/useAccountingOperations";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Select,
  Spinner,
} from "../ui";

const kinds = [
  "undeposited_receipt",
  "deposit",
  "card_account",
  "card_charge",
  "card_credit",
  "card_payment",
  "fixed_asset",
  "depreciation",
  "tax_accrual",
  "tax_payment",
  "inventory_valuation",
  "inventory_purchase",
  "inventory_usage",
  "inventory_adjustment",
  "job_cost",
  "cutover_activation",
] as const;
const links = [
  ["Invoices", "/invoices"],
  ["Receive payment", "/payments"],
  ["Vendors, bills & AP", "/accounts-payable"],
  ["Banking & reconciliation", "/accounting/banking"],
  ["Inventory", "/inventory"],
  ["Payroll accounting", "/payroll"],
  ["Financial statements", "/financial-reports"],
  ["Period close", "/accounting/close"],
  ["Beacon provenance", "/audit"],
  ["Luminary findings", "/luminary"],
  ["LIA discrepancy review", "/lia?contextDomain=accounting"],
];
const today = new Date().toISOString().slice(0, 10);

function payload(
  kind: string,
  a: string,
  b: string,
  c: string,
): Record<string, unknown> {
  if (kind === "undeposited_receipt")
    return { payment_reference: a, customer_reference: b };
  if (kind === "deposit")
    return {
      payment_references: a
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean),
      bank_account_reference: b,
    };
  if (kind === "card_account") return { masked_identity: a, account_name: b };
  if (kind === "fixed_asset")
    return {
      placed_in_service_date: a,
      useful_life_months: Number(b),
      depreciation_method: c || "straight_line",
    };
  if (kind === "depreciation") return { depreciation_period: a };
  if (kind === "tax_accrual") return { tax_type: a, liability_period: b };
  if (kind === "tax_payment") return { tax_type: a, payment_reference: b };
  if (kind === "inventory_valuation") return { valuation_method: a };
  if (["inventory_purchase", "inventory_usage"].includes(kind))
    return {
      inventory_item_id: a,
      quantity: b,
      ...(kind === "inventory_usage" ? { job_id: c } : {}),
    };
  if (kind === "inventory_adjustment")
    return { inventory_item_id: a, reason: b };
  if (kind === "job_cost") return { job_id: a, cost_category: b };
  if (kind === "cutover_activation")
    return {
      accepted_capabilities: a
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean),
      acceptance_evidence_reference: b,
    };
  return {};
}
function fieldLabels(kind: string): [string, string, string] {
  const values: Record<string, [string, string, string]> = {
    undeposited_receipt: ["Payment reference", "Customer reference", ""],
    deposit: [
      "UF receipt references (comma separated)",
      "Bank account reference",
      "",
    ],
    card_account: ["Masked identity", "Account name", ""],
    fixed_asset: [
      "Placed-in-service date",
      "Useful life (months)",
      "Depreciation method",
    ],
    depreciation: ["Depreciation period", "", ""],
    tax_accrual: ["Tax type", "Liability period", ""],
    tax_payment: ["Tax type", "Payment reference", ""],
    inventory_valuation: ["Valuation method", "", ""],
    inventory_purchase: ["Inventory item ID", "Quantity", ""],
    inventory_usage: ["Inventory item ID", "Quantity", "Job ID"],
    inventory_adjustment: ["Inventory item ID", "Reason", ""],
    job_cost: ["Job ID", "Cost category", ""],
    cutover_activation: [
      "Accepted capabilities (comma separated)",
      "Acceptance evidence reference",
      "",
    ],
  };
  return values[kind] ?? ["", "", ""];
}

export function AccountingRoute() {
  const canRead = useHasPermission("COMPANY_ACCOUNTING_READ"),
    canPrepare = useHasPermission("COMPANY_ACCOUNTING_JOURNAL_PREPARE"),
    canPost = useHasPermission("COMPANY_ACCOUNTING_JOURNAL_POST"),
    canManage = useHasPermission("COMPANY_ACCOUNTING_PERIOD_MANAGE");
  const dashboard = useAccountingDashboard(),
    accounts = useAccountingAccounts(),
    periods = useAccountingPeriods(),
    journals = useAccountingJournals(),
    operations = useAccountingOperations(),
    mutations = useAccountingMutations();
  const [journal, setJournal] = useState({
    date: today,
    period_id: "",
    description: "",
    debit_account_id: "",
    credit_account_id: "",
    amount: "",
    reference: "",
  });
  const [op, setOp] = useState({
    kind: "deposit",
    date: today,
    period_id: "",
    reference: "",
    amount: "",
    debit_account_id: "",
    credit_account_id: "",
    related_operation_id: "",
    a: "",
    b: "",
    c: "",
  });
  const [actionError, setActionError] = useState("");
  if (!canRead)
    return (
      <Alert variant="danger">You are not authorized to use Accounting.</Alert>
    );
  if (dashboard.isPending || accounts.isPending || periods.isPending)
    return <Spinner label="Loading Accounting" />;
  const activeAccounts =
      accounts.data?.filter((x) => x.status === "active") ?? [],
    openPeriods =
      periods.data?.filter((x) => ["open", "reopened"].includes(x.status)) ??
      [];
  const buildJournal = async (
    kind: string,
    reference: string,
    date: string,
    periodId: string,
    amount: string,
    debit: string,
    credit: string,
  ) => ({
    period_id: periodId,
    journal_type: "manual",
    effective_date: date,
    currency: "USD",
    description: `Controlled ${kind.replaceAll("_", " ")} ${reference}`,
    source_system: "twelvehats_browser",
    source_type: kind,
    source_identity: reference,
    source_digest: await evidenceDigest(
      `${kind}:${reference}:${date}:${amount}:${debit}:${credit}`,
    ),
    posting_rule_version: "browser-accounting-v1",
    client_idempotency_key: crypto.randomUUID(),
    lines: [
      {
        account_id: debit,
        debit: amount,
        credit: "0",
        description: `${kind} debit`,
      },
      {
        account_id: credit,
        debit: "0",
        credit: amount,
        description: `${kind} credit`,
      },
    ],
  });
  const submitJournal = async (e: FormEvent) => {
    e.preventDefault();
    setActionError("");
    try {
      await mutations.createJournal.mutateAsync(
        await buildJournal(
          "manual_journal",
          journal.reference,
          journal.date,
          journal.period_id,
          journal.amount,
          journal.debit_account_id,
          journal.credit_account_id,
        ),
      );
      setJournal({ ...journal, description: "", amount: "", reference: "" });
    } catch {
      setActionError(
        "Journal was not accepted. Verify the period, accounts, balance, and provenance.",
      );
    }
  };
  const submitOperation = async (e: FormEvent) => {
    e.preventDefault();
    setActionError("");
    try {
      const registerOnly = ["card_account", "cutover_activation"].includes(
        op.kind,
      );
      const journalPayload = registerOnly
        ? null
        : await buildJournal(
            op.kind,
            op.reference,
            op.date,
            op.period_id,
            op.amount,
            op.debit_account_id,
            op.credit_account_id,
          );
      await mutations.createOperation.mutateAsync({
        kind: op.kind,
        reference: op.reference,
        effective_date: op.date,
        amount: registerOnly ? "0" : op.amount,
        currency: "USD",
        related_operation_id: op.related_operation_id || null,
        payload: payload(op.kind, op.a, op.b, op.c),
        provenance: {
          source: "operator_recorded",
          evidence_reference: `browser:${op.reference}`,
          classification: "VERIFIED",
        },
        journal: journalPayload,
      });
      setOp({ ...op, reference: "", amount: "", a: "", b: "", c: "" });
    } catch {
      setActionError(
        "Operation failed safely. Verify its required register relationship, fields, accounts, and open period.",
      );
    }
  };
  const transition = async (
    value: AccountingJournal,
    action: "prepare" | "approve" | "post",
  ) => {
    setActionError("");
    try {
      if (action === "prepare") await prepareAccountingJournal(value);
      if (action === "approve")
        await approveAccountingJournal(
          value,
          await evidenceDigest(`approval:${value.id}:${value.version}`),
          "Independent browser approval",
        );
      if (action === "post") await postAccountingJournal(value);
      await journals.refetch();
      await Promise.all([dashboard.refetch(), operations.refetch()]);
    } catch {
      setActionError(
        "Journal transition was rejected. Independent approval, current version, and an open period are required.",
      );
    }
  };
  const labels = fieldLabels(op.kind),
    related = (operations.data ?? []).filter(
      (x) =>
        (op.kind.startsWith("card_") && x.kind === "card_account") ||
        (op.kind === "depreciation" && x.kind === "fixed_asset"),
    );
  return (
    <div className="mx-auto max-w-7xl space-y-8 pb-12">
      <header>
        <p className="text-sm font-semibold text-action-primary">Accounting</p>
        <h1 className="text-3xl font-bold">Accounting command center</h1>
        <p className="text-content-muted">
          Native current accounting, governed journals, discrepancy visibility,
          and close status.
        </p>
      </header>
      {actionError && <Alert variant="danger">{actionError}</Alert>}
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Card>
          <CardContent>
            <strong>{dashboard.data?.active_account_count ?? 0}</strong>
            <p>Active accounts</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <strong>{dashboard.data?.open_period_count ?? 0}</strong>
            <p>Open periods</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <strong>
              {dashboard.data?.balanced ? "Balanced" : "Attention"}
            </strong>
            <p>Trial Balance</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <strong>{dashboard.data?.discrepancy_count ?? 0}</strong>
            <p>Discrepancies</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <strong>{dashboard.data?.close_status}</strong>
            <p>Close status</p>
          </CardContent>
        </Card>
      </section>
      <Card>
        <CardHeader>
          <CardTitle>Accounting workspaces</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {links.map(([label, to]) => (
            <Link
              className="rounded border border-stroke p-3 font-semibold text-action-primary"
              key={to}
              to={to}
            >
              {label}
            </Link>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Chart of Accounts</CardTitle>
          <CardDescription>
            Classification, normal balance, lifecycle, and direct ledger
            drilldown.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Name</th>
                  <th>Classification</th>
                  <th>Normal</th>
                  <th>Status</th>
                  <th>Drilldown</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {accounts.data?.map((row) => (
                  <tr className="border-t border-stroke" key={row.id}>
                    <td>{row.code}</td>
                    <td>{row.name}</td>
                    <td>{row.classification}</td>
                    <td>{row.normal_balance}</td>
                    <td>
                      <Badge>{row.status}</Badge>
                    </td>
                    <td>
                      <Link
                        className="text-action-primary"
                        to={`/financial-reports?report=general-ledger&account=${row.id}`}
                      >
                        General Ledger
                      </Link>
                    </td>
                    <td>
                      {canManage && (
                        <Button
                          variant="secondary"
                          onClick={() =>
                            mutations.status.mutate({
                              id: row.id,
                              status:
                                row.status === "active" ? "archived" : "active",
                            })
                          }
                        >
                          {row.status === "active" ? "Archive" : "Activate"}
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
      {canPrepare && (
        <div className="grid gap-4 xl:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Controlled journal entry</CardTitle>
              <CardDescription>
                Balanced draft with immutable source digest; preparation,
                independent approval, and posting remain separate.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form
                className="grid gap-3 sm:grid-cols-2"
                onSubmit={(e) => void submitJournal(e)}
              >
                <Input
                  aria-label="Journal date"
                  type="date"
                  required
                  value={journal.date}
                  onChange={(e) =>
                    setJournal({ ...journal, date: e.target.value })
                  }
                />
                <Select
                  aria-label="Journal period"
                  required
                  value={journal.period_id}
                  onChange={(e) =>
                    setJournal({ ...journal, period_id: e.target.value })
                  }
                >
                  <option value="">Select period</option>
                  {openPeriods.map((x) => (
                    <option key={x.id} value={x.id}>
                      {x.name}
                    </option>
                  ))}
                </Select>
                <Input
                  aria-label="Journal reference"
                  required
                  value={journal.reference}
                  onChange={(e) =>
                    setJournal({ ...journal, reference: e.target.value })
                  }
                />
                <Input
                  aria-label="Journal amount"
                  min="0.01"
                  step="0.01"
                  type="number"
                  required
                  value={journal.amount}
                  onChange={(e) =>
                    setJournal({ ...journal, amount: e.target.value })
                  }
                />
                <Select
                  aria-label="Debit account"
                  required
                  value={journal.debit_account_id}
                  onChange={(e) =>
                    setJournal({ ...journal, debit_account_id: e.target.value })
                  }
                >
                  <option value="">Debit account</option>
                  {activeAccounts.map((x) => (
                    <option key={x.id} value={x.id}>
                      {x.code} · {x.name}
                    </option>
                  ))}
                </Select>
                <Select
                  aria-label="Credit account"
                  required
                  value={journal.credit_account_id}
                  onChange={(e) =>
                    setJournal({
                      ...journal,
                      credit_account_id: e.target.value,
                    })
                  }
                >
                  <option value="">Credit account</option>
                  {activeAccounts.map((x) => (
                    <option key={x.id} value={x.id}>
                      {x.code} · {x.name}
                    </option>
                  ))}
                </Select>
                <Button
                  type="submit"
                  loading={mutations.createJournal.isPending}
                >
                  Create balanced draft
                </Button>
              </form>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Current accounting operation</CardTitle>
              <CardDescription>
                Deposits, cards, fixed assets, depreciation, tax, inventory
                valuation, COGS, and Job cost use the same governed ledger.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form
                className="grid gap-3 sm:grid-cols-2"
                onSubmit={(e) => void submitOperation(e)}
              >
                <Select
                  aria-label="Operation type"
                  value={op.kind}
                  onChange={(e) =>
                    setOp({
                      ...op,
                      kind: e.target.value,
                      related_operation_id: "",
                      a: "",
                      b: "",
                      c: "",
                    })
                  }
                >
                  {kinds.map((x) => (
                    <option key={x} value={x}>
                      {x.replaceAll("_", " ")}
                    </option>
                  ))}
                </Select>
                <Input
                  aria-label="Operation reference"
                  required
                  value={op.reference}
                  onChange={(e) => setOp({ ...op, reference: e.target.value })}
                />
                <Input
                  aria-label="Operation date"
                  type="date"
                  required
                  value={op.date}
                  onChange={(e) => setOp({ ...op, date: e.target.value })}
                />
                {!["card_account", "cutover_activation"].includes(op.kind) && (
                  <>
                    <Select
                      aria-label="Operation period"
                      required
                      value={op.period_id}
                      onChange={(e) =>
                        setOp({ ...op, period_id: e.target.value })
                      }
                    >
                      <option value="">Select period</option>
                      {openPeriods.map((x) => (
                        <option key={x.id} value={x.id}>
                          {x.name}
                        </option>
                      ))}
                    </Select>
                    <Input
                      aria-label="Operation amount"
                      min="0.01"
                      step="0.01"
                      type="number"
                      required
                      value={op.amount}
                      onChange={(e) => setOp({ ...op, amount: e.target.value })}
                    />
                    <Select
                      aria-label="Operation debit account"
                      required
                      value={op.debit_account_id}
                      onChange={(e) =>
                        setOp({ ...op, debit_account_id: e.target.value })
                      }
                    >
                      <option value="">Debit account</option>
                      {activeAccounts.map((x) => (
                        <option key={x.id} value={x.id}>
                          {x.code} · {x.name}
                        </option>
                      ))}
                    </Select>
                    <Select
                      aria-label="Operation credit account"
                      required
                      value={op.credit_account_id}
                      onChange={(e) =>
                        setOp({ ...op, credit_account_id: e.target.value })
                      }
                    >
                      <option value="">Credit account</option>
                      {activeAccounts.map((x) => (
                        <option key={x.id} value={x.id}>
                          {x.code} · {x.name}
                        </option>
                      ))}
                    </Select>
                  </>
                )}
                {related.length > 0 && (
                  <Select
                    aria-label="Related register item"
                    required
                    value={op.related_operation_id}
                    onChange={(e) =>
                      setOp({ ...op, related_operation_id: e.target.value })
                    }
                  >
                    <option value="">Related item</option>
                    {related.map((x) => (
                      <option key={x.id} value={x.id}>
                        {x.reference}
                      </option>
                    ))}
                  </Select>
                )}
                {labels[0] && (
                  <Input
                    aria-label={labels[0]}
                    required
                    value={op.a}
                    onChange={(e) => setOp({ ...op, a: e.target.value })}
                  />
                )}{" "}
                {labels[1] && (
                  <Input
                    aria-label={labels[1]}
                    required
                    value={op.b}
                    onChange={(e) => setOp({ ...op, b: e.target.value })}
                  />
                )}{" "}
                {labels[2] && (
                  <Input
                    aria-label={labels[2]}
                    required
                    value={op.c}
                    onChange={(e) => setOp({ ...op, c: e.target.value })}
                  />
                )}
                <Button
                  type="submit"
                  loading={mutations.createOperation.isPending}
                >
                  Record controlled operation
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Journal detail and workflow</CardTitle>
          <CardDescription>
            Transaction drilldown with source provenance and explicit lifecycle
            controls.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {journals.data?.map((row) => (
            <div className="rounded border border-stroke p-3" key={row.id}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <strong>
                    {row.effective_date} · {row.description}
                  </strong>
                  <p className="text-sm text-content-muted">
                    {row.source_system}/{row.source_type}/{row.source_identity}{" "}
                    · Debits {row.total_debits} · Credits {row.total_credits}
                  </p>
                </div>
                <Badge>{row.status}</Badge>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {canPrepare && row.status === "draft" && (
                  <Button onClick={() => void transition(row, "prepare")}>
                    Prepare
                  </Button>
                )}
                {canPost && row.status === "prepared" && (
                  <Button onClick={() => void transition(row, "approve")}>
                    Approve
                  </Button>
                )}
                {canPost && row.status === "approved" && (
                  <Button onClick={() => void transition(row, "post")}>
                    Post
                  </Button>
                )}
              </div>
              <details className="mt-2">
                <summary>Journal lines and provenance</summary>
                {row.lines.map((line) => (
                  <p className="text-sm" key={line.id}>
                    {line.description} · {line.account_id} · Dr {line.debit} ·
                    Cr {line.credit}
                  </p>
                ))}
                <p className="break-all text-xs text-content-muted">
                  Digest {row.source_digest}
                </p>
              </details>
            </div>
          ))}
          {!journals.data?.length && <p>No journal activity.</p>}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Operational registers</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {operations.data?.map((row: AccountingOperation) => (
            <div
              className="flex flex-wrap justify-between rounded border border-stroke p-3"
              key={row.id}
            >
              <span>
                <strong>
                  {row.kind.replaceAll("_", " ")} · {row.reference}
                </strong>
                <br />
                <span className="text-sm text-content-muted">
                  {row.effective_date} · {row.amount} {row.currency}
                </span>
              </span>
              <Badge>{row.journal_status ?? row.status}</Badge>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
