import * as Speech from "expo-speech";
import type { LiaResponse } from "../api/lia";

export type SpeechOptions = { language?: string; rate?: number; pitch?: number; onDone?: () => void };
export interface SpeechAdapter { speak(text: string, options?: SpeechOptions): void; stop(): void; }

const sentenceBudget = { BRIEF: 2, NORMAL: 3, DETAILED: 6, EVIDENCE: 8 } as const;
const terms: ReadonlyArray<readonly [RegExp, string]> = [
  [/\bCOMPENSATION_MISSING_CONFIGURATION\b/g, "compensation setup is missing"],
  [/\bGROSS_PAY_NOT_CALCULATED\b/g, "gross pay hasn't been calculated"],
  [/\bPAYROLL_POLICY_MISSING_CONFIGURATION\b/g, "payroll policy setup is incomplete"],
  [/\bTIME_EVIDENCE_MISSING\b/g, "accepted time is missing"],
  [/\bWITHHOLDING_NOT_CALCULATED\b/g, "withholding hasn't been calculated"],
  [/\bP\s*&\s*L\b/gi, "profit and loss"],
  [/\bQBO\b/g, "Q B O"],
  [/\bACP\b/g, "A C P"],
  [/\b(?:Job\s+)?JOB-(\d+)\b/gi, "Job $1"],
  [/\b(?:Invoice\s+)?INV-(\d+)\b/gi, "Invoice $1"],
  [/\b(?:Estimate\s+)?EST-(\d+)\b/gi, "Estimate $1"],
  [/\b(?:Appointment\s+)?APT-(\d+)\b/gi, "Appointment $1"],
  [/\bcannot\b/gi, "can't"],
  [/\bis not\b/gi, "isn't"],
  [/\bare not\b/gi, "aren't"],
  [/\bdoes not\b/gi, "doesn't"],
  [/\bhas not\b/gi, "hasn't"],
];

function clean(value: string): string {
  let text = value
    .replace(/\bNo authorized authoritative evidence is available for this question\b/gi, "I don't have authorized evidence for that yet")
    .replace(/\bEvidence unavailable\b/gi, "I don't have that evidence yet")
    .replace(/^ACP's native authorized records show:\s*/i, "")
    .replace(/^Current authorized evidence\s*[—:-]\s*/i, "")
    .replace(/^Answer\s*:\s*/i, "")
    .replace(/^Correction\s*:\s*/i, "Got it — ")
    .replace(/^Topic changed\s*:\s*(.)/i, (_match, first: string) => `Now, ${first.toLocaleLowerCase()}`)
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/(^|[.!?]\s+)(?:\d+[.)]|(?:what is true|what is blocked|why|next step|evidence))\s*[:—-]?\s*/gim, "$1")
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/gi, "the selected record")
    .replace(/^[-*•]\s*/gm, "")
    .replace(/\n\s*[-*•]?\s*/g, ". ")
    .replace(/\s*\|\s*/g, ". ")
    .replace(/(^|[\s(])-\$(\d[\d,]*(?:\.\d+)?)/g, "$1negative $$$2")
    .replace(/(^|[\s(])-([\d,.]+)%(?=\s|[,.!?;:]|$)/g, "$1negative $2 percent")
    .replace(/([\d,.]+)%(?=\s|[,.!?;:]|$)/g, "$1 percent")
    .replace(/\s+/g, " ")
    .trim();
  for (const [pattern, replacement] of terms) text = text.replace(pattern, replacement);
  return text
    .replace(/\.{2,}/g, ".")
    .replace(/\s+([,.!?])/g, "$1")
    .trim();
}

function sentences(value: string): string[] {
  return (value.match(/.*?[.!?]+(?=\s|$)|.+$/g) ?? [value]).map((item) => item.trim()).filter(Boolean);
}

function evidenceSummary(response: LiaResponse): string {
  const labels = [...new Set(response.evidence.map((item) => item.label.trim()).filter(Boolean))];
  return labels.length
    ? `The supporting evidence comes from ${labels.slice(0, 3).join(", ")}.`
    : "No supporting evidence was available for this answer.";
}

function naturalNextAction(value: string): string {
  const action = value.trim().replace(/[.!?]+$/, "");
  const open = action.match(/^Open\s+(.+)$/i);
  if (open) return `You can open ${open[1]} next.`;
  const review = action.match(/^Review\s+(.+)$/i);
  if (review) return `The next step is to review ${review[1]}.`;
  const refresh = action.match(/^Refresh\s+(.+)$/i);
  if (refresh) return `Refresh ${refresh[1]} before relying on this.`;
  return `The next safe step is to ${action.charAt(0).toLowerCase()}${action.slice(1)}.`;
}

function mentionsAction(answer: string, action: string): boolean {
  const normalized = action.replace(/^(open|review|refresh)\s+/i, "").toLocaleLowerCase();
  return normalized.length > 3 && answer.toLocaleLowerCase().includes(normalized);
}

/** The authorized response envelope is the sole semantic input to native speech. */
export function spokenTextForResponse(response: LiaResponse): string {
  const mode = response.response_mode;
  let spoken = sentences(clean(response.answer)).slice(0, sentenceBudget[mode]).join(" ");
  if (response.authority === "SOURCE_BACKED" && !/source[- ]backed|source evidence|quickbooks/i.test(spoken)) {
    spoken += " That's source-backed evidence, not an A C P-native fact.";
  }
  const next = response.safe_next_action?.trim();
  if (next && mode !== "EVIDENCE" && !mentionsAction(spoken, next) && !/^Refresh authoritative ACP evidence$/i.test(next)) {
    spoken += ` ${naturalNextAction(next)}`;
  }
  if (mode === "EVIDENCE") spoken += ` ${evidenceSummary(response)}`;
  return spoken.trim();
}

export const nativeSpeech: SpeechAdapter = {
  speak: (text, options) => { if (!text) return; Speech.speak(text, { language: options?.language ?? "en-US", rate: options?.rate ?? 0.94, pitch: options?.pitch ?? 1.0, onDone: options?.onDone, onStopped: options?.onDone }); },
  stop: () => { Speech.stop(); },
};
