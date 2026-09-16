import type { QboAccountingEvidenceWorkspace } from "../../api/qboAccountingEvidence";
import {
  Alert,
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../../ui";

const friendly = (value: string) => value.replaceAll("_", " ").toLowerCase();
const timestamp = (value: string | null) =>
  value ? new Date(value).toLocaleString() : "Not supplied by source";

const reportCatalog = [
  [
    "Profit & Loss",
    "SOURCE_BACKED",
    "Run cash or accrual reports for a selected period.",
  ],
  [
    "A/R Aging",
    "SOURCE_BACKED",
    "Provider net open receivables, including credits and unapplied payments.",
  ],
  [
    "Balance Sheet",
    "PARTIAL",
    "Sealed historical controls may be inspected; arbitrary-period live projection is not yet available.",
  ],
  [
    "Trial Balance",
    "PARTIAL",
    "Sealed historical controls may be inspected; arbitrary-period live projection is not yet available.",
  ],
  [
    "General Ledger",
    "SOURCE_BACKED",
    "Digest-verified sealed controls support period filtering and bounded 50-row pages.",
  ],
  [
    "A/P / unpaid bills",
    "PARTIAL",
    "Acquired bill evidence is available; a provider-authored A/P report is not projected.",
  ],
  [
    "Customer balances",
    "PARTIAL",
    "Invoice and payment evidence is available without cross-source aggregation.",
  ],
  [
    "Vendor balances",
    "PARTIAL",
    "Bill and vendor evidence is available without an authoritative balance report.",
  ],
] as const;

const badgeVariant = (state: string) =>
  state === "SOURCE_BACKED" || state === "AVAILABLE"
    ? "success"
    : state === "UNAVAILABLE"
      ? "danger"
      : "warning";

export function FinanceSourceCenter({
  value,
}: {
  value: QboAccountingEvidenceWorkspace;
}) {
  const unavailableFamilies = value.catalog_dispositions.filter(
    (item) => item.disposition !== "ACQUIRED",
  );
  const reconciliationItems = [
    {
      state: value.refresh_state === "available" ? "READY" : "PARTIAL",
      title: "QuickBooks source acquisition",
      detail:
        value.refresh_state === "available"
          ? "A complete sealed source snapshot is available."
          : "The latest snapshot is incomplete, stale, or unavailable.",
    },
    {
      state: "ACCOUNTANT ACTION",
      title: "ACP-native Accounting admission",
      detail:
        "Source reports are not posted ACP General Ledger truth. Opening controls and accounting classifications remain governed separately.",
    },
    ...(value.conflicts.length
      ? [
          {
            state: "SOURCE CONFLICT",
            title: "Cross-source reconciliation",
            detail: `${value.conflicts.length} unresolved source conflict(s) require disposition.`,
          },
        ]
      : [
          {
            state: "OWNER ACTION",
            title: "Cross-source reconciliation",
            detail:
              "No conflict packet is attached to this snapshot; absence is not proof of reconciliation.",
          },
        ]),
  ];

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>QuickBooks Source Center</CardTitle>
          <CardDescription>
            What ACP currently has from QuickBooks, without promoting it to
            ACP-native Accounting.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <dl className="grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <dt className="text-content-muted">Company</dt>
              <dd className="font-semibold">{value.source_company_label}</dd>
              <dd className="text-content-muted">
                Provider ID {value.source_company_id_masked}
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Provider environment</dt>
              <dd className="capitalize">
                QuickBooks {value.provider_environment}
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Connection</dt>
              <dd>
                {value.provider_authorization === "verified_current"
                  ? "Connected and company verified"
                  : "Current authorization not verified"}
              </dd>
              <dd className="text-content-muted">
                Verified {timestamp(value.company_info_verified_at)}
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Acquisition</dt>
              <dd className="capitalize">
                {value.completeness} · {value.refresh_state}
              </dd>
              <dd className="text-content-muted">
                Acquired {timestamp(value.acquired_at)}
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Source as of</dt>
              <dd>{timestamp(value.as_of)}</dd>
            </div>
            <div>
              <dt className="text-content-muted">Evidence mode</dt>
              <dd>{friendly(value.evidence_mode)}</dd>
            </div>
            <div>
              <dt className="text-content-muted">Source families</dt>
              <dd>
                {
                  Object.values(value.entity_counts).filter(
                    (count) => count > 0,
                  ).length
                }{" "}
                acquired · {unavailableFamilies.length} limited
              </dd>
            </div>
            <div>
              <dt className="text-content-muted">Accounting authority</dt>
              <dd className="font-semibold">QBO SOURCE EVIDENCE</dd>
              <dd className="text-content-muted">Not ACP-native</dd>
            </div>
          </dl>
          <details>
            <summary className="cursor-pointer font-medium">
              Source-family inventory
            </summary>
            <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {Object.entries(value.entity_counts).map(([family, count]) => (
                <p
                  className="rounded-md border border-stroke p-2 text-sm"
                  key={family}
                >
                  <span className="capitalize">{friendly(family)}</span> ·{" "}
                  {count.toLocaleString()} records
                </p>
              ))}
              {unavailableFamilies.map((item) => (
                <p
                  className="rounded-md border border-stroke p-2 text-sm"
                  key={`${item.entity_kind}-${item.disposition}`}
                >
                  <span className="capitalize">
                    {friendly(item.entity_kind)}
                  </span>{" "}
                  · {friendly(item.disposition ?? "provider limitation")}
                </p>
              ))}
            </div>
          </details>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Financial report catalog</CardTitle>
          <CardDescription>
            Availability and authority are evaluated independently for each
            report.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="grid gap-3 md:grid-cols-2">
            {reportCatalog.map(([name, state, detail]) => (
              <li className="rounded-lg border border-stroke p-3" key={name}>
                <div className="flex items-center justify-between gap-3">
                  <strong>{name}</strong>
                  <Badge variant={badgeVariant(state)}>{state}</Badge>
                </div>
                <p className="mt-2 text-sm text-content-muted">{detail}</p>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Previously acquired source reports</CardTitle>
          <CardDescription>
            Sealed evidence can be inspected without calling QuickBooks again.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {value.reports.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[42rem] text-sm">
                <thead>
                  <tr className="text-left">
                    <th>Report</th>
                    <th>Period</th>
                    <th>Basis</th>
                    <th>Source as of</th>
                    <th>Authority</th>
                    <th>Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {value.reports.map((report) => (
                    <tr
                      className="border-b border-stroke"
                      key={report.report_key}
                    >
                      <td className="py-2">{report.label}</td>
                      <td>
                        {report.start_date ?? "Through"} –{" "}
                        {report.as_of ?? "Unavailable"}
                      </td>
                      <td className="capitalize">
                        {report.basis ?? "Unavailable"}
                      </td>
                      <td>{timestamp(report.acquired_at)}</td>
                      <td>QBO SOURCE EVIDENCE</td>
                      <td>
                        {report.source_digest
                          ? `${report.source_digest.slice(0, 12)}…`
                          : "Registered"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Alert variant="warning" title="No sealed report history">
              ACP has no registered report controls for this basis. Run a live
              source-backed report or acquire the required control; no empty
              report was inferred.
            </Alert>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Reconciliation and accounting readiness</CardTitle>
          <CardDescription>
            Connection, acquisition, reconciliation, and ACP-native posting are
            separate milestones.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="space-y-3">
            {reconciliationItems.map((item) => (
              <li
                className="rounded-lg border border-stroke p-3"
                key={item.title}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={badgeVariant(item.state)}>{item.state}</Badge>
                  <strong>{item.title}</strong>
                </div>
                <p className="mt-2 text-sm text-content-muted">{item.detail}</p>
              </li>
            ))}
          </ul>
          {value.limitations.length ? (
            <details className="mt-4">
              <summary className="cursor-pointer font-medium">
                Provider and evidence limitations
              </summary>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-content-muted">
                {value.limitations.map((item) => (
                  <li key={item}>{friendly(item)}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
