import { Activity, AlertTriangle, Clock3, Factory, Gauge, ShieldAlert } from "lucide-react";
import { Link, useSearchParams } from "react-router";

import { useAuth } from "../auth";
import type { FactoryLane } from "../api/factoryControl";
import { useFactoryControlOverview } from "../hooks/useFactoryControl";
import { Alert, Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, Spinner } from "../ui";

const percent = (value: number) => `${Math.max(0, Math.min(100, value)).toFixed(1)}%`;
const timestamp = (value?: string | null) => value ? new Date(value).toLocaleString() : "Not reported";

function Metric({ label, value }: { label: string; value: string }) {
  return <Card><CardContent className="pt-5"><p className="text-sm text-content-muted">{label}</p><p className="mt-1 text-2xl font-bold">{value}</p></CardContent></Card>;
}

function LaneRow({ lane }: { lane: FactoryLane }) {
  return <tr className="border-t border-border-subtle">
    <td className="px-3 py-3 font-medium"><Link className="text-action-primary hover:underline" to={`/admin/factory-control?lane=${encodeURIComponent(lane.lane_id)}`}>{lane.lane_id}</Link></td>
    <td className="px-3 py-3">{lane.worker}</td><td className="px-3 py-3"><Link className="hover:underline" to={`/admin/factory-control?domain=${encodeURIComponent(lane.domain)}`}>{lane.domain}</Link></td>
    <td className="px-3 py-3"><Badge>{lane.state.replaceAll("_", " ")}</Badge></td>
    <td className="px-3 py-3">{lane.priority ?? "—"}</td><td className="px-3 py-3 text-content-muted">{lane.assignment ?? lane.blocker ?? "No assignment reported"}</td>
  </tr>;
}

