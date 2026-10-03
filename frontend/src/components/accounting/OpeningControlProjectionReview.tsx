import {
  Alert,
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "../../ui";

export type OpeningControlStatus =
  | "NOT_STARTED"
  | "INCOMPLETE"
  | "READY_FOR_REVIEW"
  | "RECONCILED"
  | "APPROVED";

export interface OpeningTrialBalanceLine {
  identity: string;
  account: string;
  account_type: string;
  debit: string;
  credit: string;
  source_label: string;
  status: OpeningControlStatus;
}

export interface OpeningEquityClassification {
  retained_earnings: string | null;
  owner_equity: string | null;
  opening_balance_equity: string | null;
  unexplained_difference: string | null;
  status: OpeningControlStatus;
}

export interface OpeningControlException {
  id: string;
  family: "OPENING" | "EQUITY" | "AR" | "AP";
  disposition:
    | "SOURCE_ONLY"
    | "ACP_ONLY"
    | "AMOUNT_DIFFERENCE"
    | "MISSING_LINK"
    | "DUPLICATE"
    | "REVIEW_REQUIRED";
  subject: string;
  explanation: string;
  status: "OPEN" | "READY_FOR_REVIEW" | "RESOLVED" | "APPROVED";
}

export interface OpeningControlProjection {
  package_id: string;
  cutoff: string;
  source_as_of: string;
  currency: string;
  status: OpeningControlStatus;
  trial_balance: {
    lines: OpeningTrialBalanceLine[];
    total_debits: string;
    total_credits: string;
    difference: string;
    balanced: boolean;
  };
  equity: OpeningEquityClassification;
  ar: {
    control_balance: string | null;
    subledger_total: string | null;
    difference: string | null;
    status: OpeningControlStatus;
  };
  ap: {
    control_balance: string | null;
    subledger_total: string | null;
    difference: string | null;
    status: OpeningControlStatus;
  };
  exceptions: OpeningControlException[];
}

const money = (value: string | null, currency: string) => {
  if (value === null) return "Unavailable";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "Unavailable";
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
  }).format(parsed);
};

function Status({ value }: { value: OpeningControlStatus }) {
  return (
    <Badge
      variant={
        value === "APPROVED" || value === "RECONCILED"
          ? "success"
          : value === "INCOMPLETE"
            ? "warning"
            : "neutral"
      }
    >
      {value.replaceAll("_", " ")}
    </Badge>
  );
}

export function OpeningControlProjectionReview({
  value,
}: {
  value: OpeningControlProjection;
}) {
  const unresolved = value.exceptions.filter(
    (item) => item.status !== "RESOLVED" && item.status !== "APPROVED",
  );
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-content-muted">
          Cutoff {value.cutoff} · source as of {value.source_as_of}
        </p>
        <Status value={value.status} />
      </div>
      {!value.trial_balance.balanced || unresolved.length ? (
        <Alert variant="warning" title="Accountant review required">
          {!value.trial_balance.balanced
            ? "The opening Trial Balance is not balanced. "
            : ""}
          {unresolved.length
            ? `${unresolved.length} unresolved exception(s) remain.`
            : ""}
        </Alert>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle>Opening Trial Balance</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="overflow-x-auto">
            <table className="min-w-[720px] w-full text-sm">
              <thead>
                <tr className="text-left">
                  <th>Account</th>
                  <th>Type</th>
                  <th>Debit</th>
                  <th>Credit</th>
                  <th>Source</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {value.trial_balance.lines.map((line) => (
                  <tr className="border-b border-stroke" key={line.identity}>
                    <td className="py-2">{line.account}</td>
                    <td>{line.account_type}</td>
                    <td>{money(line.debit, value.currency)}</td>
                    <td>{money(line.credit, value.currency)}</td>
                    <td>{line.source_label}</td>
                    <td>
                      <Status value={line.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <dl className="grid gap-2 text-sm sm:grid-cols-3">
            <div>
              <dt>Total debits</dt>
              <dd>{money(value.trial_balance.total_debits, value.currency)}</dd>
            </div>
            <div>
              <dt>Total credits</dt>
              <dd>
                {money(value.trial_balance.total_credits, value.currency)}
              </dd>
            </div>
            <div>
              <dt>Difference</dt>
              <dd>{money(value.trial_balance.difference, value.currency)}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Opening equity</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="space-y-2 text-sm">
              <div>
                <dt>Retained earnings</dt>
                <dd>{money(value.equity.retained_earnings, value.currency)}</dd>
              </div>
              <div>
                <dt>Owner equity</dt>
                <dd>{money(value.equity.owner_equity, value.currency)}</dd>
              </div>
              <div>
                <dt>Opening-balance equity</dt>
                <dd>
                  {money(value.equity.opening_balance_equity, value.currency)}
                </dd>
              </div>
              <div>
                <dt>Unexplained difference</dt>
                <dd>
                  {money(value.equity.unexplained_difference, value.currency)}
                </dd>
              </div>
            </dl>
          </CardContent>
        </Card>
        {(["ar", "ap"] as const).map((family) => (
          <Card key={family}>
            <CardHeader>
              <CardTitle>
                {family.toUpperCase()} control reconciliation
              </CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="space-y-2 text-sm">
                <div>
                  <dt>Control account</dt>
                  <dd>
                    {money(value[family].control_balance, value.currency)}
                  </dd>
                </div>
                <div>
                  <dt>{family === "ar" ? "Customer" : "Vendor"} subledger</dt>
                  <dd>
                    {money(value[family].subledger_total, value.currency)}
                  </dd>
                </div>
                <div>
                  <dt>Difference</dt>
                  <dd>{money(value[family].difference, value.currency)}</dd>
                </div>
              </dl>
              <div className="mt-3">
                <Status value={value[family].status} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Accountant exceptions</CardTitle>
        </CardHeader>
        <CardContent>
          {value.exceptions.length ? (
            <div className="overflow-x-auto">
              <table className="min-w-[680px] w-full text-sm">
                <thead>
                  <tr className="text-left">
                    <th>Area</th>
                    <th>Issue</th>
                    <th>Record</th>
                    <th>Explanation</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {value.exceptions.map((item) => (
                    <tr className="border-b border-stroke" key={item.id}>
                      <td className="py-2">{item.family}</td>
                      <td>{item.disposition.replaceAll("_", " ")}</td>
                      <td>{item.subject}</td>
                      <td>{item.explanation}</td>
                      <td>{item.status.replaceAll("_", " ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p>
              No opening-control exceptions were reported by the server
              projection.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
