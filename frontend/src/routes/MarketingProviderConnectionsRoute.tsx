import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, CircleDashed, ExternalLink, RefreshCw, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { getOperatorApiError } from "../api/errors";
import { beginGoogleAdsAuthorization, getGoogleAdsOwnerWorkspace } from "../api/marketing";
import { useAuth } from "../auth";
import { Alert, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Select, Spinner } from "../ui";

const label = (value: string) => value.replaceAll("_", " ");
const readinessRows = (data: Awaited<ReturnType<typeof getGoogleAdsOwnerWorkspace>>["readiness"]) => [
  ["OAuth client configured", data.oauth_client_configured],
  ["Callback configured", data.callback_configured],
  ["Developer token configured", data.developer_token_configured],
  ["Environment-safe secret custody", data.environment_safe_secret_custody],
  ["Live ingestion enabled", data.live_ingestion_enabled],
] as const;

export function MarketingProviderConnectionsRoute() {
  const { activeCompany } = useAuth();
  const [historyDays, setHistoryDays] = useState("30");
  const workspace = useQuery({ queryKey: ["marketing", "google-ads", "owner-workspace", activeCompany?.id], queryFn: getGoogleAdsOwnerWorkspace, enabled: Boolean(activeCompany) });
  const error = workspace.isError ? getOperatorApiError(workspace.error, "Google Ads provider connection") : null;
  const data = workspace.data;
  const connect = useMutation({
    mutationFn: beginGoogleAdsAuthorization,
    onSuccess: (authorizationUrl) => window.location.assign(authorizationUrl),
  });
  return <div className="space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div><p className="text-sm font-medium text-action-primary">Marketing · Provider Connections</p><h2 className="mt-1 text-2xl font-bold sm:text-3xl">Google Ads</h2><p className="mt-2 max-w-3xl text-content-muted">Connect one owner-selected account for read-only evidence ingestion. TwelveHats cannot change campaigns, budgets, bids, targeting, keywords, ads, or websites.</p></div>
      <Button variant="secondary" onClick={() => void workspace.refetch()}><RefreshCw size={16}/>Refresh status</Button>
    </header>
    {workspace.isPending && <Spinner label="Checking Google Ads connection readiness"/>}
    {error && <Alert variant="danger" title={error.title}>{error.message}</Alert>}
    {data && <>
      <section className="grid gap-4 lg:grid-cols-2">
        <Card><CardHeader><CardTitle>Connection status</CardTitle><CardDescription>Beta environment: {data.readiness.environment}</CardDescription></CardHeader><CardContent className="space-y-4"><div className="flex items-center gap-2"><Badge variant={data.readiness.connection_status === "connected" ? "success" : "warning"}>{label(data.readiness.connection_status)}</Badge><span className="text-sm text-content-muted">{data.readiness.bound_account_count} bound account(s)</span></div>{data.readiness.connected_at && <p className="text-sm">Authorized {new Date(data.readiness.connected_at).toLocaleString()}</p>}<Button disabled={!data.readiness.authorization_available || connect.isPending} onClick={() => connect.mutate()}><ExternalLink size={16}/>{connect.isPending ? "Preparing secure connection…" : "Connect Google Ads"}</Button>{!data.readiness.authorization_available && <Alert variant="warning">Connection remains locked until every Beta runtime readiness check passes. No authorization request has been started.</Alert>}{connect.isError && <Alert variant="danger">The authorization request could not be prepared. No Google connection was created.</Alert>}</CardContent></Card>
        <Card><CardHeader><CardTitle>Configuration readiness</CardTitle><CardDescription>Only readiness booleans are exposed; secret names and values never reach this page.</CardDescription></CardHeader><CardContent><ul className="space-y-3">{readinessRows(data.readiness).map(([name, ready]) => <li className="flex items-center justify-between gap-3" key={name}><span>{name}</span>{ready ? <Badge variant="success"><CheckCircle2 size={14}/>Ready</Badge> : <Badge variant="warning"><CircleDashed size={14}/>Required</Badge>}</li>)}</ul></CardContent></Card>
      </section>
      <Card><CardHeader><CardTitle>Owner connection workflow</CardTitle><CardDescription>Authorization and discovery are separate from account binding. Accessible accounts are never selected automatically.</CardDescription></CardHeader><CardContent><ol className="grid gap-3 md:grid-cols-5">{["Authorize with Google", "Review exact accessible accounts", "Select All County and map its Branch", "Confirm read-only ingestion and history", "Sync, reconcile, and review coverage"].map((step, index) => <li className="rounded-lg border border-stroke p-3" key={step}><span className="text-xs font-semibold text-content-muted">STEP {index + 1}</span><p className="mt-1 font-medium">{step}</p></li>)}</ol></CardContent></Card>
      <Card><CardHeader><CardTitle>Selected account bindings</CardTitle><CardDescription>Only accounts explicitly confirmed by an owner appear here.</CardDescription></CardHeader><CardContent>{data.bindings.length ? <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th className="p-2">Account</th><th className="p-2">Branch</th><th className="p-2">Currency / time zone</th><th className="p-2">Ingestion</th></tr></thead><tbody>{data.bindings.map(binding => <tr className="border-t border-stroke" key={binding.id}><td className="p-2"><strong>{binding.descriptive_name}</strong><span className="block font-mono text-xs">{binding.external_customer_id}</span></td><td className="p-2">{activeCompany?.branches?.find(branch => branch.id === binding.branch_id)?.name ?? binding.branch_id}</td><td className="p-2">{binding.currency_code ?? "Unknown"} · {binding.time_zone ?? "Unknown"}</td><td className="p-2"><Badge variant={binding.ingestion_enabled ? "success" : "neutral"}>{binding.ingestion_enabled ? "Enabled" : "Disabled"}</Badge></td></tr>)}</tbody></table></div> : <Alert>No Google Ads account has been selected or bound.</Alert>}</CardContent></Card>
      <Card><CardHeader><CardTitle>Initial bounded sync</CardTitle><CardDescription>The cursor advances only after a complete committed partition. Provider revisions append evidence.</CardDescription></CardHeader><CardContent className="space-y-4"><label className="block max-w-sm text-sm font-medium">Initial history period<Select className="mt-1" value={historyDays} onChange={event => setHistoryDays(event.target.value)}><option value="30">Last 30 days</option><option value="90">Last 90 days</option><option value="180">Last 180 days</option></Select></label><Button disabled={!data.bindings.some(binding => binding.ingestion_enabled)}><ShieldCheck size={16}/>Confirm and start read-only sync</Button><p className="text-xs text-content-muted">This screen does not expose a sync mutation until owner authorization, binding, and Beta runtime admission are complete.</p></CardContent></Card>
      <section className="grid gap-4 lg:grid-cols-2"><Card><CardHeader><CardTitle>Evidence coverage</CardTitle><CardDescription>Unknown and missing downstream attribution remain explicit.</CardDescription></CardHeader><CardContent>{data.coverage.length ? <ul className="space-y-3">{data.coverage.map((row, index) => <li className="rounded-lg border border-stroke p-3" key={`${row.provider_account_id}-${index}`}><div className="flex justify-between"><Badge>{label(row.availability)}</Badge><strong>{row.coverage_percent}%</strong></div><p className="mt-2 text-sm">{row.evidence_count} evidence records · policy {row.attribution_policy_version}</p><p className="text-xs text-content-muted">Missing: {row.missing_components.join(", ") || "none"}</p></li>)}</ul> : <p className="text-content-muted">No coverage manifest exists until a bounded sync completes.</p>}</CardContent></Card><Card><CardHeader><CardTitle>Reconciliation</CardTitle><CardDescription>Provider totals are evidence, not TwelveHats Jobs, revenue, or economic contribution.</CardDescription></CardHeader><CardContent>{data.reconciliation.length ? <ul className="space-y-3">{data.reconciliation.map(item => <li className="rounded-lg border border-stroke p-3" key={item.id}><div className="flex justify-between"><strong>{label(item.kind)}</strong><Badge variant="warning">{label(item.state)}</Badge></div><p className="mt-1 text-xs text-content-muted">Missing: {item.missing_components.join(", ") || "none"}</p></li>)}</ul> : <p className="text-content-muted">No open reconciliation findings.</p>}</CardContent></Card></section>
    </>}
  </div>;
}
