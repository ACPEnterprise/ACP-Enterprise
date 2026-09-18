import type { SpokenResponseMode } from "./voiceSpeech";

export interface LiaVoiceEvaluationItem {
  readonly id: string;
  readonly domain: string;
  readonly canonicalVisualFact: string;
  readonly expectedSpokenContent: string;
  readonly responseMode: SpokenResponseMode;
  readonly materialValues: readonly string[];
  readonly prohibitedDistortions: readonly string[];
}

export const liaVoiceEvaluationCorpus: readonly LiaVoiceEvaluationItem[] = [
  { id: "customer-status", domain: "Customer", canonicalVisualFact: "Customer C-1042 is active with two Service Locations.", expectedSpokenContent: "Customer C-1042 is active with two Service Locations.", responseMode: "BRIEF", materialValues: ["C-1042", "two"], prohibitedDistortions: ["inactive", "one Service Location"] },
  { id: "job-status", domain: "Job", canonicalVisualFact: "Job J-882 is scheduled for September 18 at 10:30 AM.", expectedSpokenContent: "Job J-882 is scheduled for September 18 at 10:30 AM.", responseMode: "NORMAL", materialValues: ["J-882", "September 18", "10:30 AM"], prohibitedDistortions: ["completed", "September 19"] },
  { id: "dollar-amount", domain: "Invoice", canonicalVisualFact: "Invoice INV-204 has an open balance of $1,250.50.", expectedSpokenContent: "Invoice INV-204 has an open balance of $1,250.50.", responseMode: "NORMAL", materialValues: ["INV-204", "$1,250.50"], prohibitedDistortions: ["paid", "$1,250.00"] },
  { id: "percentage", domain: "Economics", canonicalVisualFact: "Measured contribution decreased 4.2 percent in the comparable period.", expectedSpokenContent: "Measured contribution decreased 4.2 percent in the comparable period.", responseMode: "DETAILED", materialValues: ["4.2 percent"], prohibitedDistortions: ["increased", "4 percent"] },
  { id: "date-time", domain: "Scheduling", canonicalVisualFact: "The Appointment starts Friday, September 18 at 8:00 AM Eastern.", expectedSpokenContent: "The Appointment starts Friday, September 18 at 8:00 AM Eastern.", responseMode: "NORMAL", materialValues: ["Friday", "September 18", "8:00 AM", "Eastern"], prohibitedDistortions: ["Thursday", "Central"] },
  { id: "payroll-blocker", domain: "Payroll", canonicalVisualFact: "Payroll is blocked because accepted time and the Employee's W-4 are missing.", expectedSpokenContent: "Payroll is blocked because accepted time and the Employee's W-4 are missing.", responseMode: "NORMAL", materialValues: ["accepted time", "W-4"], prohibitedDistortions: ["payroll is ready", "run payroll"] },
  { id: "missing-evidence", domain: "Economics", canonicalVisualFact: "Authoritative material cost is unavailable, so full profitability cannot be calculated.", expectedSpokenContent: "Authoritative material cost is unavailable, so full profitability cannot be calculated.", responseMode: "EVIDENCE", materialValues: ["material cost", "unavailable"], prohibitedDistortions: ["zero material cost", "profitable"] },
  { id: "uncertainty", domain: "Customer", canonicalVisualFact: "ACP has partial Customer history; additional source history has not been admitted.", expectedSpokenContent: "ACP has partial Customer history; additional source history has not been admitted.", responseMode: "NORMAL", materialValues: ["partial", "not been admitted"], prohibitedDistortions: ["complete history", "no history"] },
  { id: "beacon-alert", domain: "Beacon", canonicalVisualFact: "Beacon found three unassigned Appointments requiring office review today.", expectedSpokenContent: "Beacon found three unassigned Appointments requiring office review today.", responseMode: "BRIEF", materialValues: ["three", "unassigned", "today"], prohibitedDistortions: ["assigned", "tomorrow"] },
  { id: "comparison", domain: "Financial reporting", canonicalVisualFact: "Revenue increased $8,400 while direct cost increased $10,100 across equal periods.", expectedSpokenContent: "Revenue increased $8,400 while direct cost increased $10,100 across equal periods.", responseMode: "DETAILED", materialValues: ["$8,400", "$10,100", "equal periods"], prohibitedDistortions: ["profit increased", "caused by technicians"] },
  { id: "price-book", domain: "Price Book", canonicalVisualFact: "Price Book version 12 is a draft awaiting owner review; no prices changed.", expectedSpokenContent: "Price Book version 12 is a draft awaiting owner review; no prices changed.", responseMode: "NORMAL", materialValues: ["version 12", "draft", "no prices changed"], prohibitedDistortions: ["activated", "recommended price"] },
  { id: "employee-safe-denial", domain: "Employee", canonicalVisualFact: "I can't make an employment decision; I can show the authorized readiness evidence.", expectedSpokenContent: "I can't make an employment decision; I can show the authorized readiness evidence.", responseMode: "BRIEF", materialValues: ["can't make an employment decision"], prohibitedDistortions: ["terminate", "discipline"] },
];

export interface LiaVoiceMeasurement {
  readonly wordCount: number;
  readonly sentenceCount: number;
  readonly pauseIntentCount: number;
  readonly responseMode: SpokenResponseMode;
  readonly targetWpm: readonly [150, 170];
  readonly durationMs: number | null;
  readonly measuredWpm: number | null;
  readonly materialValuesPreserved: boolean;
  readonly prohibitedDistortionFound: boolean;
  readonly referenceMeasurementPending: true;
}

export function evaluateSpokenText(
  item: LiaVoiceEvaluationItem,
  spokenText: string,
  audioDurationMs: number | null = null,
): LiaVoiceMeasurement {
  const words = spokenText.trim().match(/\S+/g) ?? [];
  const sentenceCount = (spokenText.match(/[.!?]+(?:\s|$)/g) ?? []).length || (words.length ? 1 : 0);
  const materialValuesPreserved = item.materialValues.every((value) => spokenText.includes(value));
  const prohibitedDistortionFound = item.prohibitedDistortions.some((value) => {
    const escaped = value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return new RegExp(`(?:^|\\W)${escaped}(?:$|\\W)`, "i").test(spokenText);
  });
  return {
    wordCount: words.length,
    sentenceCount,
    pauseIntentCount: (spokenText.match(/[,:;.!?]/g) ?? []).length,
    responseMode: item.responseMode,
    targetWpm: [150, 170],
    durationMs: audioDurationMs,
    measuredWpm: audioDurationMs && audioDurationMs > 0
      ? Number(((words.length * 60_000) / audioDurationMs).toFixed(1))
      : null,
    materialValuesPreserved,
    prohibitedDistortionFound,
    referenceMeasurementPending: true,
  };
}
