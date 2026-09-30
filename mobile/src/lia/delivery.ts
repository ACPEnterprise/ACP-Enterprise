import type { SpeechAdapter } from "./speech";

export type NativeDeliveryIntent =
  | "CONCISE_ANSWER"
  | "NEUTRAL_EXPLANATION"
  | "CLARIFICATION"
  | "QUESTION"
  | "REASSURANCE"
  | "WARNING"
  | "OWNER_BRIEF"
  | "STEP_BY_STEP";

export interface NativeThoughtGroup {
  text: string;
  pauseAfterMs: number;
  rate: number;
  pitch: number;
}

export interface NativeDeliveryPlan {
  semanticText: string;
  intent: NativeDeliveryIntent;
  groups: NativeThoughtGroup[];
}

const rates: Record<NativeDeliveryIntent, number> = {
  CONCISE_ANSWER: 0.98,
  NEUTRAL_EXPLANATION: 0.94,
  CLARIFICATION: 0.91,
  QUESTION: 0.93,
  REASSURANCE: 0.95,
  WARNING: 0.89,
  OWNER_BRIEF: 0.92,
  STEP_BY_STEP: 0.9,
};

const normalize = (text: string) => text.trim().replace(/\s+/g, " ");
const bound = (value: number) => Math.min(1, Math.max(0.86, value));

function split(text: string): string[] {
  const source = normalize(text);
  const groups: string[] = [];
  let start = 0;
  for (let index = 0; index < source.length; index += 1) {
    const character = source[index] ?? "";
    const next = source[index + 1] ?? "";
    const hard = ".!?".includes(character) && /\s/.test(next);
    const soft = ";:—".includes(character) && /\s/.test(next);
    const comma = character === "," && /\s/.test(next) &&
      source.slice(start, index).trim().split(/\s+/).length >= 9;
    if (!hard && !soft && !comma) continue;
    groups.push(source.slice(start, index + 1).trim());
    start = index + 1;
  }
  const remainder = source.slice(start).trim();
  if (remainder) groups.push(remainder);
  return groups.filter(Boolean);
}

export function nativeDeliveryIntent(text: string, mode: string, limited = false): NativeDeliveryIntent {
  const lower = text.toLocaleLowerCase();
  if (/\b(first|second|third|next step|then)\b/.test(lower)) return "STEP_BY_STEP";
  if (/\b(?:briefing|today\b|needs your attention\b)/.test(lower)) return "OWNER_BRIEF";
  if (limited && /\b(warning|overdue|conflict|cannot|can't|missing)\b/.test(lower)) return "WARNING";
  if (text.trim().endsWith("?")) return /\b(which|what did you mean|do you mean|which one)\b/.test(lower) ? "CLARIFICATION" : "QUESTION";
  if (/\b(ready|complete|all clear|on track)\b/.test(lower)) return "REASSURANCE";
  return mode === "BRIEF" ? "CONCISE_ANSWER" : "NEUTRAL_EXPLANATION";
}

export function createNativeDeliveryPlan(
  text: string,
  mode = "NORMAL",
  limited = false,
): NativeDeliveryPlan {
  const semanticText = normalize(text);
  const intent = nativeDeliveryIntent(semanticText, mode, limited);
  const parts = split(semanticText);
  return {
    semanticText,
    intent,
    groups: parts.map((part, index) => {
      const material = /(?:\$|%|\b(?:not|missing|unavailable|overdue|conflict|first|next)\b)/i.test(part);
      const final = index === parts.length - 1;
      const ending = part.at(-1) ?? ".";
      return {
        text: part,
        pauseAfterMs: final ? 0 : ending === "?" ? 260 : ending === ":" || ending === ";" || ending === "—" ? 210 : intent === "WARNING" ? 300 : 170,
        rate: bound(rates[intent] + (material ? -0.025 : final ? -0.01 : 0.015)),
        pitch: ending === "?" ? 1.035 : intent === "WARNING" ? 0.985 : final ? 0.995 : 1,
      };
    }),
  };
}

export function nativePlanPreservesSemantics(plan: NativeDeliveryPlan): boolean {
  return normalize(plan.groups.map((group) => group.text).join(" ")) === plan.semanticText;
}

export function speakNativeDeliveryPlan(
  speech: SpeechAdapter,
  plan: NativeDeliveryPlan,
  onDone: () => void,
): { cancel(): void } {
  let cancelled = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const play = (index: number) => {
    if (cancelled) return;
    const group = plan.groups[index];
    if (!group) {
      onDone();
      return;
    }
    speech.speak(group.text, {
      language: "en-US",
      rate: group.rate,
      pitch: group.pitch,
      onDone: () => {
        if (cancelled) return;
        if (index === plan.groups.length - 1) onDone();
        else timer = setTimeout(() => play(index + 1), group.pauseAfterMs);
      },
    });
  };
  play(0);
  return {
    cancel: () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    },
  };
}
