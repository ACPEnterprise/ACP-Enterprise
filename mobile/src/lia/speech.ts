import * as Speech from "expo-speech";
import type { LiaResponse } from "../api/lia";

export type SpeechOptions = { language?: string; rate?: number; pitch?: number };
export interface SpeechAdapter { speak(text: string, options?: SpeechOptions): void; stop(): void; }

/** The server-composed answer is the sole semantic input to native speech. */
export function spokenTextForResponse(response: LiaResponse): string { return response.answer.trim(); }

export const nativeSpeech: SpeechAdapter = {
  speak: (text, options) => { if (!text) return; Speech.speak(text, { language: options?.language ?? "en-US", rate: options?.rate ?? 0.94, pitch: options?.pitch ?? 1.0 }); },
  stop: () => { Speech.stop(); },
};
