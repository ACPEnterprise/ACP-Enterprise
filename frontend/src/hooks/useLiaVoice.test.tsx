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

  beforeEach(() => {
    vi.useFakeTimers();
    RecognitionMock.latest = undefined;
    spoken = undefined;
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
});
