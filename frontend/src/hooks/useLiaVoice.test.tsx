import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useLiaVoice } from "./useLiaVoice";

class RecognitionMock {
  static latest?: RecognitionMock;
  continuous = false;
  interimResults = false;
  lang = "";
  onstart: (() => void) | null = null;
  onresult = null;
  onspeechend = null;
  onend: (() => void) | null = null;
  onerror = null;
  start = vi.fn(() => this.onstart?.());
  stop = vi.fn(() => this.onend?.());
  abort = vi.fn();

  constructor() {
    RecognitionMock.latest = this;
  }
}

class UtteranceMock {
  text: string;
  rate = 1;
  onstart: (() => void) | null = null;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(text: string) {
    this.text = text;
  }
}

describe("useLiaVoice", () => {
  let spoken: UtteranceMock | undefined;
  let utterances: UtteranceMock[];

  beforeEach(() => {
    vi.useFakeTimers();
    RecognitionMock.latest = undefined;
    spoken = undefined;
    utterances = [];
    Object.defineProperty(window, "SpeechRecognition", {
      configurable: true,
      value: RecognitionMock,
    });
    Object.defineProperty(window, "speechSynthesis", {
      configurable: true,
      value: {
        cancel: vi.fn(),
        speak: vi.fn((utterance: UtteranceMock) => {
          spoken = utterance;
          utterances.push(utterance);
          utterance.onstart?.();
        }),
      },
    });
    vi.stubGlobal("SpeechSynthesisUtterance", UtteranceMock);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("aborts foreground capture when conversation inactivity expires", () => {
    const { result } = renderHook(() =>
      useLiaVoice({
        onTranscript: vi.fn(),
        onConversationTranscript: vi.fn(),
        inactivityMs: 1_000,
      }),
    );
    act(() => result.current.beginConversation());
    act(() => result.current.speak("Authorized answer."));
    act(() => spoken?.onend?.());
    const activeRecognition = RecognitionMock.latest;

    act(() => vi.advanceTimersByTime(1_000));

    expect(activeRecognition?.abort).toHaveBeenCalled();
    expect(result.current.conversationMode).toBe(false);
    expect(result.current.state).toBe("IDLE");
  });

  it("speaks thought groups sequentially with bounded variable delivery", () => {
    const { result } = renderHook(() =>
      useLiaVoice({ onTranscript: vi.fn(), onConversationTranscript: vi.fn() }),
    );
    act(() => result.current.speak("Six appointments are scheduled. Two still need attention."));
    expect(utterances).toHaveLength(1);
    expect(utterances[0].text).toBe("Six appointments are scheduled.");
    act(() => utterances[0].onend?.());
    act(() => vi.runOnlyPendingTimers());
    expect(utterances).toHaveLength(2);
    expect(utterances[1].text).toBe("Two still need attention.");
    expect(utterances[0].rate).not.toBe(0.94);
    act(() => utterances[1].onend?.());
    expect(result.current.state).toBe("IDLE");
  });

  it("cancels the remaining delivery plan when interrupted", () => {
    const { result } = renderHook(() =>
      useLiaVoice({ onTranscript: vi.fn(), onConversationTranscript: vi.fn() }),
    );
    act(() => result.current.speak("First answer. Second answer."));
    act(() => result.current.stopSpeaking());
    act(() => utterances[0].onend?.());
    act(() => vi.runOnlyPendingTimers());
    expect(utterances).toHaveLength(1);
    expect(result.current.state).toBe("INTERRUPTED");
  });
});
