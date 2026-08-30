import { useMemo, useState } from "react";
import { Award, Languages, Search, ShieldCheck, UserRoundCheck, UsersRound } from "lucide-react";

import { getOperatorApiError } from "../api/errors";
import { useWorkforceDirectory, useWorkforceEmployee } from "../hooks/useWorkforce";
import { Alert, Badge, Card, Input, Spinner } from "../ui";

function Readiness({ state }: { state: "READY" | "BLOCKED" | "INSUFFICIENT_EVIDENCE" }) {
  return <Badge variant={state === "READY" ? "success" : state === "BLOCKED" ? "danger" : "neutral"}>{state.replaceAll("_", " ")}</Badge>;
}

export function WorkforceRoute() {
  const directory = useWorkforceDirectory();
  const [selected, setSelected] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const detail = useWorkforceEmployee(selected);
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (directory.data ?? []).filter((item) => !query || [item.display_name, item.employee_number, item.job_title ?? "", ...item.capability_codes, ...item.language_codes].some((value) => value.toLowerCase().includes(query)));
  }, [directory.data, search]);

  return <div className="space-y-6">
    <header><p className="text-sm font-medium text-action-primary">Workforce operations</p><h2 className="mt-1 text-2xl font-bold sm:text-3xl">Employee readiness</h2><p className="mt-2 text-content-muted">Operational identity, capability, credential, language, and Branch evidence. Payroll data is excluded.</p></header>
    <div className="grid gap-6 xl:grid-cols-[minmax(20rem,0.85fr)_minmax(0,1.4fr)]">
      <Card className="min-w-0 overflow-hidden">
        <div className="border-b border-stroke p-4"><label className="relative block"><span className="sr-only">Search workforce</span><Search size={17} className="absolute left-3 top-3 text-content-muted"/><Input className="pl-10" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name, number, role, capability, language"/></label></div>
        {directory.isLoading && <div className="p-8"><Spinner label="Loading workforce"/></div>}
        {directory.isError && (() => { const error = getOperatorApiError(directory.error, "workforce directory"); return <div className="p-4"><Alert variant="danger" title={error.title}>{error.message}</Alert></div>; })()}
        <div className="divide-y divide-stroke">
          {filtered.map((employee) => <button key={employee.employee_id} type="button" onClick={() => setSelected(employee.employee_id)} className="flex min-h-16 w-full items-center justify-between gap-3 p-4 text-left hover:bg-surface-subtle focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus"><span className="min-w-0"><span className="block truncate font-semibold">{employee.display_name}</span><span className="block truncate text-xs text-content-muted">{employee.employee_number} · {employee.job_title ?? employee.employee_type}</span></span><Readiness state={employee.readiness_state}/></button>)}
        </div>
        {directory.isSuccess && filtered.length === 0 && <p className="p-5 text-sm text-content-muted">No authorized Employee profile matches this search.</p>}
      </Card>
      {!selected ? <Card className="flex min-h-72 items-center justify-center p-8 text-center"><div><UsersRound className="mx-auto text-action-primary"/><h3 className="mt-3 text-xl font-semibold">Select an Employee</h3><p className="mt-2 text-sm text-content-muted">Inspect explicit readiness evidence without exposing Payroll or compensation data.</p></div></Card> : detail.isLoading ? <Card className="p-8"><Spinner label="Loading Employee profile"/></Card> : detail.isError || !detail.data ? <Alert variant="danger" title="Employee profile unavailable">The profile could not be loaded within the current Company and Branch authority.</Alert> : <Card className="min-w-0 p-4 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm text-action-primary">{detail.data.employee_number}</p><h3 className="mt-1 text-2xl font-bold">{detail.data.display_name}</h3><p className="mt-1 text-content-muted">{detail.data.job_title ?? detail.data.employee_type}</p></div><Readiness state={detail.data.readiness_state}/></div>
        {detail.data.readiness_blockers.length > 0 && <section className="mt-5 rounded-xl border border-status-warning/40 bg-status-warning/5 p-4"><h4 className="font-semibold">Assignment readiness blockers</h4><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-content-muted">{detail.data.readiness_blockers.map((item) => <li key={item}>{item.replaceAll("_", " ")}</li>)}</ul></section>}
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <section className="rounded-xl border border-stroke p-4"><h4 className="flex items-center gap-2 font-semibold"><UserRoundCheck size={17}/>Capabilities</h4><div className="mt-3 space-y-2">{detail.data.capabilities.map((item) => <p key={item.code} className="text-sm"><strong>{item.display_name}</strong> · {item.proficiency}</p>)}{detail.data.capabilities.length === 0 && <p className="text-sm text-content-muted">No explicit capability evidence.</p>}</div></section>
          <section className="rounded-xl border border-stroke p-4"><h4 className="flex items-center gap-2 font-semibold"><Languages size={17}/>Languages</h4><div className="mt-3 space-y-2">{detail.data.languages.map((item) => <p key={item.code} className="text-sm"><strong>{item.english_name}</strong> · {item.spoken_proficiency}{item.customer_facing_eligible ? " · customer-facing" : ""}</p>)}{detail.data.languages.length === 0 && <p className="text-sm text-content-muted">No explicit language evidence.</p>}</div></section>
          <section className="rounded-xl border border-stroke p-4 md:col-span-2"><h4 className="flex items-center gap-2 font-semibold"><Award size={17}/>Certifications</h4><div className="mt-3 grid gap-2 md:grid-cols-2">{detail.data.certifications.map((item) => <div key={`${item.code}-${item.credential_reference}`} className="rounded-lg bg-surface-subtle p-3 text-sm"><div className="flex justify-between gap-3"><strong>{item.display_name}</strong><Badge variant="neutral">{item.status}</Badge></div><p className="mt-1 text-xs text-content-muted">Evidence {item.credential_reference}{item.expires_on ? ` · expires ${item.expires_on}` : " · no expiration recorded"}</p></div>)}{detail.data.certifications.length === 0 && <p className="text-sm text-content-muted">No certification evidence.</p>}</div></section>
          <section className="rounded-xl border border-stroke p-4"><h4 className="flex items-center gap-2 font-semibold"><ShieldCheck size={17}/>Branch authority</h4><div className="mt-3 space-y-2">{detail.data.branches.map((item) => <p key={item.branch_id} className="break-all text-sm">{item.branch_id} · {item.status}</p>)}{detail.data.branches.length === 0 && <p className="text-sm text-content-muted">Home Branch only or no explicit eligibility evidence.</p>}</div></section>
          <section className="rounded-xl border border-stroke p-4"><h4 className="font-semibold">Restrictions and equipment</h4><p className="mt-3 text-sm text-content-muted">{detail.data.work_restrictions.length ? detail.data.work_restrictions.join(", ") : "No active work restriction evidence."}</p><p className="mt-2 text-sm text-content-muted">{detail.data.equipment_capabilities.length ? detail.data.equipment_capabilities.map((item) => item.display_name).join(", ") : "No equipment capability evidence."}</p></section>
        </div>
      </Card>}
    </div>
  </div>;
}
