import { useEffect, useRef } from "react";
import { Mic, MicOff, RotateCcw, Square, Volume2 } from "lucide-react";

import { useLiaVoice } from "../../hooks/useLiaVoice";
import type { LiaResponse } from "../../types/lia";
import { Alert, Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../ui";
import { spokenAnswer } from "./voiceSpeech";

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
  const voice = useLiaVoice({
    onTranscript: onDraft,
    onConversationTranscript: onSubmit,
  });

  useEffect(() => {
    if (!result || result.request_id === lastSpokenRequest.current) return;
    lastSpokenRequest.current = result.request_id;
    voice.speak(spokenAnswer(result, result.response_mode));
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
