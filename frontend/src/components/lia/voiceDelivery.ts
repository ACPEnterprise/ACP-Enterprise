import type { SpokenResponseMode } from "./voiceSpeech";

export type PauseIntent = "NATURAL" | "SHORT" | "DELIBERATE";
export type QuestionContourIntent = "GENTLE_RISE" | "NEUTRAL";
export type DeliveryCategory = "KNOWN" | "LIMITED" | "UNCERTAIN" | "BLOCKER";

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
