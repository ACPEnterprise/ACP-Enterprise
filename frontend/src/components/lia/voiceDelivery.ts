import type { SpokenResponseMode } from "./voiceSpeech";

export type PauseIntent = "NATURAL" | "SHORT" | "DELIBERATE";
export type QuestionContourIntent = "GENTLE_RISE" | "NEUTRAL";
export type DeliveryCategory = "KNOWN" | "LIMITED" | "UNCERTAIN" | "BLOCKER";
export type LiaDeliveryIntent =
  | "CONCISE_ANSWER"
  | "NEUTRAL_EXPLANATION"
  | "CLARIFICATION"
  | "QUESTION"
  | "REASSURANCE"
  | "WARNING"
  | "OWNER_BRIEF"
  | "STEP_BY_STEP";

export interface LiaThoughtGroup {
  readonly text: string;
  readonly pauseAfterMs: number;
  readonly relativeRate: number;
  readonly pitch: number;
  readonly emphasis: "NEUTRAL" | "SELECTIVE";
}

export interface LiaDeliveryPlan {
  readonly version: "lia-delivery-plan.v1";
  readonly intent: LiaDeliveryIntent;
  readonly semanticText: string;
  readonly groups: readonly LiaThoughtGroup[];
}

export interface LiaDeliveryStyle {
  readonly version: "lia-delivery-style.v1";
  readonly language: string;
  readonly nominalPace: "MODERATE";
  readonly evaluationTargetWpm: readonly [150, 170];
  readonly sentencePauseIntent: PauseIntent;
  readonly limitationPauseIntent: PauseIntent;
  readonly questionContourIntent: QuestionContourIntent;
  readonly emphasisIntent: "MEANING_BEARING_TERMS_ONLY";
  readonly expressiveness: "RESTRAINED";
  readonly deliveryCategory: DeliveryCategory;
  readonly responseMode: SpokenResponseMode;
  readonly platformMapping: {
    readonly relativeRate: 0.94;
    readonly pitch: 1;
    readonly volume: 1;
  };
}

export const liaDeliveryStyle = (
  responseMode: SpokenResponseMode,
  deliveryCategory: DeliveryCategory = "KNOWN",
): LiaDeliveryStyle => ({
  version: "lia-delivery-style.v1",
  language: "en-US",
  nominalPace: "MODERATE",
  evaluationTargetWpm: [150, 170],
  sentencePauseIntent: "NATURAL",
  limitationPauseIntent: deliveryCategory === "KNOWN" ? "SHORT" : "DELIBERATE",
  questionContourIntent: "GENTLE_RISE",
  emphasisIntent: "MEANING_BEARING_TERMS_ONLY",
  expressiveness: "RESTRAINED",
  deliveryCategory,
  responseMode,
  platformMapping: { relativeRate: 0.94, pitch: 1, volume: 1 },
});

export interface LiaVoiceMetadata {
  readonly id: string;
  readonly name: string;
  readonly language: string;
  readonly isDefault: boolean;
  readonly isLocal: boolean;
}

export interface LiaVoicePreference {
  readonly reviewedVoiceIds: readonly string[];
  readonly language: string;
  readonly requireLocal: boolean;
}

export const defaultVoicePreference: LiaVoicePreference = {
  reviewedVoiceIds: [],
  language: "en-US",
  requireLocal: true,
};

export function normalizeVoiceInventory(
  voices: readonly SpeechSynthesisVoice[],
): LiaVoiceMetadata[] {
  return voices
    .map((voice) => ({
      id: voice.voiceURI || `${voice.name}:${voice.lang}`,
      name: voice.name,
      language: voice.lang,
      isDefault: voice.default,
      isLocal: voice.localService,
    }))
    .sort((left, right) => left.id.localeCompare(right.id));
}

const languageMatches = (actual: string, desired: string) => {
  const normalizedActual = actual.toLocaleLowerCase();
  const normalizedDesired = desired.toLocaleLowerCase();
  return normalizedActual === normalizedDesired ||
    normalizedActual.split("-")[0] === normalizedDesired.split("-")[0];
};

export function selectPreferredVoice(
  voices: readonly SpeechSynthesisVoice[],
  preference: LiaVoicePreference = defaultVoicePreference,
): SpeechSynthesisVoice | null {
  const languageVoices = voices.filter((voice) =>
    languageMatches(voice.lang, preference.language),
  );
  const reviewed = preference.reviewedVoiceIds
    .map((id) => languageVoices.find((voice) => (voice.voiceURI || `${voice.name}:${voice.lang}`) === id))
    .find((voice): voice is SpeechSynthesisVoice => Boolean(voice));
  if (reviewed && (!preference.requireLocal || reviewed.localService)) return reviewed;
  return languageVoices.find((voice) => voice.default && voice.localService) ??
    languageVoices.find((voice) => voice.localService) ??
    languageVoices.find((voice) => voice.default) ??
    languageVoices[0] ??
    null;
}

export interface PronunciationHint {
  readonly term: string;
  readonly spokenForm: string;
  readonly status: "PROPOSED" | "APPROVED";
  readonly version: number;
}

export const proposedPronunciationCatalog: readonly PronunciationHint[] = [
  { term: "ACP", spokenForm: "A C P", status: "PROPOSED", version: 1 },
  { term: "LIA", spokenForm: "L I A", status: "PROPOSED", version: 1 },
  { term: "HVAC", spokenForm: "H V A C", status: "PROPOSED", version: 1 },
  { term: "QBO", spokenForm: "Q B O", status: "PROPOSED", version: 1 },
  { term: "SKU", spokenForm: "S K U", status: "PROPOSED", version: 1 },
];

