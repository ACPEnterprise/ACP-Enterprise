import { describe, expect, it } from "vitest";

import { evaluateSpokenText, liaVoiceEvaluationCorpus } from "./voiceEvaluation";

describe("LIA spoken evaluation corpus", () => {
  it("covers the required business and safety families", () => {
    expect(liaVoiceEvaluationCorpus).toHaveLength(12);
    expect(new Set(liaVoiceEvaluationCorpus.map((item) => item.domain)).size).toBeGreaterThanOrEqual(10);
  });

  it.each(liaVoiceEvaluationCorpus)("preserves material values for $id", (item) => {
    const measurement = evaluateSpokenText(item, item.expectedSpokenContent);
    expect(measurement.materialValuesPreserved).toBe(true);
    expect(measurement.prohibitedDistortionFound).toBe(false);
    expect(measurement.measuredWpm).toBeNull();
    expect(measurement.referenceMeasurementPending).toBe(true);
  });

  it("calculates measured WPM only when actual duration metadata exists", () => {
    const item = liaVoiceEvaluationCorpus[0];
    const withoutAudio = evaluateSpokenText(item, item.expectedSpokenContent);
    const withAudio = evaluateSpokenText(item, item.expectedSpokenContent, 6_000);
    expect(withoutAudio.durationMs).toBeNull();
    expect(withoutAudio.measuredWpm).toBeNull();
    expect(withAudio.durationMs).toBe(6_000);
    expect(withAudio.measuredWpm).toBeGreaterThan(0);
  });

  it("detects material-value loss and prohibited distortion", () => {
    const item = liaVoiceEvaluationCorpus.find((candidate) => candidate.id === "dollar-amount")!;
    const measurement = evaluateSpokenText(item, "Invoice INV-204 is paid with a balance of $1,250.00.");
    expect(measurement.materialValuesPreserved).toBe(false);
    expect(measurement.prohibitedDistortionFound).toBe(true);
  });
});
