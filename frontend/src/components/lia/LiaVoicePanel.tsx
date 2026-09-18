import { useEffect, useRef, useState } from "react";
import { Mic, MicOff, RotateCcw, Square, Volume2 } from "lucide-react";

import { useLiaVoice } from "../../hooks/useLiaVoice";
import type { LiaResponse } from "../../types/lia";
import { Alert, Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../ui";
import { spokenAnswer } from "./voiceSpeech";
import { liaDeliveryStyle, type DeliveryCategory } from "./voiceDelivery";
import { liaVoiceEvaluationCorpus } from "./voiceEvaluation";

export function LiaVoicePanel({
  result,
  busy,
  onDraft,
  onSubmit,
}: {
  result?: LiaResponse;
  busy: boolean;
  onDraft: (transcript: string) => void;
  onSubmit: (transcript: string) => void;
}) {
  const lastSpokenRequest = useRef<string | undefined>(undefined);
  const [previewItemId, setPreviewItemId] = useState(
    liaVoiceEvaluationCorpus[0]?.id ?? "",
  );
  const voice = useLiaVoice({
    onTranscript: onDraft,
    onConversationTranscript: onSubmit,
  });
  const previewItem =
    liaVoiceEvaluationCorpus.find((item) => item.id === previewItemId) ??
    liaVoiceEvaluationCorpus[0];

  useEffect(() => {
    if (!result || result.request_id === lastSpokenRequest.current) return;
    lastSpokenRequest.current = result.request_id;
    const deliveryCategory: DeliveryCategory = result.classification === "KNOWN"
      ? "KNOWN"
      : result.classification === "UNAVAILABLE"
        ? "BLOCKER"
        : result.classification === "INCOMPLETE"
          ? "LIMITED"
          : "UNCERTAIN";
    voice.speak(
      spokenAnswer(result, result.response_mode),
      liaDeliveryStyle(result.response_mode, deliveryCategory),
    );
  }, [result, voice]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mic aria-hidden className="size-5" />
          Voice conversation
        </CardTitle>
        <CardDescription>
          Foreground-only voice uses the same authorized LIA request and evidence context as text.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!voice.supported ? (
          <Alert variant="warning" title="Voice unavailable in this browser">
            Text LIA remains available. ACP has not sent audio to an external AI provider.
          </Alert>
        ) : (
          <>
            <div
              aria-live="polite"
              className="rounded-lg border border-stroke bg-surface-muted p-3"
            >
              <p className="font-semibold">{voice.state.replaceAll("_", " ")}</p>
              <p className="mt-1 text-sm text-content-muted">
                {voice.conversationMode
                  ? "Conversation mode is active. The microphone is used only while this page is visible and listening is shown."
                  : "Tap Listen once, then review or edit the recognized text before sending."}
              </p>
              {voice.interimTranscript ? (
                <p className="mt-2" aria-label="Recognized speech">
                  {voice.interimTranscript}
                </p>
              ) : null}
            </div>
            {voice.error ? (
              <Alert variant="danger" title="Voice request unavailable">
                {voice.error}
              </Alert>
            ) : null}
            <div className="flex flex-wrap gap-2">
              {voice.state === "LISTENING" ? (
                <Button
                  variant="secondary"
                  leadingIcon={<Square className="size-4" />}
                  onClick={voice.stopListening}
                >
                  Stop listening
                </Button>
              ) : (
                <Button
                  disabled={busy}
                  leadingIcon={<Mic className="size-4" />}
                  onClick={voice.startListening}
                >
                  Listen
                </Button>
              )}
              {voice.state === "SPEAKING" ? (
                <Button variant="secondary" onClick={voice.interruptAndListen}>
                  Interrupt LIA
                </Button>
              ) : null}
              {voice.conversationMode ? (
                <Button
                  variant="destructive"
                  leadingIcon={<MicOff className="size-4" />}
                  onClick={voice.endConversation}
                >
                  End conversation
                </Button>
              ) : (
                <Button
                  variant="outline"
                  disabled={busy}
                  leadingIcon={<Volume2 className="size-4" />}
                  onClick={voice.beginConversation}
                >
                  Start conversation mode
                </Button>
              )}
              <Button variant="ghost" onClick={voice.cancel}>
                Cancel
              </Button>
              <Button
                variant="ghost"
                disabled={!voice.hasReplay}
                leadingIcon={<RotateCcw className="size-4" />}
                onClick={voice.replay}
              >
                Replay answer
              </Button>
            </div>
            <details className="rounded-lg border border-stroke p-3">
              <summary className="cursor-pointer font-medium">
                Preview a distinct device voice
              </summary>
              <div className="mt-3 space-y-3">
                <label className="block text-sm font-medium" htmlFor="lia-device-voice">
                  English voice available on this device
                </label>
                <select
                  className="min-h-11 w-full rounded-md border border-stroke bg-surface px-3"
                  id="lia-device-voice"
                  value={voice.selectedVoiceId}
                  onChange={(event) => voice.setSelectedVoiceId(event.target.value)}
                >
                  <option value="">Automatic local English fallback</option>
                  {voice.availableVoices.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name} · {item.language}
                      {item.isLocal ? " · On device" : ""}
                    </option>
                  ))}
                </select>
                <label className="block text-sm font-medium" htmlFor="lia-preview-response">
                  Evaluation response
                </label>
                <select
                  className="min-h-11 w-full rounded-md border border-stroke bg-surface px-3"
                  id="lia-preview-response"
                  value={previewItemId}
                  onChange={(event) => setPreviewItemId(event.target.value)}
                >
                  {liaVoiceEvaluationCorpus.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.domain} · {item.id.replaceAll("-", " ")}
                    </option>
                  ))}
                </select>
                <Button
                  variant="secondary"
                  leadingIcon={<Volume2 className="size-4" />}
                  onClick={() => {
                    if (!previewItem) return;
                    voice.speak(
                      previewItem.expectedSpokenContent,
                      liaDeliveryStyle(previewItem.responseMode, "LIMITED"),
                    );
                  }}
                >
                  Preview LIA style
                </Button>
                <p className="text-xs text-content-muted">
                  This preference stays on this browser. It does not admit a production
                  voice or compare anyone's vocal identity.
                </p>
              </div>
            </details>
          </>
        )}
        <p className="text-xs text-content-muted">
          No background recording. ACP does not persist raw audio. Your browser or
          device speech service may process audio under its own privacy terms; do
          not speak passwords, banking details, tax data, or other secrets. End
          Conversation stops capture and speech immediately.
        </p>
      </CardContent>
    </Card>
  );
}
