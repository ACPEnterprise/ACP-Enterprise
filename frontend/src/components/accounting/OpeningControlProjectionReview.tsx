import { useState } from "react";
import { useOpeningSubledger } from "../../hooks/useAccountingClose";
import type { OpeningControlDetail } from "../../api/accountingClose";
import { Alert, Badge, Button, Card, CardContent, CardHeader, CardTitle } from "../../ui";

function amount(value: string | null | undefined) {
  return value === null || value === undefined ? "Unavailable" : value;
}
function status(value: string) {
  return <Badge variant={value === "APPROVED" || value === "APPLIED" ? "success" : value === "REVIEW_REQUIRED" ? "warning" : "neutral"}>{value.replaceAll("_", " ")}</Badge>;
}
export function OpeningControlProjectionReview({ value }: { value: OpeningControlDetail }) {
  const [family, setFamily] = useState<"ar" | "ap" | null>(null);
  const subledger = useOpeningSubledger(value.package.id, family ?? "ar", Boolean(family));
  const unresolved = value.package.status === "REVIEW_REQUIRED" || value.difference !== "0" || value.ar_difference !== "0" || value.ap_difference !== "0";
  return <div className="space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p className="text-sm text-content-muted">Package {value.package.package_identity} · cutoff {value.cutoff_at} · source as of {value.source_as_of}</p>
      {status(value.package.status)}
    </div>
    {unresolved && <Alert variant="warning" title="Accountant review required">Server-owned opening controls contain an unresolved balance, exception, or difference.</Alert>}
    <Card><CardHeader><CardTitle>Opening Trial Balance</CardTitle></CardHeader><CardContent className="space-y-3">
      <div className="overflow-x-auto"><table className="min-w-[760px] w-full text-sm"><thead><tr className="text-left"><th>Source identity</th><th>Type</th><th>Debit</th><th>Credit</th><th>Equity category</th></tr></thead><tbody>{value.trial_balance.map((line) => <tr className="border-b border-stroke" key={line.source_identity}><td className="py-2">{line.source_identity}</td><td>{line.account_type}</td><td>{amount(line.debit)}</td><td>{amount(line.credit)}</td><td>{line.equity_category ?? "—"}</td></tr>)}</tbody></table></div>
      <dl className="grid gap-2 text-sm sm:grid-cols-3"><div><dt>Total debits</dt><dd>{amount(value.total_debits)}</dd></div><div><dt>Total credits</dt><dd>{amount(value.total_credits)}</dd></div><div><dt>Difference</dt><dd>{amount(value.difference)}</dd></div></dl>
    </CardContent></Card>
    <Card><CardHeader><CardTitle>Equity and control distinctions</CardTitle></CardHeader><CardContent className="grid gap-3 text-sm sm:grid-cols-2"><p>Equity categories: {value.equity_categories.length ? value.equity_categories.join(", ") : "Unavailable"}</p><p>Unexplained difference: {amount(value.difference)}</p><p>AR control difference: {amount(value.ar_difference)}</p><p>AP control difference: {amount(value.ap_difference)}</p></CardContent></Card>
    <Card><CardHeader><CardTitle>AR/AP drill-down</CardTitle></CardHeader><CardContent className="space-y-3"><div className="flex flex-wrap gap-2"><Button variant={family === "ar" ? "primary" : "secondary"} onClick={() => setFamily("ar")}>Load AR</Button><Button variant={family === "ap" ? "primary" : "secondary"} onClick={() => setFamily("ap")}>Load AP</Button></div>{family && (subledger.isLoading ? <p>Loading {family.toUpperCase()} evidence…</p> : subledger.isError ? <Alert variant="warning">{family.toUpperCase()} evidence is unavailable.</Alert> : <><p className="text-sm text-content-muted">{subledger.data?.total ?? 0} server-owned records · offset {subledger.data?.offset ?? 0} · limit {subledger.data?.limit ?? 0}</p><div className="overflow-x-auto"><table className="min-w-[680px] w-full text-sm"><thead><tr className="text-left"><th>Source identity</th><th>Party</th><th>Document</th><th>Open amount</th><th>As of</th></tr></thead><tbody>{(subledger.data?.items ?? []).map((item) => <tr className="border-b border-stroke" key={String(item.source_identity)}><td className="py-2">{String(item.source_identity ?? "Unavailable")}</td><td>{String(item.party_identity ?? "Unavailable")}</td><td>{String(item.document_identity ?? "Unavailable")}</td><td>{String(item.open_amount ?? "Unavailable")}</td><td>{String(item.as_of ?? "Unavailable")}</td></tr>)}</tbody></table></div></>)}</CardContent></Card>
    <Card><CardHeader><CardTitle>Lifecycle</CardTitle></CardHeader><CardContent className="space-y-2 text-sm">{value.lifecycle.map((item) => <p key={item.state + item.at}>{item.state} · {item.actor_role} · {item.actor_display_name} · {item.at}</p>)}</CardContent></Card>
  </div>;
}
