import { describe, expect, it } from "vitest";

import {
  applyApprovedPronunciationHints,
  applyBrowserDeliveryStyle,
  liaDeliveryStyle,
  normalizeVoiceInventory,
  selectPreferredVoice,
  type PronunciationHint,
} from "./voiceDelivery";

const voice = (
  id: string,
  language: string,
  options: { local?: boolean; default?: boolean } = {},
): SpeechSynthesisVoice => ({
  voiceURI: id,
  name: id,
  lang: language,
  localService: options.local ?? false,
  default: options.default ?? false,
});

describe("LIA provider-neutral delivery controls", () => {
  it("normalizes inventory deterministically and preserves empty inventory", () => {
    expect(normalizeVoiceInventory([])).toEqual([]);
    expect(normalizeVoiceInventory([voice("z", "en-GB"), voice("a", "en-US")]).map((item) => item.id)).toEqual(["a", "z"]);
  });

  it("prefers an explicitly reviewed matching local voice", () => {
    const voices = [
      voice("default-en", "en-US", { local: true, default: true }),
      voice("reviewed-en", "en-US", { local: true }),
      voice("reviewed-fr", "fr-FR", { local: true }),
    ];
    expect(selectPreferredVoice(voices, {
      reviewedVoiceIds: ["reviewed-fr", "reviewed-en"],
      language: "en-US",
      requireLocal: true,
    })?.voiceURI).toBe("reviewed-en");
  });

  it("falls back safely without inventing an unavailable voice", () => {
    expect(selectPreferredVoice([], undefined)).toBeNull();
    expect(selectPreferredVoice([voice("english", "en-GB", { local: true })])?.voiceURI).toBe("english");
    expect(selectPreferredVoice([voice("french", "fr-FR", { local: true })])).toBeNull();
  });

  it("maps the accepted 0.94 browser behavior without treating it as absolute WPM", () => {
    const utterance = { lang: "", rate: 1, pitch: 0, volume: 0, voice: null } as SpeechSynthesisUtterance;
    const selected = voice("local", "en-US", { local: true });
    const style = liaDeliveryStyle("EVIDENCE", "LIMITED");
    applyBrowserDeliveryStyle(utterance, style, selected);
    expect(utterance).toMatchObject({ lang: "en-US", rate: 0.94, pitch: 1, volume: 1, voice: selected });
    expect(style.evaluationTargetWpm).toEqual([150, 170]);
  });

  it("applies only explicitly approved pronunciation hints", () => {
    const hints: PronunciationHint[] = [
      { term: "ACP", spokenForm: "A C P", status: "APPROVED", version: 1 },
      { term: "LIA", spokenForm: "Lee ah", status: "PROPOSED", version: 1 },
    ];
    expect(applyApprovedPronunciationHints("ACP asked LIA.", hints)).toBe("A C P asked LIA.");
  });
});
