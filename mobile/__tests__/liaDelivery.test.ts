import {
  createNativeDeliveryPlan,
  nativePlanPreservesSemantics,
  speakNativeDeliveryPlan,
} from "../src/lia/delivery";

describe("native LIA delivery", () => {
  jest.useFakeTimers();

  it("preserves exact semantic text while producing thought groups", () => {
    const text = "Revenue is $12,450.00, but material cost is missing. Contribution is unavailable.";
    const plan = createNativeDeliveryPlan(text, "NORMAL", true);
    expect(plan.semanticText).toBe(text);
    expect(nativePlanPreservesSemantics(plan)).toBe(true);
    expect(plan.groups.length).toBeGreaterThan(1);
    expect(plan.groups.map((group) => group.text).join(" ")).toContain("$12,450.00");
  });

  it("plays groups sequentially and remains cancellable", () => {
    const speech = { speak: jest.fn(), stop: jest.fn() };
    const done = jest.fn();
    const playback = speakNativeDeliveryPlan(
      speech,
      createNativeDeliveryPlan("First answer. Second answer."),
      done,
    );
    expect(speech.speak).toHaveBeenCalledTimes(1);
    const firstOptions = speech.speak.mock.calls[0]?.[1];
    firstOptions?.onDone?.();
    jest.runOnlyPendingTimers();
    expect(speech.speak).toHaveBeenCalledTimes(2);
    playback.cancel();
    speech.speak.mock.calls[1]?.[1]?.onDone?.();
    expect(done).not.toHaveBeenCalled();
  });
});
