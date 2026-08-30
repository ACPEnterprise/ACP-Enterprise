import { AlertTriangle, RefreshCw, ShieldAlert, Wrench } from "lucide-react";
import { Card } from "../ui";

const states = [
  ["RETRY_SAFE", "Retry the same operation using the same idempotency identity. Do not change the request."],
  ["RETRY_AFTER_REFRESH", "Refresh authoritative state before trying again; another operation may have advanced it."],
  ["USER_CORRECTION_REQUIRED", "Correct the highlighted input. Retrying unchanged will not succeed."],
  ["OWNER_ADMIN_ACTION_REQUIRED", "An authorized owner or administrator must resolve configuration or access."],
  ["RECONCILIATION_REQUIRED", "The outcome is uncertain or contradictory. Review authoritative evidence before acting."],
  ["TEMPORARILY_UNAVAILABLE", "The dependency is degraded. Preserve the operation identity and retry when service recovers."],
  ["TERMINAL_FAILURE", "The operation cannot continue in its current state. Follow the domain-specific resolution path."],
] as const;

export function OperatorGuideRoute() {
  return <div className="space-y-6"><header><p className="text-sm font-medium text-action-primary">Deterministic help</p><h2 className="mt-1 text-2xl font-bold sm:text-3xl">Operator recovery guide</h2><p className="mt-2 text-content-muted">Understand what ACP needs next without interpreting raw database or provider errors.</p></header><div className="grid gap-4 md:grid-cols-2">{states.map(([state, explanation]) => <Card key={state} className="p-5"><h3 className="flex items-center gap-2 font-semibold">{state === "RETRY_SAFE" || state === "RETRY_AFTER_REFRESH" ? <RefreshCw size={18}/> : state === "RECONCILIATION_REQUIRED" ? <AlertTriangle size={18}/> : state === "OWNER_ADMIN_ACTION_REQUIRED" ? <ShieldAlert size={18}/> : <Wrench size={18}/>} {state.replaceAll("_", " ")}</h3><p className="mt-2 text-sm text-content-muted">{explanation}</p></Card>)}</div></div>;
}
