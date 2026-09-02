import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, History, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

import { getDataQualitySummary } from "../api/dataQuality";
import { getOperatorApiError } from "../api/errors";
import { Alert, Badge, Card, Spinner } from "../ui";

const label = (value: string) => value.replaceAll("_", " ");

export function DataQualityRoute() {
  const quality = useQuery({ queryKey: ["data-quality", "summary"], queryFn: () => getDataQualitySummary() });
  const error = quality.isError ? getOperatorApiError(quality.error, "operational data quality") : null;
  return <div className="space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div><p className="text-sm font-medium text-action-primary">Read-only operational evidence</p><h2 className="mt-1 text-2xl font-bold sm:text-3xl">Data quality center</h2><p className="mt-2 max-w-3xl text-content-muted">Find records that need attention without merging identities or changing source-domain authority. Historical exceptions do not automatically block clean new work.</p></div>
      <button type="button" className="flex min-h-11 items-center gap-2 rounded-lg border border-stroke px-4 font-semibold hover:bg-surface-subtle" onClick={() => void quality.refetch()}><RefreshCw size={16}/>Refresh evidence</button>
    </header>
    {quality.isPending && <Spinner label="Inspecting authorized operational evidence"/>}
    {error && <Alert variant="danger" title={error.title}>{error.message}</Alert>}
    {quality.data && <>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Quality summary">
        <Metric title="Exceptions" value={quality.data.total_issues} icon={<AlertTriangle size={18}/>}/>
        <Metric title="Blocking this record" value={quality.data.blocks_new_operation} icon={<AlertTriangle size={18}/>}/>
        <Metric title="Owner review" value={quality.data.owner_review} icon={<CheckCircle2 size={18}/>}/>
        <Metric title="Historical only" value={quality.data.historical_only} icon={<History size={18}/>}/>
      </section>
      <Card className="overflow-hidden"><div className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm"><caption className="sr-only">Authorized data-quality exceptions and owning workflows</caption><thead className="bg-surface-subtle text-content-muted"><tr><th className="p-3">Domain</th><th className="p-3">Record</th><th className="p-3">Issue</th><th className="p-3">Operational effect</th><th className="p-3">Correction owner</th></tr></thead><tbody className="divide-y divide-stroke">{quality.data.issues.map((issue) => <tr key={`${issue.rule_id}-${issue.safe_record_identity}`}><td className="p-3"><Badge variant={issue.severity === "CRITICAL" ? "danger" : "neutral"}>{label(issue.domain)}</Badge></td><td className="p-3 font-mono text-xs break-all">{issue.safe_record_identity}</td><td className="p-3"><p className="font-medium">{issue.explanation}</p><p className="mt-1 text-xs text-content-muted">Evidence: {issue.missing_or_conflicting_evidence.join(", ")}</p></td><td className="p-3"><span className="font-medium">{label(issue.launch_impact)}</span><span className="mt-1 block text-xs text-content-muted">{label(issue.state)}</span></td><td className="p-3">{label(issue.repair_owner)}</td></tr>)}{quality.data.issues.length === 0 && <tr><td colSpan={5} className="p-8 text-center"><CheckCircle2 className="mx-auto mb-2 text-status-success"/><p className="font-semibold">No exceptions found by the active bounded probes.</p><p className="mt-1 text-content-muted">This does not infer readiness for source or policy gates outside the catalog.</p></td></tr>}</tbody></table></div></Card>
      <p className="text-xs text-content-muted">Catalog {quality.data.catalog_version} · {quality.data.scanned_rules} active probes · digest {quality.data.catalog_digest.slice(0, 12)}…</p>
    </>}
  </div>;
}

function Metric({ title, value, icon }: { title: string; value: number; icon: ReactNode }) {
  return <Card className="p-4"><div className="flex items-center gap-2 text-content-muted">{icon}<span className="text-sm font-medium">{title}</span></div><p className="mt-2 text-3xl font-bold">{value}</p></Card>;
}
