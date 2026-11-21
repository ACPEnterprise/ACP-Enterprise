import { useState } from "react";
import { Link } from "react-router";
import { Alert, Button, Card, Input } from "../ui";
import { useAuth } from "../auth";
import { useDemoFeedback, useDemoScenarios, useResetDemo } from "../hooks/useDemo";

const destinations: Record<string, string> = {
  new_service_call: "/customers", emergency_drain: "/dispatch", water_heater_estimate: "/estimates",
  dispatch_conflict: "/dispatch", overdue_ar: "/invoices", margin_problem: "/luminary",
  inventory_shortage: "/inventory", owner_morning_review: "/command-center",
};

const showcases = [
  { title: "Command Center", eyebrow: "Executive overview", path: "/command-center", description: "Open the business pulse, receivables exposure, operational exceptions, and evidence behind each finding.", intelligence: "Beacon attention + Luminary analysis + LIA guidance" },
  { title: "Accounting", eyebrow: "Financial intelligence", path: "/financial-reports", description: "Review synthetic performance, posted invoices, receivables, vendor obligations, and the financial impact of exceptions.", intelligence: "Evidence-backed analysis; no banking or money movement" },
  { title: "Dispatch", eyebrow: "Operational intelligence", path: "/dispatch", description: "Inspect the daily board, assigned technicians, two intentional openings, and an overlapping appointment condition.", intelligence: "Beacon detection + capacity and revenue opportunity" },
  { title: "Estimating", eyebrow: "Profitable selling", path: "/estimates", description: "Use the synthetic price book and customer records to discuss cost, selling price, gross profit, and margin risk.", intelligence: "Luminary profitability + LIA recommended next step" },
] as const;

function scenarioDestination(code: string, refs: Record<string, unknown> = {}) {
  if (typeof refs.invoice_id === "string") return `/invoices/${refs.invoice_id}`;
  if (typeof refs.job_id === "string") return `/jobs/${refs.job_id}`;
  if (typeof refs.customer_id === "string") return `/customers/${refs.customer_id}`;
  return destinations[code] ?? "/sales-demo";
}

