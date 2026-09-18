import * as Speech from "expo-speech";
import type { LiaResponse } from "../api/lia";
import { z } from "zod";

export type SpeechOptions = { language?: string; rate?: number; pitch?: number; onDone?: () => void };
export interface SpeechAdapter { speak(text: string, options?: SpeechOptions): void; stop(): void; }
export type SpeechRendererKind = "DEVICE_LOCAL_FALLBACK" | "TWELVE_HATS_SPEECH";
export const ACTIVE_SPEECH_RENDERER: SpeechRendererKind = "DEVICE_LOCAL_FALLBACK";

export const twelveHatsAudioSchema = z.object({
  audio: z.string().min(1), content_type: z.string().min(1), duration_ms: z.number().int().nonnegative(),
  model_version: z.string().min(1), render_version: z.string().min(1), render_digest: z.string().regex(/^[a-f0-9]{64}$/),
});
export type TwelveHatsAudio = z.infer<typeof twelveHatsAudioSchema>;

/** Reserved owned-engine boundary. It is intentionally unavailable until a governed contract is released. */
export const twelveHatsSpeech: SpeechAdapter | null = null;

const sentenceBudget = { BRIEF: 2, NORMAL: 3, DETAILED: 6, EVIDENCE: 8 } as const;
const spokenTerms: ReadonlyArray<readonly [RegExp, string]> = [
  [/\bCOMPENSATION_MISSING_CONFIGURATION\b/g, "compensation setup is missing"],
  [/\bGROSS_PAY_NOT_CALCULATED\b/g, "gross pay hasn't been calculated"],
  [/\bPAYROLL_POLICY_MISSING_CONFIGURATION\b/g, "payroll policy setup is incomplete"],
  [/\bTIME_EVIDENCE_MISSING\b/g, "accepted time is missing"],
  [/\bP\s*&\s*L\b/gi, "profit and loss"], [/\bQBO\b/g, "Q B O"], [/\bACP\b/g, "A C P"],
  [/\b(?:Job\s+)?JOB-(\d+)\b/gi, "Job $1"], [/\b(?:Invoice\s+)?INV-(\d+)\b/gi, "Invoice $1"],
  [/\bcannot\b/gi, "can't"], [/\bis not\b/gi, "isn't"], [/\bare not\b/gi, "aren't"],
];
function cleanSpoken(value: string): string {
  let text = value.replace(/\bNo authorized authoritative evidence is available for this question\b/gi, "I don't have authorized evidence for that yet")
    .replace(/\bEvidence unavailable\b/gi, "I don't have that evidence yet")
    .replace(/^ACP's native authorized records show:\s*/i, "").replace(/^Answer\s*:\s*/i, "")
    .replace(/^Correction\s*:\s*/i, "Got it — ").replace(/^#{1,6}\s*/gm, "")
    .replace(/(^|[.!?]\s+)(?:\d+[.)]|(?:what is true|what is blocked|why|next step|evidence))\s*[:—-]?\s*/gim, "$1")
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/gi, "the selected record")
    .replace(/^[-*•]\s*/gm, "").replace(/\n\s*[-*•]?\s*/g, ". ").replace(/\s*\|\s*/g, ". ")
    .replace(/\s+/g, " ").trim();
  for (const [pattern, replacement] of spokenTerms) text = text.replace(pattern, replacement);
  return text.replace(/\s+([,.!?])/g, "$1").trim();
}
function spokenSentences(value: string): string[] { return (value.match(/.*?[.!?]+(?=\s|$)|.+$/g) ?? [value]).map((item) => item.trim()).filter(Boolean); }
function evidenceSummary(response: LiaResponse): string {
  const labels = [...new Set(response.evidence.map((item) => item.label.trim()).filter(Boolean))];
  return labels.length ? `The supporting evidence comes from ${labels.slice(0, 3).join(", ")}.` : "No supporting evidence was available for this answer.";
}
function nextAction(value: string): string { const action = value.trim().replace(/[.!?]+$/, ""); return `The next safe step is to ${action.charAt(0).toLowerCase()}${action.slice(1)}.`; }
/** Shared spoken semantics are the sole semantic input to native speech. */
export function spokenTextForResponse(response: LiaResponse): string {
  let spoken = spokenSentences(cleanSpoken(response.answer)).slice(0, sentenceBudget[response.response_mode]).join(" ");
  if (response.authority === "SOURCE_BACKED" && !/source[- ]backed|source evidence|quickbooks/i.test(spoken)) spoken += " That's source-backed evidence, not an A C P-native fact.";
  const action = response.safe_next_action?.trim();
  if (action && response.response_mode !== "EVIDENCE" && !spoken.toLocaleLowerCase().includes(action.toLocaleLowerCase()) && !/^Refresh authoritative ACP evidence$/i.test(action)) spoken += ` ${nextAction(action)}`;
  if (response.response_mode === "EVIDENCE") spoken += ` ${evidenceSummary(response)}`;
  return spoken.trim();
}

export const nativeSpeech: SpeechAdapter = {
  speak: (text, options) => { if (!text) return; Speech.speak(text, { language: options?.language ?? "en-US", rate: options?.rate ?? 0.94, pitch: options?.pitch ?? 1.0, onDone: options?.onDone, onStopped: options?.onDone }); },
  stop: () => { Speech.stop(); },
};
