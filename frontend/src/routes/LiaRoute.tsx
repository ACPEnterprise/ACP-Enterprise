import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { Bot, ChevronDown, ShieldCheck, Sparkles } from "lucide-react";

import { useAskLia, useLiaFoundationReadiness, useLiaReadiness, useOwnerBriefing } from "../hooks/useLia";
import type { LiaResponse } from "../types/lia";
import { Alert, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Spinner } from "../ui";

const prompts = [
  "How are we doing today?",
  "What needs my attention?",
  "What invoices remain outstanding?",
  "What purchasing or inventory issues need attention?",
  "What information is incomplete?",
];

const tone = (classification: LiaResponse["classification"]) =>
  classification === "KNOWN" || classification === "DERIVED" ? "success" :
  classification === "UNAUTHORIZED" || classification === "CONFLICTING" ? "danger" : "warning";

function Answer({ result }: { result: LiaResponse }) {
  const navigate = useNavigate();
  return <article aria-live="polite" className="space-y-4">
    <Alert variant={tone(result.classification)} title={result.classification.replaceAll("_", " ")}>{result.answer}</Alert>
    {result.evidence.length ? <Card><CardHeader><CardTitle>Why LIA said this</CardTitle><CardDescription>Authorized ACP evidence queried for this answer.</CardDescription></CardHeader><CardContent className="space-y-3">{result.evidence.map((item) => <details className="rounded-lg border border-stroke p-3" key={item.evidence_digest}><summary className="flex cursor-pointer list-none items-center justify-between gap-3 font-medium"><span>{item.label}</span><span className="text-sm text-content-muted">{item.count ?? "—"} records <ChevronDown className="ml-1 inline size-4" /></span></summary><p className="mt-2 text-sm text-content-muted">{item.state}. {item.authority.replaceAll("_", " ")} · {item.freshness.replaceAll("_", " ")}.</p></details>)}</CardContent></Card> : null}
    {result.limitations.length ? <Card><CardHeader><CardTitle>Limits</CardTitle></CardHeader><CardContent><ul className="list-disc space-y-2 pl-5 text-sm text-content-muted">{result.limitations.map((item) => <li key={item}>{item}</li>)}</ul></CardContent></Card> : null}
    {result.navigation.length ? <div className="flex flex-wrap gap-2">{result.navigation.map((item) => <Button variant="secondary" key={item.internal_path} onClick={() => navigate(item.internal_path)}>{item.label}</Button>)}</div> : null}
  </article>;
}

