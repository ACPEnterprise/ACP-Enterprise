import { useCallback, useEffect, useRef, useState } from "react";

import {
  applyBrowserThoughtGroup,
  createDeliveryPlan,
  liaDeliveryStyle,
  normalizeVoiceInventory,
  selectPreferredVoice,
  type LiaDeliveryStyle,
} from "../components/lia/voiceDelivery";

export type LiaVoiceState =
  | "IDLE"
  | "LISTENING"
  | "TRANSCRIBING"
  | "THINKING"
  | "SPEAKING"
  | "INTERRUPTED"
  | "ERROR";

interface SpeechRecognitionAlternativeLike {
  transcript: string;
}

interface SpeechRecognitionResultLike {
  isFinal: boolean;
  0: SpeechRecognitionAlternativeLike;
}

interface SpeechRecognitionEventLike extends Event {
  resultIndex: number;
  results: ArrayLike<SpeechRecognitionResultLike>;
}

interface SpeechRecognitionErrorEventLike extends Event {
  error: string;
}

interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onstart: (() => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onspeechend: (() => void) | null;
  onend: (() => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

const DEFAULT_SILENCE_MS = 900;
const DEFAULT_INACTIVITY_MS = 90_000;
const VOICE_PREFERENCE_KEY = "twelve-hats.lia.device-voice.v1";

const recognitionConstructor = () =>
  window.SpeechRecognition ?? window.webkitSpeechRecognition;

const voiceError = (error: string) => {
  if (error === "not-allowed" || error === "service-not-allowed") {
    return "Microphone or speech recognition permission was denied. Enable it in browser settings to use voice.";
  }
  if (error === "network") {
    return "Speech recognition could not reach its service. Your business question was not submitted.";
  }
  if (error === "no-speech") {
    return "No speech was recognized. Try again or type the question.";
  }
  return "Speech recognition failed safely. No business answer was inferred.";
};

export function useLiaVoice({
  onTranscript,
  onConversationTranscript,
  silenceMs = DEFAULT_SILENCE_MS,
  inactivityMs = DEFAULT_INACTIVITY_MS,
}: {
  onTranscript: (text: string) => void;
  onConversationTranscript: (text: string) => void;
  silenceMs?: number;
  inactivityMs?: number;
}) {
  const recognition = useRef<SpeechRecognitionLike | undefined>(undefined);
  const stopTimer = useRef<number | undefined>(undefined);
  const inactivityTimer = useRef<number | undefined>(undefined);
  const finalTranscript = useRef("");
  const conversationModeRef = useRef(false);
  const [state, setState] = useState<LiaVoiceState>("IDLE");
  const [conversationMode, setConversationMode] = useState(false);
  const [interimTranscript, setInterimTranscript] = useState("");
  const [error, setError] = useState<string>();
  const [lastSpokenAnswer, setLastSpokenAnswer] = useState("");
  const [voiceInventory, setVoiceInventory] = useState<SpeechSynthesisVoice[]>([]);
  const [selectedVoiceId, setSelectedVoiceIdState] = useState(() =>
    typeof window === "undefined"
      ? ""
      : (window.localStorage.getItem(VOICE_PREFERENCE_KEY) ?? ""),
  );
  const lastDeliveryStyle = useRef<LiaDeliveryStyle>(liaDeliveryStyle("NORMAL"));
  const speechRun = useRef(0);

  const supported =
    typeof window !== "undefined" &&
    Boolean(recognitionConstructor()) &&
    "speechSynthesis" in window;

  useEffect(() => {
    conversationModeRef.current = conversationMode;
  }, [conversationMode]);

  useEffect(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const synthesis = window.speechSynthesis;
    const refreshVoices = () => setVoiceInventory(synthesis.getVoices?.() ?? []);
    refreshVoices();
    synthesis.addEventListener?.("voiceschanged", refreshVoices);
    return () => synthesis.removeEventListener?.("voiceschanged", refreshVoices);
  }, []);

  const clearTimers = useCallback(() => {
    if (stopTimer.current) window.clearTimeout(stopTimer.current);
    if (inactivityTimer.current) window.clearTimeout(inactivityTimer.current);
  }, []);

  const stopSpeaking = useCallback(() => {
    speechRun.current += 1;
    if (typeof window !== "undefined") window.speechSynthesis?.cancel();
    setState("INTERRUPTED");
  }, []);

  const stopListening = useCallback(() => {
    if (stopTimer.current) window.clearTimeout(stopTimer.current);
    recognition.current?.stop();
    setState("TRANSCRIBING");
  }, []);

  const startListening = useCallback(() => {
    const Constructor = recognitionConstructor();
    if (!Constructor) {
      setError("Voice recognition is unavailable in this browser. You can continue with text LIA.");
      setState("ERROR");
      return;
    }
    clearTimers();
    speechRun.current += 1;
    window.speechSynthesis?.cancel();
    finalTranscript.current = "";
    setInterimTranscript("");
    setError(undefined);

    const instance = new Constructor();
    instance.continuous = false;
    instance.interimResults = true;
    instance.lang = "en-US";
    instance.onstart = () => setState("LISTENING");
    instance.onresult = (event) => {
      let interim = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        if (result.isFinal) finalTranscript.current += result[0].transcript;
        else interim += result[0].transcript;
      }
      setInterimTranscript(`${finalTranscript.current} ${interim}`.trim());
    };
    instance.onspeechend = () => {
      stopTimer.current = window.setTimeout(() => instance.stop(), silenceMs);
    };
    instance.onerror = (event) => {
      setError(voiceError(event.error));
      setState("ERROR");
    };
    instance.onend = () => {
      recognition.current = undefined;
      const transcript = finalTranscript.current.trim();
      setInterimTranscript(transcript);
      if (!transcript) {
        setState((current) => (current === "ERROR" ? current : "IDLE"));
        return;
      }
      setState("TRANSCRIBING");
      onTranscript(transcript);
      if (conversationModeRef.current) {
        setState("THINKING");
        onConversationTranscript(transcript);
      }
    };
    recognition.current = instance;
    try {
      instance.start();
    } catch {
      setError("The microphone is already in use. Stop the current capture before retrying.");
      setState("ERROR");
    }
  }, [clearTimers, onConversationTranscript, onTranscript, silenceMs]);

  const speak = useCallback(
    (answer: string, style: LiaDeliveryStyle = liaDeliveryStyle("NORMAL")) => {
      if (!supported || !answer.trim()) return;
      const run = speechRun.current + 1;
      speechRun.current = run;
      window.speechSynthesis.cancel();
      const voices = voiceInventory.length
        ? voiceInventory
        : (window.speechSynthesis.getVoices?.() ?? []);
      const selectedVoice = selectPreferredVoice(voices, {
        reviewedVoiceIds: selectedVoiceId ? [selectedVoiceId] : [],
        language: style.language,
        requireLocal: true,
      });
      const plan = createDeliveryPlan(answer, style);
      const finish = () => {
        if (speechRun.current !== run) return;
        setState("IDLE");
        if (conversationModeRef.current) {
          startListening();
          inactivityTimer.current = window.setTimeout(() => {
            conversationModeRef.current = false;
            setConversationMode(false);
            recognition.current?.abort();
            recognition.current = undefined;
            setInterimTranscript("");
            setState("IDLE");
          }, inactivityMs);
        }
      };
      const speakGroup = (index: number) => {
        if (speechRun.current !== run) return;
        const group = plan.groups[index];
        if (!group) {
          finish();
          return;
        }
        const utterance = new SpeechSynthesisUtterance(group.text);
        applyBrowserThoughtGroup(utterance, style, group, selectedVoice);
        utterance.onstart = () => setState("SPEAKING");
        utterance.onerror = () => {
          if (speechRun.current !== run) return;
          speechRun.current += 1;
          setError("The spoken response could not be played. The full answer remains visible.");
          setState("ERROR");
        };
        utterance.onend = () => {
          if (speechRun.current !== run) return;
          if (index === plan.groups.length - 1) {
            finish();
            return;
          }
          window.setTimeout(() => speakGroup(index + 1), group.pauseAfterMs);
        };
        window.speechSynthesis.speak(utterance);
      };
      setLastSpokenAnswer(answer);
      lastDeliveryStyle.current = style;
      speakGroup(0);
    },
    [inactivityMs, selectedVoiceId, startListening, supported, voiceInventory],
  );

  const setSelectedVoiceId = useCallback((voiceId: string) => {
    setSelectedVoiceIdState(voiceId);
    if (voiceId) window.localStorage.setItem(VOICE_PREFERENCE_KEY, voiceId);
    else window.localStorage.removeItem(VOICE_PREFERENCE_KEY);
  }, []);

  const beginConversation = useCallback(() => {
    setConversationMode(true);
    conversationModeRef.current = true;
    startListening();
  }, [startListening]);

  const endConversation = useCallback(() => {
    speechRun.current += 1;
    conversationModeRef.current = false;
    setConversationMode(false);
    clearTimers();
    recognition.current?.abort();
    recognition.current = undefined;
    window.speechSynthesis?.cancel();
    setInterimTranscript("");
    setState("IDLE");
  }, [clearTimers]);

  const cancel = useCallback(() => {
    speechRun.current += 1;
    conversationModeRef.current = false;
    setConversationMode(false);
    clearTimers();
    recognition.current?.abort();
    recognition.current = undefined;
    window.speechSynthesis?.cancel();
    setInterimTranscript("");
    setError(undefined);
    setState("IDLE");
  }, [clearTimers]);

  const replay = useCallback(() => {
    if (lastSpokenAnswer) speak(lastSpokenAnswer, lastDeliveryStyle.current);
  }, [lastSpokenAnswer, speak]);

  const interruptAndListen = useCallback(() => {
    stopSpeaking();
    startListening();
  }, [startListening, stopSpeaking]);

  useEffect(() => endConversation, [endConversation]);

  return {
    supported,
    state,
    error,
    conversationMode,
    interimTranscript,
    hasReplay: Boolean(lastSpokenAnswer),
    availableVoices: normalizeVoiceInventory(voiceInventory).filter(
      (item) => item.isLocal && item.language.toLocaleLowerCase().startsWith("en"),
    ),
    selectedVoiceId,
    setSelectedVoiceId,
    startListening,
    stopListening,
    stopSpeaking,
    interruptAndListen,
    beginConversation,
    endConversation,
    cancel,
    speak,
    replay,
  };
}
