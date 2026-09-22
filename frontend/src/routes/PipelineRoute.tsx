import { type FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { useAuth, useHasPermission } from "../auth";
import { useCreateLead, useLeads } from "../hooks/usePipeline";
import { Alert } from "../ui";
import type { Lead } from "../types/pipeline";

const views = [
  ["all", "All"],
  ["new", "New"],
  ["needs_attention", "Needs Attention"],
  ["scheduled", "Scheduled"],
  ["estimate_follow_up", "Estimate Follow-Up"],
  ["won", "Won"],
  ["lost", "Lost"],
  ["nurture", "Nurture"],
] as const;

const labels: Record<string, string> = {
  new_uncontacted: "New — contact needed",
  due_now: "Due now",
  overdue: "Overdue",
  qualified_not_scheduled: "Qualified — not scheduled",
  estimate_follow_up: "Estimate follow-up",
  missing_next_action: "Next action missing",
  stale: "Stale opportunity",
};

function LeadCard({ lead }: { readonly lead: Lead }) {
  const subject = lead.prospect_name ?? "Existing customer";
  return (
    <article className="rounded-lg border border-stroke bg-surface p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold text-content">{subject}</h3>
          <p className="text-sm text-content-muted">{lead.service_need}</p>
        </div>
        <span className="rounded-full border border-stroke px-2 py-1 text-xs font-medium">
          {lead.stage.replaceAll("_", " ")}
        </span>
      </div>
      <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div><dt className="text-content-muted">Source</dt><dd>{lead.lead_source}</dd></div>
        <div><dt className="text-content-muted">Next action</dt><dd>{lead.next_action_type ?? "Not set"}</dd></div>
        <div><dt className="text-content-muted">Due</dt><dd>{lead.next_action_due_at ? new Date(lead.next_action_due_at).toLocaleString() : "Not set"}</dd></div>
        <div><dt className="text-content-muted">Attempts</dt><dd>{lead.contact_attempt_count}</dd></div>
      </dl>
      {lead.attention_state && (
        <p className="mt-3 font-medium text-warning">{labels[lead.attention_state] ?? lead.attention_state}</p>
      )}
      <div className="mt-3 flex flex-wrap gap-3 text-sm">
        {lead.customer_id && <Link className="text-link" to={`/customers/${lead.customer_id}`}>Open Customer</Link>}
        {lead.job_id && <Link className="text-link" to={`/jobs/${lead.job_id}`}>Open Job</Link>}
        {lead.appointment_id && <Link className="text-link" to={`/appointments/${lead.appointment_id}`}>Open Appointment</Link>}
      </div>
    </article>
  );
}

export function PipelineRoute() {
  const canRead = useHasPermission("COMPANY_CUSTOMER_READ");
  const canManage = useHasPermission("COMPANY_CUSTOMER_MANAGE");
  const { activeCompany } = useAuth();
  const [params, setParams] = useSearchParams();
  const view = params.get("view") ?? "needs_attention";
  const leads = useLeads(view, canRead);
  const create = useCreateLead();
  const [showCreate, setShowCreate] = useState(false);

  if (!canRead) return <Alert variant="danger">You are not authorized to view Pipeline.</Alert>;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const branchId = String(form.get("branch_id") ?? "");
    await create.mutateAsync({
      branch_id: branchId,
      prospect_name: String(form.get("prospect_name") ?? ""),
      contact_phone: String(form.get("contact_phone") ?? "") || undefined,
      lead_source: String(form.get("lead_source") ?? "manual_csr"),
      service_need: String(form.get("service_need") ?? ""),
      next_action_type: "contact",
      next_action_due_at: new Date().toISOString(),
    });
    event.currentTarget.reset();
    setShowCreate(false);
    setParams({ view: "needs_attention" });
  }

  return (
    <section className="space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div><h1 className="text-2xl font-semibold">Pipeline</h1><p className="text-content-muted">Every legitimate service opportunity, with its next action.</p></div>
        {canManage && <button className="rounded-md bg-action px-4 py-2 text-on-action" onClick={() => setShowCreate((value) => !value)}>New Lead</button>}
      </header>
      <nav aria-label="Pipeline views" className="flex gap-2 overflow-x-auto pb-1">
        {views.map(([key, label]) => <button key={key} className={`whitespace-nowrap rounded-md border px-3 py-2 ${view === key ? "border-action bg-action-subtle" : "border-stroke"}`} aria-current={view === key ? "page" : undefined} onClick={() => setParams({ view: key })}>{label}</button>)}
      </nav>
      {showCreate && (
        <form className="grid gap-3 rounded-lg border border-stroke bg-surface p-4 sm:grid-cols-2" onSubmit={(event) => void submit(event)}>
          <h2 className="sm:col-span-2 text-lg font-semibold">Capture service opportunity</h2>
          <label>Prospect or contact name<input required name="prospect_name" className="mt-1 w-full rounded border border-stroke p-2" /></label>
          <label>Phone<input name="contact_phone" type="tel" className="mt-1 w-full rounded border border-stroke p-2" /></label>
          <label>Lead source<select name="lead_source" className="mt-1 w-full rounded border border-stroke p-2"><option value="incoming_phone">Incoming phone call</option><option value="sms">SMS / text</option><option value="web_form">Web form</option><option value="referral">Referral</option><option value="existing_customer">Existing customer</option><option value="manual_csr">Manual CSR entry</option><option value="other">Other</option></select></label>
          <label>Branch<select required name="branch_id" className="mt-1 w-full rounded border border-stroke p-2">{activeCompany?.branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}</select></label>
          <label className="sm:col-span-2">What service do they need?<textarea required name="service_need" className="mt-1 w-full rounded border border-stroke p-2" /></label>
          {create.isError && <Alert variant="danger">The Lead could not be saved. Review the information and try again.</Alert>}
          <button disabled={create.isPending} className="rounded-md bg-action px-4 py-2 text-on-action sm:col-span-2">{create.isPending ? "Saving…" : "Create Lead"}</button>
        </form>
      )}
      {leads.isPending && <p role="status">Loading Pipeline…</p>}
      {leads.isError && <Alert variant="danger">Pipeline is unavailable. Try again.</Alert>}
      {leads.data?.items.length === 0 && <div className="rounded-lg border border-dashed border-stroke p-8 text-center"><h2 className="font-semibold">No Leads in this view</h2><p className="text-content-muted">Choose another view or capture a new service opportunity.</p></div>}
      <div className="grid gap-3">{leads.data?.items.map((lead) => <LeadCard key={lead.id} lead={lead} />)}</div>
    </section>
  );
}