export function LiaRoute() {
  const readiness = useLiaReadiness();
  const foundation = useLiaFoundationReadiness();
  const briefing = useOwnerBriefing();
  const ask = useAskLia();
  const [question, setQuestion] = useState("");
  const [conversationId, setConversationId] = useState<string>();
  const submit = (event: FormEvent) => { event.preventDefault(); const value = question.trim(); if (!value) return; ask.mutate({ question: value, conversation_id: conversationId }, { onSuccess: (result) => setConversationId(result.conversation_id) }); };
  const askPrompt = (value: string) => { setQuestion(value); ask.mutate({ question: value, conversation_id: conversationId }, { onSuccess: (result) => setConversationId(result.conversation_id) }); };
  return <div className="mx-auto max-w-5xl space-y-6 pb-28 sm:pb-12">
    <header className="rounded-2xl bg-gradient-to-br from-action-primary/15 to-surface p-5 sm:p-8"><div className="flex items-start gap-4"><div className="rounded-xl bg-action-primary p-3 text-white"><Bot aria-hidden className="size-6" /></div><div><p className="text-sm font-semibold text-action-primary">Governed intelligence</p><h1 className="mt-1 text-2xl font-bold sm:text-3xl">Ask LIA</h1><p className="mt-2 max-w-2xl text-content-muted">Understand ACP evidence, find what needs attention, and navigate to authoritative workflows. LIA explains and proposes—it does not silently execute business actions.</p></div></div></header>
    {readiness.isPending ? <Spinner label="Checking LIA readiness" /> : readiness.isError || !readiness.data ? <Alert variant="danger" title="LIA readiness unavailable">No readiness state was inferred. Retry when ACP connectivity is restored.</Alert> : <Alert variant={readiness.data.provider_state === "AI_PROVIDER_NOT_CONFIGURED" ? "warning" : "success"} title={readiness.data.state.replaceAll("_", " ")}><span className="inline-flex items-center gap-2"><ShieldCheck className="size-4" />Deterministic authorized retrieval is ready. {readiness.data.provider_state === "AI_PROVIDER_NOT_CONFIGURED" ? "Generative explanations await a separately configured provider." : "The configured provider is available."}</span></Alert>}
    {foundation.data ? <Card><CardHeader><CardTitle>LIA foundation readiness</CardTitle><CardDescription>This is a safety and evidence substrate—not a configured AI provider.</CardDescription></CardHeader><CardContent className="space-y-4"><dl className="grid gap-3 text-sm sm:grid-cols-3"><div><dt className="text-content-muted">Release profile</dt><dd className="font-semibold">{foundation.data.release_profile}</dd></div><div><dt className="text-content-muted">Provider</dt><dd className="font-semibold">{foundation.data.provider_state.replaceAll("_", " ")}</dd></div><div><dt className="text-content-muted">Autonomous mutation</dt><dd className="font-semibold">{foundation.data.autonomous_mutation ? "Enabled" : "Disabled"}</dd></div></dl><div><h2 className="font-semibold">Authorized context sources</h2><ul className="mt-2 grid gap-2 sm:grid-cols-2">{Object.entries(foundation.data.source_states).map(([source, state]) => <li className="flex justify-between rounded-md border border-stroke p-2 text-sm" key={source}><span>{source.replaceAll("_", " ")}</span><strong>{state}</strong></li>)}</ul></div>{foundation.data.blockers.length ? <details><summary className="cursor-pointer font-semibold">Explicit readiness gates</summary><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-content-muted">{foundation.data.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul></details> : null}</CardContent></Card> : foundation.isError ? <Alert variant="danger" title="Foundation readiness unavailable">No safety readiness was inferred.</Alert> : null}
    <Card><CardHeader><CardTitle className="flex items-center gap-2"><Sparkles className="size-5" />Owner briefing</CardTitle><CardDescription>Current evidence across the domains you are permitted to read.</CardDescription></CardHeader><CardContent>{briefing.isPending ? <Spinner label="Preparing briefing" /> : briefing.isError || !briefing.data ? <Alert variant="danger">The briefing could not be verified. No summary was fabricated.</Alert> : <Answer result={briefing.data} />}</CardContent></Card>
    <section><h2 className="mb-3 text-lg font-semibold">Try asking</h2><div className="flex snap-x gap-2 overflow-x-auto pb-2 sm:flex-wrap">{prompts.map((prompt) => <Button className="shrink-0 snap-start" key={prompt} variant="secondary" onClick={() => askPrompt(prompt)}>{prompt}</Button>)}</div></section>
    {ask.data ? <Answer result={ask.data} /> : null}
    {ask.isError ? <Alert variant="danger" title="LIA request unavailable">The request failed safely. No answer was inferred.</Alert> : null}
    <form className="fixed inset-x-0 bottom-0 z-20 border-t border-stroke bg-surface/95 p-3 backdrop-blur sm:static sm:rounded-xl sm:border" onSubmit={submit}><div className="mx-auto flex max-w-5xl gap-2"><Input aria-label="Ask LIA a question" autoComplete="off" placeholder="Ask about today, a Job, an Invoice, or readiness…" value={question} onChange={(event) => setQuestion(event.target.value)} /><Button disabled={ask.isPending || !question.trim()} type="submit">{ask.isPending ? "Checking…" : "Ask"}</Button></div></form>
  </div>;
}
