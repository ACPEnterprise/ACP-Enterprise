import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";
import { ArrowLeft, ArrowRight, Check, CircleHelp, LifeBuoy, RefreshCw, Sparkles } from "lucide-react";

import { useAuth, type AuthenticatedUser } from "../auth";
import type { AccessibleCompany } from "../auth/companyTypes";
import { createMigrationSupportCase, getCommercialOnboardingEvidence, type CommercialException, type CommercialProgressItem } from "../api/commercialOnboarding";
import { getOperatorApiError } from "../api/errors";
import { useLiaReadiness } from "../hooks/useLia";
import { loadCommercialOnboardingDraft, saveCommercialOnboardingDraft, type CommercialOnboardingDraft, type CommercialOnboardingStep } from "../onboarding/commercialOnboardingState";
import { Alert, Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Select, Spinner, Textarea } from "../ui";

const steps: Array<{ id: CommercialOnboardingStep; label: string }> = [
  { id: "company", label: "Company" },
  { id: "systems", label: "Systems" },
  { id: "import", label: "Import" },
  { id: "review", label: "Review" },
  { id: "ready", label: "Ready" },
];

const stateVariant = (state: string) => state === "COMPLETE" || state === "CONNECTED" ? "success" as const : state === "NEEDS_REVIEW" || state === "NEEDS ATTENTION" ? "warning" as const : state === "NOT CONNECTED" ? "neutral" as const : "information" as const;

function ProgressBadge({ state }: { state: string }) {
  return <Badge variant={stateVariant(state)}>{state.replaceAll("_", " ")}</Badge>;
}

function ProgressGrid({ items }: { items: CommercialProgressItem[] }) {
  return <div className="grid gap-2 sm:grid-cols-2">{items.map((item) => <div className="flex items-start justify-between gap-3 rounded-lg border border-stroke p-3" key={item.id}><div><p className="font-semibold">{item.label}</p><p className="mt-1 text-sm text-content-muted">{item.detail}</p></div><ProgressBadge state={item.state} /></div>)}</div>;
}

export function CommercialOnboardingRoute() {
  const { activeCompany, user } = useAuth();
  if (!activeCompany) return <Alert variant="danger" title="Company unavailable">Choose an active Company before starting setup.</Alert>;
  return <CommercialOnboardingCompanyRoute key={`${activeCompany.id}:${activeCompany.name}`} activeCompany={activeCompany} user={user} />;
}

