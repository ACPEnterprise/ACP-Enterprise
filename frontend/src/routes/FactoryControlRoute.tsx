import { Activity, Clock3, Factory, Gauge, ShieldAlert } from "lucide-react";
import { Link, useSearchParams } from "react-router";

import type { FactoryLane } from "../api/factoryControl";
import { useAuth } from "../auth";
import { useFactoryControlOverview } from "../hooks/useFactoryControl";
import { Alert, Badge, Card, CardContent, CardHeader, CardTitle, Spinner } from "../ui";

const percent = (value: number) => `${Math.max(0, Math.min(100, value)).toFixed(1)}%`;
const timestamp = (value?: string | null) => value ? new Date(value).toLocaleString() : "Not reported";
const duration = (seconds?: number | null) => seconds == null ? "Not reported" : `${Math.round(seconds / 60)} min`;

function Metric({ label, value }: { label: string; value: string }) {
  return <Card><CardContent className="pt-5"><p className="text-sm text-content-muted">{label}</p><p className="mt-1 text-2xl font-bold">{value}</p></CardContent></Card>;
}

function LaneRow({ lane }: { lane: FactoryLane }) {
  return <tr className="border-t border-border-subtle">
    <td className="px-3 py-3 font-medium"><Link className="text-action-primary hover:underline" to={`/admin/factory-control?lane=${encodeURIComponent(lane.lane_code)}`}>{lane.lane_code}</Link></td>
    <td className="px-3 py-3">{lane.milestone_code ?? "Unassigned"}</td>
    <td className="px-3 py-3"><Badge>{lane.lifecycle_state.replaceAll("_", " ")}</Badge></td>
    <td className="px-3 py-3">{lane.queue_depth}</td>
    <td className="px-3 py-3 text-content-muted">{timestamp(lane.last_event_at)}</td>
  </tr>;
}

export function FactoryControlRoute() {
  const { permissionCodes = [] } = useAuth();
  const authorized = permissionCodes.includes("PLATFORM_FACTORY_CONTROL_READ");
  const [search] = useSearchParams();
  const selectedLane = search.get("lane") ?? undefined;
  const overview = useFactoryControlOverview({ lane: selectedLane }, authorized);
  if (!authorized) return <Alert variant="danger" title="Factory Control is private">Platform owner or administrator authority is required.</Alert>;
  if (overview.isPending) return <Spinner label="Loading Factory Control" />;
  if (overview.isError || !overview.data) return <Alert variant="danger" title="Factory telemetry unavailable">The authoritative overview could not be loaded. No progress or health values were inferred.</Alert>;
  const data = overview.data;
  const lanes = selectedLane ? data.lanes.filter((lane) => lane.lane_code === selectedLane) : data.lanes;
  return <div className="space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm font-semibold text-action-primary">Private platform administration</p><h1 className="mt-1 text-heading-l">Factory Control</h1><p className="mt-2 max-w-3xl text-content-muted">Authoritative engineering throughput, gates, quality, and handoff health. Read-only; no dispatch or release action is available here.</p></div><div className="text-right text-xs text-content-muted"><p>As of {timestamp(data.generated_at)}</p><p>{data.roadmap_milestones} roadmap milestones</p><p className="font-mono">{data.roadmap_digest}</p></div></header>
    {selectedLane && <Alert variant="information" title="Drilldown active">Showing lane {selectedLane}. <Link className="underline" to="/admin/factory-control">Clear filter</Link></Alert>}
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5"><Metric label="Closed" value={percent(data.metrics.closed_percent)} /><Metric label="Engineering" value={percent(data.metrics.engineering_percent)} /><Metric label="Beta" value={percent(data.metrics.beta_percent)} /><Metric label="Owner" value={percent(data.metrics.owner_percent)} /><Metric label="Weighted delivery" value={percent(data.metrics.weighted_delivery_percent)} /></section>
    <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Metric label="Open defects" value={String(data.metrics.open_defects)} /><Metric label="Open gates" value={String(data.metrics.open_gates)} /><Metric label="Queue depth" value={String(data.metrics.queue_depth)} /><Metric label="Utilization" value={percent(data.metrics.utilization_percent)} /></section>
    <Card><CardHeader><CardTitle className="flex items-center gap-2"><Factory size={18}/>Worker lanes</CardTitle></CardHeader><CardContent className="overflow-x-auto"><table className="min-w-full text-left text-sm"><thead><tr><th className="px-3 py-2">Lane</th><th className="px-3 py-2">Milestone</th><th className="px-3 py-2">State</th><th className="px-3 py-2">Queue</th><th className="px-3 py-2">Last event</th></tr></thead><tbody>{lanes.map((lane) => <LaneRow key={lane.lane_code} lane={lane} />)}</tbody></table></CardContent></Card>
    <section className="grid gap-4 lg:grid-cols-3"><Card><CardHeader><CardTitle className="flex items-center gap-2"><Clock3 size={18}/>Flow</CardTitle></CardHeader><CardContent><p>Pickup latency: {duration(data.metrics.pickup_latency_seconds)}</p><p>Oldest handoff: {duration(data.metrics.oldest_handoff_seconds)}</p></CardContent></Card><Card><CardHeader><CardTitle className="flex items-center gap-2"><ShieldAlert size={18}/>Quality</CardTitle></CardHeader><CardContent><p>First-pass yield: {percent(data.metrics.first_pass_yield_percent)}</p><p>Rework: {percent(data.metrics.rework_rate_percent)}</p></CardContent></Card><Card><CardHeader><CardTitle className="flex items-center gap-2"><Gauge size={18}/>Delivery windows</CardTitle></CardHeader><CardContent><p>1d {percent(data.metrics.delivery_1d_percent)} · 3d {percent(data.metrics.delivery_3d_percent)} · 7d {percent(data.metrics.delivery_7d_percent)}</p><p className="mt-2 flex items-center gap-2 text-content-muted"><Activity size={16}/>Controller evidence only</p></CardContent></Card></section>
  </div>;
}