export function FactoryControlRoute() {
  const { permissionCodes = [] } = useAuth();
  const authorized = permissionCodes.includes("COMPANY_ADMINISTER");
  const [search] = useSearchParams();
  const filters = { lane: search.get("lane") ?? undefined, domain: search.get("domain") ?? undefined };
  const overview = useFactoryControlOverview(filters, authorized);
  if (!authorized) return <Alert variant="danger" title="Factory Control is private">Owner or Company administrator authority is required.</Alert>;
  if (overview.isPending) return <Spinner label="Loading Factory Control" />;
  if (overview.isError || !overview.data) return <Alert variant="danger" title="Factory telemetry unavailable">The authoritative overview could not be loaded. No progress or health values were inferred.</Alert>;
  const data = overview.data;
  const active = data.lanes.filter((lane) => lane.state === "active").length;
  const idle = data.lanes.filter((lane) => lane.state === "eligible_idle").length;
  return <div className="space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm font-semibold text-action-primary">Private administration</p><h1 className="mt-1 text-heading-l">Factory Control</h1><p className="mt-2 max-w-3xl text-content-muted">Authoritative engineering throughput, gates, and handoff health. Read-only; no dispatch or release action is available here.</p></div><div className="text-right text-xs text-content-muted"><p>As of {timestamp(data.as_of)}</p><p className="font-mono">{data.authority_sha}</p></div></header>
    {(filters.lane || filters.domain) && <Alert variant="information" title="Drilldown active">Showing {filters.lane ? `lane ${filters.lane}` : `domain ${filters.domain}`}. <Link className="underline" to="/admin/factory-control">Clear filter</Link></Alert>}
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5"><Metric label="Closed" value={percent(data.completion.closed_percent)} /><Metric label="Engineering" value={percent(data.completion.engineering_percent)} /><Metric label="Beta" value={percent(data.completion.beta_percent)} /><Metric label="Owner" value={percent(data.completion.owner_percent)} /><Metric label="Today weighted" value={percent(data.completion.today_weighted_progress)} /></section>
    <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Metric label="P0 backlog" value={String(data.backlog.p0)} /><Metric label="P1 backlog" value={String(data.backlog.p1)} /><Metric label="Active lanes" value={String(active)} /><Metric label="Eligible idle" value={String(idle)} /></section>
    <section className="grid gap-4 xl:grid-cols-3">{data.queues.map((queue) => <Card key={queue.queue_id}><CardHeader><CardTitle>{queue.queue_id}</CardTitle><CardDescription>Execution queue</CardDescription></CardHeader><CardContent className="grid grid-cols-3 gap-2 text-sm"><div><b>{queue.active}</b><br/>active</div><div><b>{queue.eligible_idle}</b><br/>eligible idle</div><div><b>{queue.blocked}</b><br/>blocked</div><p className="col-span-3 text-content-muted">Oldest handoff: {timestamp(queue.oldest_handoff_at)}</p></CardContent></Card>)}</section>
    <section className="grid gap-4 lg:grid-cols-2"><Card><CardHeader><CardTitle className="flex items-center gap-2"><Clock3 size={18}/>Oldest handoff</CardTitle></CardHeader><CardContent>{data.oldest_handoff ? <><p className="font-semibold">{data.oldest_handoff.lane_id}: {data.oldest_handoff.assignment ?? "Unnamed handoff"}</p><p className="text-sm text-content-muted">{timestamp(data.oldest_handoff.handoff_at)}</p></> : <p className="text-content-muted">No handoff reported.</p>}</CardContent></Card><Card><CardHeader><CardTitle className="flex items-center gap-2"><AlertTriangle size={18}/>Current bottleneck</CardTitle></CardHeader><CardContent><p className="font-semibold">{data.bottleneck?.label ?? "No bottleneck reported"}</p>{data.bottleneck?.detail && <p className="text-sm text-content-muted">{data.bottleneck.detail}</p>}</CardContent></Card></section>
    <Card><CardHeader><CardTitle className="flex items-center gap-2"><Factory size={18}/>Worker lanes and domains</CardTitle></CardHeader><CardContent className="overflow-x-auto"><table className="min-w-full text-left text-sm"><thead><tr><th className="px-3 py-2">Lane</th><th className="px-3 py-2">Worker</th><th className="px-3 py-2">Domain</th><th className="px-3 py-2">State</th><th className="px-3 py-2">Priority</th><th className="px-3 py-2">Truth</th></tr></thead><tbody>{data.lanes.map((lane) => <LaneRow key={lane.lane_id} lane={lane} />)}</tbody></table></CardContent></Card>
    <section className="grid gap-4 lg:grid-cols-2"><Card><CardHeader><CardTitle className="flex items-center gap-2"><ShieldAlert size={18}/>Human and provider gates</CardTitle></CardHeader><CardContent className="space-y-3">{data.gates.length ? data.gates.map((gate) => <div key={gate.code}><div className="flex items-center justify-between"><p className="font-medium">{gate.label}</p><Badge>{gate.kind}</Badge></div><p className="text-sm text-content-muted">{gate.detail ?? "No additional detail."} · {gate.blocked_lanes} lane(s)</p></div>) : <p className="text-content-muted">No gates reported.</p>}</CardContent></Card><Card><CardHeader><CardTitle className="flex items-center gap-2"><Gauge size={18}/>Migration completeness</CardTitle></CardHeader><CardContent><p className="text-3xl font-bold">{percent(data.migration.completeness_percent)}</p><p className="text-sm text-content-muted">{data.migration.complete} of {data.migration.total} classified complete</p>{data.migration.limitations?.map((item) => <p className="mt-2 text-sm" key={item}>• {item}</p>)}</CardContent></Card></section>
    <Card><CardHeader><CardTitle className="flex items-center gap-2"><Activity size={18}/>Velocity</CardTitle><CardDescription>Completed work and weighted progress by reported window</CardDescription></CardHeader><CardContent className="grid gap-3 sm:grid-cols-3">{(["1d", "3d", "7d"] as const).map((window) => { const value = data.velocity.find((item) => item.window === window); return <div className="rounded border border-border-subtle p-3" key={window}><p className="font-semibold">{window}</p><p>{value ? `${value.completed} completed · ${percent(value.weighted_progress)}` : "Not reported"}</p></div>; })}</CardContent></Card>
  </div>;
}
