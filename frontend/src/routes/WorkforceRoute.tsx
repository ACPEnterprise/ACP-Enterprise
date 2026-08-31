import { useMemo, useState } from "react";
import { Award, Languages, Search, ShieldCheck, UserRoundCheck, UsersRound } from "lucide-react";

import { getOperatorApiError } from "../api/errors";
import { useWorkforceDirectory, useWorkforceEligibility, useWorkforceEmployee } from "../hooks/useWorkforce";
import { Alert, Badge, Card, Input, Spinner } from "../ui";

function Readiness({ state }: { state: "READY" | "BLOCKED" | "INSUFFICIENT_EVIDENCE" }) {
  return <Badge variant={state === "READY" ? "success" : state === "BLOCKED" ? "danger" : "neutral"}>{state.replaceAll("_", " ")}</Badge>;
}

export function WorkforceRoute() {
  const directory = useWorkforceDirectory();
  const [selected, setSelected] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const detail = useWorkforceEmployee(selected);
  const eligibility = useWorkforceEligibility();
  const [branchId, setBranchId] = useState("");
  const [windowStart, setWindowStart] = useState("");
  const [windowEnd, setWindowEnd] = useState("");
  const [capabilities, setCapabilities] = useState("");
  const [languages, setLanguages] = useState("");
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (directory.data ?? []).filter((item) => !query || [item.display_name, item.employee_number, item.job_title ?? "", ...item.capability_codes, ...item.language_codes].some((value) => value.toLowerCase().includes(query)));
  }, [directory.data, search]);

  return <div className="space-y-6">
    <header><p className="text-sm font-medium text-action-primary">Workforce operations</p><h2 className="mt-1 text-2xl font-bold sm:text-3xl">Employee readiness</h2><p className="mt-2 text-content-muted">Operational identity, capability, credential, language, and Branch evidence. Payroll data is excluded.</p></header>
    <Card className="p-4 sm:p-6">
      <h3 className="text-lg font-semibold">Assignment eligibility</h3>
      <p className="mt-1 text-sm text-content-muted">Evaluate explicit Branch, availability, capability, language, restriction, and assignment evidence. This does not assign work.</p>
      <form className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5" onSubmit={(event) => { event.preventDefault(); eligibility.mutate({ branch_id: branchId, window_start_at: new Date(windowStart).toISOString(), window_end_at: new Date(windowEnd).toISOString(), required_capability_codes: capabilities.split(",").map((value) => value.trim()).filter(Boolean), required_language_codes: languages.split(",").map((value) => value.trim()).filter(Boolean) }); }}>
        <label className="text-sm"><span className="mb-1 block font-medium">Branch ID</span><Input required value={branchId} onChange={(event) => setBranchId(event.target.value)} placeholder="Authorized Branch UUID"/></label>
        <label className="text-sm"><span className="mb-1 block font-medium">Window start</span><Input required type="datetime-local" value={windowStart} onChange={(event) => setWindowStart(event.target.value)}/></label>
        <label className="text-sm"><span className="mb-1 block font-medium">Window end</span><Input required type="datetime-local" value={windowEnd} onChange={(event) => setWindowEnd(event.target.value)}/></label>
        <label className="text-sm"><span className="mb-1 block font-medium">Capabilities</span><Input value={capabilities} onChange={(event) => setCapabilities(event.target.value)} placeholder="plumbing, technician"/></label>
        <label className="text-sm"><span className="mb-1 block font-medium">Languages</span><Input value={languages} onChange={(event) => setLanguages(event.target.value)} placeholder="en, es"/></label>
        <button type="submit" disabled={eligibility.isPending} className="min-h-10 rounded-lg bg-action-primary px-4 font-semibold text-white disabled:opacity-50 md:col-span-2 xl:col-span-1">{eligibility.isPending ? "Evaluating…" : "Evaluate"}</button>
      </form>
      {eligibility.isError && <div className="mt-4"><Alert variant="danger" title="Eligibility unavailable">The evidence could not be evaluated. Verify the authorized Branch and time window.</Alert></div>}
      {eligibility.data && <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-3">{eligibility.data.map((item) => <div key={item.employee_id} className="rounded-xl border border-stroke p-3"><div className="flex items-start justify-between gap-2"><div><strong>{item.display_name}</strong><p className="text-xs text-content-muted">{item.employee_number}</p></div><Badge variant={item.eligible ? "success" : "neutral"}>{item.decision}</Badge></div><p className="mt-2 text-xs text-content-muted">{item.reasons.length ? item.reasons.join(" · ") : "No blockers"} · {item.availability_confidence}</p></div>)}</div>}
    </Card>
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
          <section className="rounded-xl border border-stroke p-4 md:col-span-2"><h4 className="font-semibold">Recorded availability</h4><div className="mt-3 grid gap-2 md:grid-cols-2">{detail.data.availability.map((item) => <div key={`${item.branch_id}-${item.start_at}-${item.end_at}`} className="rounded-lg bg-surface-subtle p-3 text-sm"><div className="flex justify-between gap-3"><strong>{item.status}</strong><span className="text-xs text-content-muted">{item.source}</span></div><p className="mt-1 text-xs text-content-muted">{new Date(item.start_at).toLocaleString()} – {new Date(item.end_at).toLocaleString()}</p></div>)}{detail.data.availability.length === 0 && <p className="text-sm text-content-muted">No configured working-availability evidence.</p>}</div></section>
        </div>
      </Card>}
    </div>
  </div>;
}
