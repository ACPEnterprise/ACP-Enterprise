import { useState } from "react";

import { useHasPermission } from "../auth";
import {
  useApplyQboSafeMajority,
  useQboApplicationLedger,
  useQboReviewQueue,
} from "../hooks/useQboNativeApplication";
import { Alert, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Spinner } from "../ui";

const label = (value: string) => value.replaceAll("_", " ").toLowerCase();

export function QboMigrationRoute() {
  const canReconcile = useHasPermission("COMPANY_ACCOUNTING_RECONCILE");
  const ledger = useQboApplicationLedger(canReconcile);
  const review = useQboReviewQueue(canReconcile);
  const apply = useApplyQboSafeMajority();
  const [confirmed, setConfirmed] = useState(false);

  if (!canReconcile) return <Alert variant="danger">Accounting reconciliation permission is required.</Alert>;
  if (ledger.isPending) return <Spinner label="Loading QuickBooks migration evidence" />;
  if (ledger.isError || !ledger.data) return <Alert variant="danger">QuickBooks migration status could not be loaded. No source data was applied.</Alert>;

  const source = ledger.data.source_evidence;
  const dispositionTotal = ledger.data.families.reduce((total, item) => total + item.total_source, 0);
  const appliedTotal = ledger.data.families.reduce((total, item) => total + item.applied + item.bound, 0);
  const safePercentage = dispositionTotal ? ((appliedTotal / dispositionTotal) * 100).toFixed(2) : "0.00";

  return <div className="mx-auto max-w-7xl space-y-6 pb-12">
    <header><p className="text-sm font-semibold text-action-primary">Accounting</p><h1 className="text-2xl font-bold sm:text-3xl">QuickBooks migration and reconciliation</h1><p className="mt-2 text-content-muted">Apply exact source matches, quarantine records that need a decision, and continue the safe majority. This never changes QuickBooks or posts Accounting entries.</p></header>

    <Card><CardHeader><CardTitle>Sealed QuickBooks source</CardTitle><CardDescription>Digest-verified evidence already acquired into protected Twelve Hats custody.</CardDescription></CardHeader><CardContent className="space-y-3">
      <div className="flex flex-wrap items-center gap-2"><Badge variant={source.available ? "success" : "warning"}>{source.available ? "Available" : "Unavailable"}</Badge>{source.acquired_at && <span className="text-sm">Acquired {new Date(source.acquired_at).toLocaleString()}</span>}</div>
      {source.available ? <><p className="text-sm"><strong>{source.total_source_records ?? 0}</strong> source records across <strong>{source.source_families?.length ?? 0}</strong> families.</p><div className="flex flex-wrap gap-2">{source.source_families?.map((item) => <Badge key={item.source_family}>{label(item.source_family)}: {item.total_source}</Badge>)}</div></> : <Alert variant="warning">{source.reason ?? "Sealed source evidence is unavailable."} Release must restore the protected evidence volume; do not reacquire or fabricate counts.</Alert>}
    </CardContent></Card>

    <Card><CardHeader><CardTitle>Application status</CardTitle><CardDescription>Every processed source record has an explicit disposition. Unexplained must remain zero.</CardDescription></CardHeader><CardContent className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3"><p><strong>{dispositionTotal}</strong><br/><span className="text-sm text-content-muted">records dispositioned</span></p><p><strong>{appliedTotal}</strong><br/><span className="text-sm text-content-muted">applied or bound</span></p><p><strong>{safePercentage}%</strong><br/><span className="text-sm text-content-muted">safe majority</span></p></div>
      {ledger.data.families.length ? <div className="overflow-x-auto"><table className="min-w-[900px] w-full text-sm"><thead><tr className="text-left"><th>Source family</th><th>Total</th><th>Applied</th><th>Bound</th><th>Quarantined</th><th>Unavailable</th><th>Unsupported</th><th>Rejected</th><th>Unexplained</th><th>Safe %</th></tr></thead><tbody>{ledger.data.families.map((item) => <tr className="border-t border-stroke" key={item.source_family}><td className="py-2 font-medium">{label(item.source_family)}</td><td>{item.total_source}</td><td>{item.applied}</td><td>{item.bound}</td><td>{item.quarantined}</td><td>{item.provider_unavailable}</td><td>{item.unsupported}</td><td>{item.rejected}</td><td>{item.unexplained}</td><td>{item.safe_majority_applied_percentage}%</td></tr>)}</tbody></table></div> : <p className="text-sm text-content-muted">No application receipt exists yet. Source availability above is a preflight, not an application result.</p>}
      {ledger.data.last_execution.last_applied_at && <Alert variant="success">Durable receipt: {ledger.data.last_execution.total_dispositions} current dispositions, last recorded {new Date(ledger.data.last_execution.last_applied_at).toLocaleString()}.</Alert>}
      <label className="flex items-start gap-2 text-sm"><input className="mt-1" type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)}/><span>I understand this binds exact matches and quarantines conflicts. It does not write to QuickBooks, post Accounting, or move money.</span></label>
      <Button disabled={!source.available || !confirmed} loading={apply.isPending} onClick={() => void apply.mutateAsync()}>Apply safe majority</Button>
      {apply.isSuccess && <Alert variant="success">Execution receipt: {apply.data.processed} processed, {apply.data.created} new dispositions, {apply.data.replayed} exact replays. No QuickBooks write or Accounting posting occurred.</Alert>}
      {apply.isError && <Alert variant="danger">The safe-majority run failed closed. No QuickBooks write or Accounting posting occurred. Verify evidence custody and current authorization.</Alert>}
    </CardContent></Card>

    <Card><CardHeader><CardTitle>Needs review</CardTitle><CardDescription>Only records with a specific conflict or missing authority appear here. Unrelated records continue.</CardDescription></CardHeader><CardContent>
      {review.isPending ? <Spinner label="Loading reconciliation review queue"/> : review.isError ? <Alert variant="warning">The review queue could not be loaded.</Alert> : review.data?.length ? <div className="space-y-3">{review.data.map((item) => <article className="rounded-lg border border-stroke p-4" key={item.id}><div className="flex flex-wrap justify-between gap-2"><h2 className="font-semibold">{label(item.source_family)} · {item.reference_number ?? item.provider_record_id}</h2><Badge variant="warning">Needs review</Badge></div><p className="mt-2 text-sm">{item.exact_conflict}</p><dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4"><div><dt className="text-content-muted">Date</dt><dd>{item.source_date ?? "Not supplied"}</dd></div><div><dt className="text-content-muted">Amount</dt><dd>{item.source_amount ?? "Not supplied"}</dd></div><div><dt className="text-content-muted">Entity</dt><dd>{item.source_entity_names.join(", ") || "Not supplied"}</dd></div><div><dt className="text-content-muted">Candidate native identity</dt><dd>{item.candidate_native_ids.join(", ") || "No exact candidate"}</dd></div></dl>{item.affected_dependents.length > 0 && <p className="mt-2 text-sm"><strong>Dependent records:</strong> {item.affected_dependents.join(", ")}</p>}<p className="mt-2 text-sm text-content-muted">Allowed next actions: {item.allowed_actions.map(label).join(" · ")}</p></article>)}</div> : <p className="text-sm text-content-muted">No open reconciliation conflicts.</p>}
    </CardContent></Card>
  </div>;
}
