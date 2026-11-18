import { useState } from "react";
import { Link } from "react-router";
import { Alert, Button, Card, Input } from "../ui";
import { useAuth } from "../auth";
import { useDemoFeedback, useDemoScenarios, useDemoSignals, useResetDemo } from "../hooks/useDemo";

const destinations: Record<string, string> = {
  new_service_call: "/customers", emergency_drain: "/dispatch", water_heater_estimate: "/estimates",
  dispatch_conflict: "/dispatch", overdue_ar: "/invoices", margin_problem: "/luminary",
  inventory_shortage: "/inventory", owner_morning_review: "/command-center",
};

export function SalesDemoRoute() {
  const { refreshAuthorization } = useAuth();
  const scenarios = useDemoScenarios();
  const signals = useDemoSignals();
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
      <div><p className="text-sm font-medium text-action-primary">TwelveHats Demo Services</p><h2 className="mt-1 text-2xl font-bold sm:text-3xl">Sales training</h2><p className="mt-2 max-w-3xl text-content-muted">Practice in your isolated, synthetic company. Messages, payments, payroll, tax filing, and integrations are simulated and cannot create real-world activity.</p></div>
      <div className="flex flex-wrap gap-2"><Button variant="secondary" onClick={() => setGuided((value) => !value)}>{guided ? "Hide guide" : "Start demo"}</Button><Button variant="destructive" loading={reset.isPending} onClick={() => void performReset()}>Reset Demo Company</Button></div>
    </header>
    {reset.isSuccess && <Alert variant="success" title="Demo restored">Generation {reset.data.generation} is ready. The previous tenant was deactivated and your original scenarios were restored.</Alert>}
    {reset.isError && <Alert variant="danger" title="Reset could not complete">Trusted demo state was not changed. Try again or report the issue.</Alert>}
    {guided && <section aria-labelledby="demo-scenarios"><h3 id="demo-scenarios" className="text-xl font-semibold">Choose a guided scenario</h3><div className="mt-3 grid gap-4 md:grid-cols-2">{scenarios.data?.map((scenario) => <Card className="p-5" key={scenario.code}><p className="text-xs font-semibold uppercase tracking-wide text-action-primary">Scenario {scenario.position}</p><h4 className="mt-1 text-lg font-semibold">{scenario.title}</h4><ol className="mt-3 space-y-1 text-sm text-content-muted">{scenario.guided_steps.map((step) => <li key={step.order}>{step.order}. {step.action}</li>)}</ol><Link className="mt-4 inline-block font-semibold text-action-primary" to={destinations[scenario.code]}>Start scenario</Link></Card>)}</div></section>}
    <section aria-labelledby="demo-intelligence"><h3 id="demo-intelligence" className="text-xl font-semibold">Business intelligence grounded in demo records</h3><div className="mt-3 grid gap-4 lg:grid-cols-2">{signals.data?.map((signal) => <Card className="p-5" key={signal.scenario_code}><p className="text-xs font-semibold text-action-primary">{signal.source}</p><h4 className="mt-1 font-semibold">{signal.title}</h4><p className="mt-2 text-sm text-content-muted">{signal.explanation}</p><p className="mt-3 text-sm"><strong>Recommended:</strong> {signal.recommendation}</p><Link className="mt-3 inline-block font-semibold text-action-primary" to={destinations[signal.scenario_code]}>Open source records</Link></Card>)}</div></section>
    <Card className="p-5"><h3 className="text-lg font-semibold">Share sales feedback</h3><p className="mt-1 text-sm text-content-muted">The current page, user, tenant, timestamp, scenario, and application version are captured with your note.</p><div className="mt-4 grid gap-3 sm:grid-cols-[12rem_1fr_auto]"><label className="text-sm">Type<select className="mt-1 min-h-11 w-full rounded-md border border-stroke bg-surface px-3" value={category} onChange={(event) => setCategory(event.target.value)}><option value="confusing">Confusing</option><option value="bug">Bug</option><option value="missing_feature">Missing feature</option><option value="customer_objection">Customer objection</option><option value="sales_idea">Sales idea</option></select></label><label className="text-sm">Comment<Input className="mt-1" value={comment} onChange={(event) => setComment(event.target.value)} /></label><Button className="self-end" disabled={!comment.trim()} loading={feedback.isPending} onClick={() => feedback.mutate({ category, page: window.location.pathname, comment, app_sha: import.meta.env.VITE_APP_SHA || "development" }, { onSuccess: () => setComment("") })}>Send feedback</Button></div>{feedback.isSuccess && <p className="mt-3 text-sm text-success">Feedback recorded.</p>}</Card>
  </div>;
}