function CommercialOnboardingCompanyRoute({ activeCompany, user }: { activeCompany: AccessibleCompany; user: AuthenticatedUser | null }) {
  const navigate = useNavigate();
  const companyId = activeCompany.id;
  const [draft, setDraft] = useState<CommercialOnboardingDraft>(() => loadCommercialOnboardingDraft(companyId, activeCompany.name));
  const [supportMessage, setSupportMessage] = useState("");
  const [supportSent, setSupportSent] = useState(false);
  const evidence = useQuery({ queryKey: ["commercial-onboarding-evidence", companyId], queryFn: getCommercialOnboardingEvidence, enabled: companyId !== "no-company", retry: false });
  const lia = useLiaReadiness();
  const support = useMutation({ mutationFn: createMigrationSupportCase });

  useEffect(() => {
    saveCommercialOnboardingDraft(companyId, draft);
  }, [companyId, draft]);

  const update = (changes: Partial<CommercialOnboardingDraft>) => setDraft((current) => ({ ...current, ...changes }));
  const stepIndex = steps.findIndex((step) => step.id === draft.step);
  const progress = evidence.data;
  const exceptions = useMemo(() => progress?.exceptions ?? [], [progress]);
  const openExceptions = exceptions.filter((item) => !draft.deferredExceptionIds.includes(item.id));
  const readinessTitle = progress && progress.migrationAvailable && exceptions.length === 0 && draft.crm && draft.accounting ? "YOUR COMPANY IS READY" : `${exceptions.length || 1} ITEM${exceptions.length === 1 ? "" : "S"} NEED REVIEW`;
  const apiMessage = evidence.isError ? getOperatorApiError(evidence.error, "onboarding status").message : undefined;

  const move = (step: CommercialOnboardingStep) => update({ step });
  const next = () => move(steps[Math.min(stepIndex + 1, steps.length - 1)].id);
  const back = () => move(steps[Math.max(stepIndex - 1, 0)].id);
  const deferException = (id: string) => update({ deferredExceptionIds: [...new Set([...draft.deferredExceptionIds, id])] });
  const submitSupport = (event: FormEvent) => {
    event.preventDefault();
    if (!supportMessage.trim()) return;
    support.mutate(
      { onboarding_stage: draft.step, domain: "migration", message: supportMessage.trim() },
      { onSuccess: () => setSupportSent(true) },
    );
  };

  return <div className="space-y-6">
    <header className="primary-work-panel rounded-2xl border-2 p-5 sm:p-7">
      <p className="text-sm font-semibold uppercase tracking-wide text-action-primary">Welcome to TwelveHats</p>
      <h1 className="mt-2 text-3xl font-bold sm:text-4xl">Set up your company</h1>
      <p className="mt-3 max-w-3xl text-content-muted">Connect the systems you already use. TwelveHats will import your business, show you the few items that need a decision, and tell you when you are ready to get to work.</p>
      <div className="mt-6 grid gap-2 sm:grid-cols-5">{steps.map((step, index) => <button type="button" key={step.id} onClick={() => move(step.id)} className={`flex items-center gap-2 rounded-lg border p-3 text-left text-sm ${step.id === draft.step ? "border-action-primary bg-action-primary/10" : "border-stroke bg-surface/70"}`}><span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-action-primary text-sm font-bold text-content-inverse">{index < stepIndex ? <Check size={16} /> : index + 1}</span><span className="font-semibold">{step.label}</span></button>)}</div>
    </header>

    {draft.step === "company" && <Card className="primary-work-panel"><CardHeader><CardTitle>Tell us about your company</CardTitle><p className="mt-2 text-sm text-content-muted">This helps us use the right language and time zone. You can change these details later.</p></CardHeader><CardContent><div className="grid gap-4 md:grid-cols-2"><label className="text-sm font-medium">Company name<Input className="mt-1" value={draft.companyName} onChange={(event) => update({ companyName: event.target.value })} /></label><label className="text-sm font-medium">Business type<Select className="mt-1" value={draft.businessType} onChange={(event) => update({ businessType: event.target.value })}><option value="">Choose one</option><option>Plumbing</option><option>HVAC</option><option>Electrical</option><option>Other home service</option></Select></label><label className="text-sm font-medium">Primary location<Input className="mt-1" placeholder="City, State" value={draft.primaryLocation} onChange={(event) => update({ primaryLocation: event.target.value })} /></label><label className="text-sm font-medium">Time zone<Select className="mt-1" value={draft.timezone} onChange={(event) => update({ timezone: event.target.value })}><option>America/New_York</option><option>America/Chicago</option><option>America/Denver</option><option>America/Los_Angeles</option></Select></label></div><div className="mt-5 rounded-lg bg-surface-subtle p-4 text-sm"><strong>Owner / administrator</strong><p className="mt-1 text-content-muted">{user?.display_name ?? "Current signed-in administrator"}{user?.normalized_email ? ` · ${user.normalized_email}` : ""}</p></div><div className="mt-6 flex justify-end"><Button onClick={next} disabled={!draft.companyName.trim() || !draft.businessType || !draft.primaryLocation.trim()} trailingIcon={<ArrowRight size={17} />}>Continue to systems</Button></div></CardContent></Card>}

    {draft.step === "systems" && <Card className="primary-work-panel"><CardHeader><CardTitle>What do you use today?</CardTitle><p className="mt-2 text-sm text-content-muted">Choose the systems your team uses now. You can choose different providers for each part of the business.</p></CardHeader><CardContent><div className="grid gap-4 md:grid-cols-3"><label className="text-sm font-medium">Service business system<Select className="mt-1" value={draft.crm} onChange={(event) => update({ crm: event.target.value })}><option value="">Choose one</option><option>Housecall Pro</option><option>ServiceTitan</option><option>Jobber</option><option>Other</option></Select></label><label className="text-sm font-medium">Accounting<Select className="mt-1" value={draft.accounting} onChange={(event) => update({ accounting: event.target.value })}><option value="">Choose one</option><option>QuickBooks</option><option>Xero</option><option>Sage</option><option>Other</option></Select></label><label className="text-sm font-medium">Payroll<Select className="mt-1" value={draft.payroll} onChange={(event) => update({ payroll: event.target.value })}><option value="same">Same as accounting</option><option>Separate payroll provider</option><option>Other</option><option>Not currently using payroll software</option></Select></label></div><div className="mt-6 flex justify-between gap-3"><Button variant="secondary" onClick={back} leadingIcon={<ArrowLeft size={17} />}>Back</Button><Button onClick={next} disabled={!draft.crm || !draft.accounting} trailingIcon={<ArrowRight size={17} />}>See import progress</Button></div></CardContent></Card>}

    {draft.step === "import" && <Card className="primary-work-panel"><CardHeader><div className="flex flex-wrap items-center justify-between gap-3"><div><CardTitle>We are bringing your business over</CardTitle><p className="mt-2 text-sm text-content-muted">These statuses come from the connected systems. TwelveHats will never mark a category complete without source evidence.</p></div><Button variant="outline" size="small" onClick={() => void evidence.refetch()} leadingIcon={<RefreshCw size={16} />}>Refresh status</Button></div></CardHeader><CardContent>{evidence.isLoading ? <Spinner label="Loading import status" /> : apiMessage ? <Alert variant="warning" title="Import status needs attention">{apiMessage} No completion has been assumed.</Alert> : progress ? <><div className="mb-4 grid gap-3 sm:grid-cols-2">{progress.connections.map((connection) => <div className="rounded-lg border border-stroke p-4" key={connection.id}><div className="flex items-center justify-between gap-3"><strong>{connection.label}</strong><ProgressBadge state={connection.state} /></div><p className="mt-2 text-sm text-content-muted">{connection.detail}</p></div>)}</div><ProgressGrid items={progress.progress} /></> : null}<div className="mt-6 flex justify-between gap-3"><Button variant="secondary" onClick={back} leadingIcon={<ArrowLeft size={17} />}>Back</Button><Button onClick={next} trailingIcon={<ArrowRight size={17} />}>Review what needs attention</Button></div></CardContent></Card>}

    {draft.step === "review" && <Card className="primary-work-panel"><CardHeader><CardTitle>Review a few exceptions</CardTitle><p className="mt-2 text-sm text-content-muted">Only items that need a human decision appear here. Nothing is activated or overwritten for you.</p></CardHeader><CardContent>{evidence.isLoading ? <Spinner label="Loading review items" /> : openExceptions.length ? <div className="space-y-3">{openExceptions.map((item) => <ExceptionCard exception={item} key={item.id} onDefer={() => deferException(item.id)} />)}</div> : exceptions.length ? <Alert variant="warning" title="Some items are deferred">You chose to review these later. They remain unresolved and keep the company from being marked ready.</Alert> : <Alert variant="success" title="Nothing needs your decision right now">The source-backed migration status has no open customer decisions.</Alert>}<div className="mt-6 flex justify-between gap-3"><Button variant="secondary" onClick={back} leadingIcon={<ArrowLeft size={17} />}>Back</Button><Button onClick={next} trailingIcon={<ArrowRight size={17} />}>See readiness</Button></div></CardContent></Card>}

    {draft.step === "ready" && <><Card className="primary-work-panel"><CardHeader><div className="flex items-center gap-3"><Sparkles className="text-action-primary" /><div><CardTitle>{readinessTitle}</CardTitle><p className="mt-2 text-sm text-content-muted">Here is the honest status of your TwelveHats setup.</p></div></div></CardHeader><CardContent><div className="grid gap-3 sm:grid-cols-2"><div className="rounded-lg bg-surface-subtle p-4"><strong>Systems selected</strong><p className="mt-1 text-sm text-content-muted">{[draft.crm, draft.accounting, draft.payroll === "same" ? "Payroll follows accounting" : draft.payroll].filter(Boolean).join(" · ") || "None yet"}</p></div><div className="rounded-lg bg-surface-subtle p-4"><strong>Open decisions</strong><p className="mt-1 text-sm text-content-muted">{exceptions.length} source-backed item{exceptions.length === 1 ? "" : "s"} need review.</p></div></div>{progress && <div className="mt-5"><ProgressGrid items={progress.progress} /></div>}{!progress?.migrationAvailable && <Alert className="mt-5" variant="warning" title="We are still waiting on import evidence">TwelveHats has not assumed a successful import. Refresh this page after the connection is available or ask for help.</Alert>}{exceptions.length > 0 && <Alert className="mt-5" variant="warning" title="Review is still required">Deferring an item keeps it visible to the company team and does not certify the migration.</Alert>}<div className="mt-6 flex flex-wrap justify-between gap-3"><Button variant="secondary" onClick={back} leadingIcon={<ArrowLeft size={17} />}>Back</Button><div className="flex flex-wrap gap-2"><Button variant="outline" onClick={() => update({ completed: false, step: "import" })}>Keep reviewing</Button><Button disabled={!progress?.migrationAvailable || exceptions.length > 0} onClick={() => { update({ completed: true }); navigate("/command-center"); }}>Continue to TwelveHats</Button></div></div></CardContent></Card><SupportCard companyName={activeCompany.name} stage={draft.step} sent={supportSent} message={supportMessage} setMessage={setSupportMessage} onSubmit={submitSupport} /></>}

    <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-content-muted"><span>Saved for {activeCompany.name}. You can close this page and come back later.</span><Link className="font-semibold text-action-primary" to="/lia?contextDomain=migration">Ask LIA what this means <CircleHelp className="inline size-4" /></Link><span className="sr-only">LIA status: {lia.isSuccess ? "available" : "checking"}</span></div>
  </div>;
}

function ExceptionCard({ exception, onDefer }: { exception: CommercialException; onDefer: () => void }) {
  return <article className="rounded-xl border border-status-warning/40 bg-status-warning/10 p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div><Badge variant="warning">{exception.domain}</Badge><h3 className="mt-2 text-lg font-semibold">{exception.title}</h3></div><Button size="small" variant="outline" onClick={onDefer}>I’ll review this</Button></div><p className="mt-3 text-sm"><strong>Why it matters:</strong> {exception.whyItMatters}</p><p className="mt-2 text-sm"><strong>Recommended action:</strong> {exception.recommendedAction}</p><div className="mt-4 flex flex-wrap gap-2"><Link className="inline-flex min-h-11 items-center rounded-md border border-stroke px-3 text-sm font-semibold" to={`/lia?contextDomain=${exception.domain.toLowerCase().includes("price") ? "price-book" : "migration"}`}>Ask LIA</Link><a className="inline-flex min-h-11 items-center rounded-md border border-stroke px-3 text-sm font-semibold" href="#support">Get Help</a></div></article>;
}

function SupportCard({ companyName, stage, sent, message, setMessage, onSubmit }: { companyName: string; stage: string; sent: boolean; message: string; setMessage: (value: string) => void; onSubmit: (event: FormEvent) => void }) {
  return <Card id="support" className="primary-work-panel"><CardHeader><CardTitle className="flex items-center gap-2"><LifeBuoy size={19} />Need help?</CardTitle><p className="mt-2 text-sm text-content-muted">Tell the TwelveHats team what you need. We will include your company and current setup stage so you do not have to explain the technical details.</p></CardHeader><CardContent>{sent ? <Alert variant="success" title="Your help request was sent">The TwelveHats support team has your company, onboarding stage, source context, and message. Reference: {companyName.replaceAll(" ", "-").toLowerCase()}-{stage}.</Alert> : <form className="space-y-3" onSubmit={onSubmit}><Textarea aria-label="How can we help?" required value={message} onChange={(event) => setMessage(event.target.value)} placeholder="What is stopping you from moving forward?" /><Button type="submit">Get Help</Button></form>}</CardContent></Card>;
}
