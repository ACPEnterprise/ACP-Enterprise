import * as Speech from "expo-speech";
import type { LiaResponse } from "../api/lia";
import { z } from "zod";

export type SpeechOptions = { language?: string; rate?: number; pitch?: number };
export interface SpeechAdapter { speak(text: string, options?: SpeechOptions): void; stop(): void; }
export type SpeechRendererKind = "DEVICE_LOCAL_FALLBACK" | "TWELVE_HATS_SPEECH";
export const ACTIVE_SPEECH_RENDERER: SpeechRendererKind = "DEVICE_LOCAL_FALLBACK";

export const twelveHatsAudioSchema = z.object({
  audio: z.string().min(1), content_type: z.string().min(1), duration_ms: z.number().int().nonnegative(),
  model_version: z.string().min(1), render_version: z.string().min(1), render_digest: z.string().regex(/^[a-f0-9]{64}$/),
});
export type TwelveHatsAudio = z.infer<typeof twelveHatsAudioSchema>;

/** Reserved owned-engine boundary. It is intentionally unavailable until a governed contract is released. */
export const twelveHatsSpeech: SpeechAdapter | null = null;

/** The server-composed answer is the sole semantic input to native speech. */
export function spokenTextForResponse(response: LiaResponse): string { return response.answer.trim(); }

export const nativeSpeech: SpeechAdapter = {
  speak: (text, options) => { if (!text) return; Speech.speak(text, { language: options?.language ?? "en-US", rate: options?.rate ?? 0.94, pitch: options?.pitch ?? 1.0 }); },
  stop: () => { Speech.stop(); },
};