export function applyApprovedPronunciationHints(
  text: string,
  hints: readonly PronunciationHint[],
): string {
  return hints
    .filter((hint) => hint.status === "APPROVED")
    .reduce(
      (value, hint) => value.replace(new RegExp(`\\b${hint.term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g"), hint.spokenForm),
      text,
    );
}

export interface LiaSpeechRenderRequest {
  readonly text: string;
  readonly style: LiaDeliveryStyle;
  readonly pronunciationHints: readonly PronunciationHint[];
  readonly responseId: string;
}

export interface LiaSpeechRenderResult {
  readonly state: "READY" | "PLAYING" | "COMPLETED" | "FAILED" | "UNAVAILABLE";
  readonly adapterId: string;
  readonly voiceId: string | null;
  readonly durationMs: number | null;
  readonly renderDigest: string | null;
  readonly errorClass: string | null;
}

export interface LiaSpeechRenderer {
  readonly adapterId: string;
  render(request: LiaSpeechRenderRequest): Promise<LiaSpeechRenderResult>;
}

export function applyBrowserDeliveryStyle(
  utterance: SpeechSynthesisUtterance,
  style: LiaDeliveryStyle,
  voice: SpeechSynthesisVoice | null,
): void {
  utterance.lang = style.language;
  utterance.rate = style.platformMapping.relativeRate;
  utterance.pitch = style.platformMapping.pitch;
  utterance.volume = style.platformMapping.volume;
  utterance.voice = voice;
}

const intentRate: Record<LiaDeliveryIntent, number> = {
  CONCISE_ANSWER: 0.98,
  NEUTRAL_EXPLANATION: 0.94,
  CLARIFICATION: 0.91,
  QUESTION: 0.93,
  REASSURANCE: 0.95,
  WARNING: 0.89,
  OWNER_BRIEF: 0.92,
  STEP_BY_STEP: 0.9,
};

const bounded = (value: number, minimum: number, maximum: number) =>
  Math.min(maximum, Math.max(minimum, value));

const normalized = (value: string) => value.trim().replace(/\s+/g, " ");

function boundaryPause(character: string, intent: LiaDeliveryIntent): number {
  if (character === "?" || intent === "CLARIFICATION" || intent === "QUESTION") return 260;
  if (character === "!" || intent === "WARNING") return 300;
  if (character === ":" || character === ";" || character === "—") return 210;
  return intent === "OWNER_BRIEF" || intent === "STEP_BY_STEP" ? 240 : 170;
}

function splitThoughtGroups(text: string): string[] {
  const source = normalized(text);
  if (!source) return [];
  const groups: string[] = [];
  let start = 0;
  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    const next = source[index + 1] ?? "";
    const previous = source[index - 1] ?? "";
    const hard = ".!?".includes(character) && /\s/.test(next) &&
      !(character === "." && /\d/.test(previous) && /\d/.test(next));
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

export function inferDeliveryIntent(
  text: string,
  style: LiaDeliveryStyle,
): LiaDeliveryIntent {
  const lower = text.toLocaleLowerCase();
  if (/\b(first|second|third|next step|then)\b/.test(lower)) return "STEP_BY_STEP";
  if (/\b(?:briefing|today\b|needs your attention\b)/.test(lower)) return "OWNER_BRIEF";
  if (style.deliveryCategory === "BLOCKER" || /\b(warning|overdue|conflict|cannot|can't)\b/.test(lower)) return "WARNING";
  if (text.trim().endsWith("?")) {
    return /\b(which|what did you mean|do you mean|which one)\b/.test(lower)
      ? "CLARIFICATION"
      : "QUESTION";
  }
  if (/\b(ready|complete|all clear|on track)\b/.test(lower)) return "REASSURANCE";
  if (style.responseMode === "BRIEF") return "CONCISE_ANSWER";
  return "NEUTRAL_EXPLANATION";
}

export function createDeliveryPlan(
  text: string,
  style: LiaDeliveryStyle,
  requestedIntent?: LiaDeliveryIntent,
): LiaDeliveryPlan {
  const semanticText = normalized(text);
  const intent = requestedIntent ?? inferDeliveryIntent(semanticText, style);
  const pieces = splitThoughtGroups(semanticText);
  const groups = pieces.map((group, index): LiaThoughtGroup => {
    const finalCharacter = group.at(-1) ?? ".";
    const material = /(?:\$|%|\b(?:not|missing|unavailable|overdue|conflict|first|next)\b)/i.test(group);
    const finalGroup = index === pieces.length - 1;
    const question = finalCharacter === "?";
    const rateAdjustment = material ? -0.025 : finalGroup ? -0.01 : 0.015;
    return {
      text: group,
      pauseAfterMs: finalGroup ? 0 : boundaryPause(finalCharacter, intent),
      relativeRate: bounded(intentRate[intent] + rateAdjustment, 0.86, 1),
      pitch: question ? 1.035 : intent === "WARNING" ? 0.985 : finalGroup ? 0.995 : 1,
      emphasis: material ? "SELECTIVE" : "NEUTRAL",
    };
  });
  return { version: "lia-delivery-plan.v1", intent, semanticText, groups };
}

export function deliveryPlanPreservesSemantics(plan: LiaDeliveryPlan): boolean {
  return normalized(plan.groups.map((group) => group.text).join(" ")) === plan.semanticText;
}

export function applyBrowserThoughtGroup(
  utterance: SpeechSynthesisUtterance,
  style: LiaDeliveryStyle,
  group: LiaThoughtGroup,
  voice: SpeechSynthesisVoice | null,
): void {
  applyBrowserDeliveryStyle(utterance, style, voice);
  utterance.rate = group.relativeRate;
  utterance.pitch = group.pitch;
}