export function SalesDemoRoute() {
  const { refreshAuthorization } = useAuth();
  const scenarios = useDemoScenarios();
  const reset = useResetDemo();
  const feedback = useDemoFeedback();
  const [guided, setGuided] = useState(true);
  const [category, setCategory] = useState("confusing");
  const [comment, setComment] = useState("");

  const performReset = async () => {
    if (!window.confirm("Reset this Demo Company? Your practice records will be replaced with the original synthetic scenarios.")) return;
    await reset.mutateAsync();
    await refreshAuthorization();
  };

  return <div className="space-y-6">
    <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div><p className="text-sm font-medium text-action-primary">Sales Forward · TwelveHats Demo Services</p><h2 className="mt-1 text-2xl font-bold sm:text-3xl">Intelligent contractor operations</h2><p className="mt-2 max-w-3xl text-content-muted">A tenant-isolated synthetic company for showing how TwelveHats turns operational and financial records into decisions. Payments, payroll, tax filing, banking, messages, and external integrations cannot create real-world activity.</p></div>
      <div className="flex flex-wrap gap-2"><Button variant="secondary" onClick={() => setGuided((value) => !value)}>{guided ? "Hide guide" : "Start demo"}</Button><Button variant="destructive" loading={reset.isPending} onClick={() => void performReset()}>Reset Demo Company</Button></div>
    </header>
    {reset.isSuccess && <Alert variant="success" title="Demo restored">Generation {reset.data.generation} is ready. The previous tenant was deactivated and your original scenarios were restored.</Alert>}
    {reset.isError && <Alert variant="danger" title="Reset could not complete">Trusted demo state was not changed. Try again or report the issue.</Alert>}
    <section aria-labelledby="showcase-journeys"><div className="flex flex-wrap items-end justify-between gap-2"><div><p className="text-xs font-semibold uppercase tracking-wide text-action-primary">Four-part presentation</p><h3 id="showcase-journeys" className="mt-1 text-xl font-semibold">Choose a showcase</h3></div><p className="text-sm text-content-muted">Every value originates in this synthetic tenant.</p></div><div className="mt-3 grid gap-4 md:grid-cols-2 xl:grid-cols-4">{showcases.map((showcase, index) => <Card className="flex h-full flex-col p-5" key={showcase.title}><p className="text-xs font-semibold uppercase tracking-wide text-action-primary">{index + 1}. {showcase.eyebrow}</p><h4 className="mt-2 text-lg font-semibold">{showcase.title}</h4><p className="mt-2 flex-1 text-sm text-content-muted">{showcase.description}</p><p className="mt-4 rounded-md bg-surface-subtle p-3 text-xs font-medium">{showcase.intelligence}</p><Link className="mt-4 font-semibold text-action-primary" to={showcase.path}>Open {showcase.title}</Link></Card>)}</div></section>
    <section aria-labelledby="demo-intelligence"><h3 id="demo-intelligence" className="text-xl font-semibold">Working intelligence, clearly labeled</h3><p className="mt-2 text-sm text-content-muted">The guided steps are a presentation script. Beacon conditions, Luminary analysis, and LIA responses run through the product's tenant-scoped intelligence services using synthetic records.</p><div className="mt-3 grid gap-4 md:grid-cols-3"><Card className="p-5"><p className="text-xs font-semibold uppercase tracking-wide text-success">Live service · synthetic evidence</p><h4 className="mt-1 font-semibold">Beacon</h4><p className="mt-2 text-sm text-content-muted">Detect overdue receivables, dispatch openings, conflicts, inventory shortages, and other conditions requiring attention.</p><Link className="mt-3 inline-block font-semibold text-action-primary" to="/command-center">Open Beacon</Link></Card><Card className="p-5"><p className="text-xs font-semibold uppercase tracking-wide text-success">Live service · synthetic evidence</p><h4 className="mt-1 font-semibold">Luminary</h4><p className="mt-2 text-sm text-content-muted">Explain financial and operational performance, including negative job margin and capacity opportunity.</p><Link className="mt-3 inline-block font-semibold text-action-primary" to="/luminary">Open Luminary</Link></Card><Card className="p-5"><p className="text-xs font-semibold uppercase tracking-wide text-success">Live service · bounded recommendations</p><h4 className="mt-1 font-semibold">LIA</h4><p className="mt-2 text-sm text-content-muted">Provide evidence-bound explanations and recommended next steps without executing payments, payroll, banking, tax, or external communication.</p><Link className="mt-3 inline-block font-semibold text-action-primary" to="/lia">Open LIA</Link></Card></div></section>
    {guided && <section aria-labelledby="demo-scenarios"><h3 id="demo-scenarios" className="text-xl font-semibold">Eight guided scenarios</h3><p className="mt-2 text-sm text-content-muted">Scripted talk tracks open working product records; they are not AI-generated claims.</p><div className="mt-3 grid gap-4 md:grid-cols-2">{scenarios.data?.map((scenario) => <Card className="p-5" key={scenario.code}><p className="text-xs font-semibold uppercase tracking-wide text-action-primary">Scenario {scenario.position}</p><h4 className="mt-1 text-lg font-semibold">{scenario.title}</h4><ol className="mt-3 space-y-1 text-sm text-content-muted">{scenario.guided_steps.map((step) => <li key={step.order}>{step.order}. {step.action}</li>)}</ol><Link className="mt-4 inline-block font-semibold text-action-primary" to={scenarioDestination(scenario.code, scenario.record_refs)}>Open evidence</Link></Card>)}</div></section>}
    <Card className="p-5"><h3 className="text-lg font-semibold">Share sales feedback</h3><p className="mt-1 text-sm text-content-muted">The current page, user, tenant, timestamp, scenario, and application version are captured with your note.</p><div className="mt-4 grid gap-3 sm:grid-cols-[12rem_1fr_auto]"><label className="text-sm">Type<select className="mt-1 min-h-11 w-full rounded-md border border-stroke bg-surface px-3" value={category} onChange={(event) => setCategory(event.target.value)}><option value="confusing">Confusing</option><option value="bug">Bug</option><option value="missing_feature">Missing feature</option><option value="customer_objection">Customer objection</option><option value="sales_idea">Sales idea</option></select></label><label className="text-sm">Comment<Input className="mt-1" value={comment} onChange={(event) => setComment(event.target.value)} /></label><Button className="self-end" disabled={!comment.trim()} loading={feedback.isPending} onClick={() => feedback.mutate({ category, page: window.location.pathname, comment, app_sha: import.meta.env.VITE_APP_SHA || "development" }, { onSuccess: () => setComment("") })}>Send feedback</Button></div>{feedback.isSuccess && <p className="mt-3 text-sm text-success">Feedback recorded.</p>}</Card>
  </div>;
}
