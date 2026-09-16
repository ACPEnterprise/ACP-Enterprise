import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { LiaResponse } from "../../types/lia";
import { LiaVoicePanel } from "./LiaVoicePanel";
import { spokenAnswer } from "./voiceSpeech";

class RecognitionMock {
  static latest?: RecognitionMock;
  continuous = false;
  interimResults = false;
  lang = "";
  onstart: (() => void) | null = null;
  onresult: ((event: never) => void) | null = null;
  onspeechend: (() => void) | null = null;
  onend: (() => void) | null = null;
  onerror: ((event: never) => void) | null = null;
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

const speech = {
  cancel: vi.fn(),
  speak: vi.fn((utterance: UtteranceMock) => {
    utterance.onstart?.();
  }),
};

const response = (): LiaResponse => ({
  request_id: "request-1",
  conversation_id: "conversation-1",
  classification: "KNOWN",
  authority: "ACP_AUTHORITATIVE",
  answer: "Two appointments are scheduled tomorrow.",
  evidence: [],
  limitations: [],
  navigation: [{ label: "Open Scheduling", internal_path: "/scheduling" }],
  proposals: [],
  completeness: "COMPLETE_FOR_AUTHORIZED_ADAPTERS",
  freshness: "CURRENT_QUERY",
  provider: "deterministic-acp",
  provider_version: "v1",
  policy_version: "v1",
  evidence_digest: "a".repeat(64),
  authorization_version: 1,
  company_id: "11111111-1111-4111-8111-111111111111",
  branch_ids: [],
  subject_domain: null,
  subject_id: null,
  source_systems: ["scheduling"],
  missing_evidence: [],
  safe_next_action: "Open Scheduling",
  as_of: "2026-09-15T12:00:00Z",
  generated_at: "2026-09-15T12:00:00Z",
});

describe("LIA voice panel", () => {
  beforeEach(() => {
    RecognitionMock.latest = undefined;
    vi.clearAllMocks();
    Object.defineProperty(window, "SpeechRecognition", {
      configurable: true,
      value: RecognitionMock,
    });
    Object.defineProperty(window, "speechSynthesis", {
      configurable: true,
      value: speech,
    });
    Object.defineProperty(window, "SpeechSynthesisUtterance", {
      configurable: true,
      value: UtteranceMock,
    });
    vi.stubGlobal("SpeechSynthesisUtterance", UtteranceMock);
  });

  it("captures a foreground transcript for review without submitting it", () => {
    const onDraft = vi.fn();
    const onSubmit = vi.fn();
    render(
      <LiaVoicePanel
        busy={false}
        onDraft={onDraft}
        onSubmit={onSubmit}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Listen" }));
    expect(screen.getByText("LISTENING")).toBeVisible();
    act(() => {
      RecognitionMock.latest?.onresult?.({
        resultIndex: 0,
        results: [{ isFinal: true, 0: { transcript: "What is scheduled tomorrow?" } }],
      } as never);
      RecognitionMock.latest?.onend?.();
    });
    expect(onDraft).toHaveBeenCalledWith("What is scheduled tomorrow?");
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Recognized speech")).toHaveTextContent(
      "What is scheduled tomorrow?",
    );
  });

  it("submits automatically only after explicit conversation-mode activation", () => {
    const onSubmit = vi.fn();
    render(
      <LiaVoicePanel busy={false} onDraft={vi.fn()} onSubmit={onSubmit} />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Start conversation mode" }),
    );
    act(() => {
      RecognitionMock.latest?.onresult?.({
        resultIndex: 0,
        results: [{ isFinal: true, 0: { transcript: "Show me Lianne" } }],
      } as never);
      RecognitionMock.latest?.onend?.();
    });
    expect(onSubmit).toHaveBeenCalledWith("Show me Lianne");
    fireEvent.click(screen.getByRole("button", { name: "End conversation" }));
    expect(screen.getByText("IDLE")).toBeVisible();
    expect(speech.cancel).toHaveBeenCalled();
  });

  it("speaks a new authorized answer and allows immediate interruption", () => {
    render(
      <LiaVoicePanel
        busy={false}
        result={response()}
        onDraft={vi.fn()}
        onSubmit={vi.fn()}
      />,
    );
    expect(speech.speak).toHaveBeenCalledOnce();
    expect(screen.getByText("SPEAKING")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Interrupt LIA" }));
    expect(speech.cancel).toHaveBeenCalled();
    expect(screen.getByText("LISTENING")).toBeVisible();
  });

  it("ends active capture and never exposes a mutation control", () => {
    render(
      <LiaVoicePanel busy={false} onDraft={vi.fn()} onSubmit={vi.fn()} />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Start conversation mode" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "End conversation" }));
    expect(RecognitionMock.latest?.abort).toHaveBeenCalled();
    expect(screen.queryByText(/approve|reschedule|dispatch now/i)).toBeNull();
  });

  it("cancel ends conversation capture and spoken output", () => {
    render(
      <LiaVoicePanel busy={false} onDraft={vi.fn()} onSubmit={vi.fn()} />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Start conversation mode" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(RecognitionMock.latest?.abort).toHaveBeenCalled();
    expect(speech.cancel).toHaveBeenCalled();
    expect(screen.getByText("IDLE")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Start conversation mode" }),
    ).toBeVisible();
  });

  it("keeps spoken output concise while full evidence remains on screen", () => {
    const result = response();
    result.answer =
      "Direct conclusion. Important implication. Detailed evidence one. Detailed evidence two. Detailed evidence three.";
    expect(spokenAnswer(result)).toBe(
      "Direct conclusion. Important implication. Next: Open Scheduling.",
    );
  });
});
