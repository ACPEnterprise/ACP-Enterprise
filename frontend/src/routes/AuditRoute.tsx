import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Clock3, Filter, ShieldCheck } from "lucide-react";

import { listAuditRecords, type AuditFilters } from "../api/audit";
import { getOperatorApiError } from "../api/errors";
import { Alert, Badge, Card, Input, Spinner } from "../ui";

export function AuditRoute() {
  const [filters, setFilters] = useState<AuditFilters>({ limit: 50 });
  const [draft, setDraft] = useState({ resource_type: "", action: "", outcome: "", correlation_id: "", branch_id: "" });
  const records = useQuery({ queryKey: ["audit-history", filters], queryFn: () => listAuditRecords(filters) });
  const error = records.isError ? getOperatorApiError(records.error, "audit history") : null;
  return <div className="space-y-6">
    <header><p className="text-sm font-medium text-action-primary">Enterprise evidence</p><h2 className="mt-1 text-2xl font-bold sm:text-3xl">Audit history</h2><p className="mt-2 text-content-muted">Immutable, permission-scoped administrative and consequential activity. Protected payloads and security metadata are excluded.</p></header>
    <Card className="p-4 sm:p-6"><form className="grid gap-3 md:grid-cols-2 xl:grid-cols-5" onSubmit={(event) => { event.preventDefault(); setFilters({ limit: 50, ...Object.fromEntries(Object.entries(draft).filter(([, value]) => value.trim())) }); }}>
      <label className="text-sm"><span className="mb-1 block font-medium">Domain/resource</span><Input value={draft.resource_type} onChange={(event) => setDraft({ ...draft, resource_type: event.target.value })}/></label>
      <label className="text-sm"><span className="mb-1 block font-medium">Action</span><Input value={draft.action} onChange={(event) => setDraft({ ...draft, action: event.target.value })}/></label>
      <label className="text-sm"><span className="mb-1 block font-medium">Outcome</span><Input value={draft.outcome} onChange={(event) => setDraft({ ...draft, outcome: event.target.value })}/></label>
      <label className="text-sm"><span className="mb-1 block font-medium">Correlation ID</span><Input value={draft.correlation_id} onChange={(event) => setDraft({ ...draft, correlation_id: event.target.value })}/></label>
      <label className="text-sm"><span className="mb-1 block font-medium">Branch ID</span><Input value={draft.branch_id} onChange={(event) => setDraft({ ...draft, branch_id: event.target.value })}/></label>
      <button className="flex min-h-10 items-center justify-center gap-2 rounded-lg bg-action-primary px-4 font-semibold text-white" type="submit"><Filter size={16}/>Apply filters</button>
    </form></Card>
    {records.isLoading && <Spinner label="Loading audit history"/>}
    {error && <Alert variant="danger" title={error.title}>{error.message}</Alert>}
    {records.data && <><Card className="overflow-hidden"><div className="divide-y divide-stroke">{records.data.map((record) => <article key={record.id} className="p-4 sm:p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="font-semibold">{record.action}</h3><p className="mt-1 text-sm text-content-muted">{record.resource_type}{record.resource_id ? ` · ${record.resource_id}` : ""}</p></div><Badge variant={record.outcome === "success" ? "success" : "neutral"}>{record.outcome}</Badge></div><div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-content-muted"><span className="flex items-center gap-1"><Clock3 size={14}/>{new Date(record.occurred_at).toLocaleString()}</span><span className="flex items-center gap-1"><ShieldCheck size={14}/>{record.actor_user_id ?? "system"}</span><span>Correlation {record.correlation_id}</span>{record.reason_code && <span>Reason {record.reason_code}</span>}</div></article>)}{records.data.length === 0 && <p className="p-6 text-sm text-content-muted">No authorized audit evidence matches these filters.</p>}</div></Card>{records.data.length === 50 && <button type="button" className="min-h-10 rounded-lg border border-stroke px-4 text-sm font-semibold hover:bg-surface-subtle" onClick={() => { const cursor = records.data.at(-1); setFilters({ ...filters, occurred_before: cursor?.occurred_at, before_id: cursor?.id }); }}>Load older evidence</button>}</>}
  </div>;
}
