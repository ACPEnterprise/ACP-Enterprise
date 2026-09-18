import type { LiaResponse } from "../../types/lia";

export type SpokenResponseMode = "BRIEF" | "NORMAL" | "DETAILED" | "EVIDENCE";

const sentenceBudget: Record<SpokenResponseMode, number> = {
  BRIEF: 2,
  NORMAL: 3,
  DETAILED: 6,
  EVIDENCE: 8,
};

const mechanicalTerms: ReadonlyArray<readonly [RegExp, string]> = [
  [/\bCOMPENSATION_MISSING_CONFIGURATION\b/g, "compensation setup is missing"],
  [/\bGROSS_PAY_NOT_CALCULATED\b/g, "gross pay hasn't been calculated"],
  [/\bPAYROLL_POLICY_MISSING_CONFIGURATION\b/g, "payroll policy setup is incomplete"],
  [/\bTIME_EVIDENCE_MISSING\b/g, "accepted time is missing"],
  [/\bWITHHOLDING_NOT_CALCULATED\b/g, "withholding hasn't been calculated"],
  [/\bINSUFFICIENT_EVIDENCE\b/g, "there isn't enough evidence yet"],
  [/\bSOURCE_BACKED\b/g, "source-backed"],
  [/\bACP_AUTHORITATIVE\b/g, "ACP-authoritative"],
  [/\bPOLICY_REQUIRED\b/g, "a policy decision is required"],
];

const contractions: ReadonlyArray<readonly [RegExp, string]> = [
  [/\bcannot\b/gi, "can't"],
  [/\bis not\b/gi, "isn't"],
  [/\bare not\b/gi, "aren't"],
  [/\bdoes not\b/gi, "doesn't"],
  [/\bdo not\b/gi, "don't"],
  [/\bhas not\b/gi, "hasn't"],
  [/\bhave not\b/gi, "haven't"],
  [/\bwe are\b/gi, "we're"],
  [/\bthey are\b/gi, "they're"],
  [/\bthat is\b/gi, "that's"],
  [/\bthere is\b/gi, "there's"],
];

const pronunciationTerms: ReadonlyArray<readonly [RegExp, string]> = [
  [/\bP\s*&\s*L\b/gi, "profit and loss"],
  [/\bQBO\b/g, "Q B O"],
  [/\bACP\b/g, "A C P"],
  [/\bHVAC\b/g, "H V A C"],
  [/\b(?:Job\s+)?JOB-(\d+)\b/gi, "Job $1"],
  [/\b(?:Invoice\s+)?INV-(\d+)\b/gi, "Invoice $1"],
  [/\b(?:Estimate\s+)?EST-(\d+)\b/gi, "Estimate $1"],
  [/\b(?:Appointment\s+)?APT-(\d+)\b/gi, "Appointment $1"],
];

function normalizeSpokenSemantics(value: string): string {
  let text = value
    .replace(/(^|[\s(])-\$(\d[\d,]*(?:\.\d+)?)/g, "$1negative $$$2")
    .replace(/(^|[\s(])-([\d,.]+)%(?=\s|[,.!?;:]|$)/g, "$1negative $2 percent")
    .replace(/([\d,.]+)%(?=\s|[,.!?;:]|$)/g, "$1 percent");

  for (const [pattern, replacement] of pronunciationTerms) {
    text = text.replace(pattern, replacement);
  }
  return text;
}

function cleanVisualScaffolding(value: string): string {
  let text = value
    .replace(/\bNo authorized authoritative evidence is available for this question\b/gi, "I don't have authorized evidence for that yet")
    .replace(/\bEvidence unavailable\b/gi, "I don't have that evidence yet")
    .replace(/^ACP's native authorized records show:\s*/i, "")
    .replace(/^Current authorized evidence\s*[—:-]\s*/i, "")
    .replace(/^Answer\s*:\s*/i, "")
    .replace(/^Correction\s*:\s*/i, "Got it — ")
    .replace(/^Topic changed\s*:\s*(.)/i, (_match, first: string) => `Now, ${first.toLocaleLowerCase()}`)
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/(^|[.!?]\s+)(?:\d+[.)]|(?:what is true|what is blocked|why|next step|evidence))\s*[:—-]?\s*/gim, "$1")
    .replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/gi, "the selected record")
    .replace(/^[-*•]\s*/gm, "")
    .replace(/\n\s*[-*•]?\s*/g, ". ")
    .replace(/\s*\|\s*/g, ". ")
    .replace(/\s+/g, " ")
    .trim();

  for (const [pattern, replacement] of mechanicalTerms) {
    text = text.replace(pattern, replacement);
  }
  for (const [pattern, replacement] of contractions) {
    text = text.replace(pattern, replacement);
  }

  text = normalizeSpokenSemantics(text);

  return text
    .replace(/\bCustomer status active\b/gi, "I found the customer; they're active")
    .replace(/\bCustomer status inactive\b/gi, "I found the customer; they're inactive")
    .replace(/\bJobs count (\d+)\b/gi, "$1 jobs are on record")
    .replace(/\bBalance ([\d,.]+) dollars?\b/gi, "The outstanding balance is $$$1")
    .replace(/\.{2,}/g, ".")
    .replace(/\s+([,.!?])/g, "$1")
    .trim();
}

function evidenceSummary(result: LiaResponse): string {
  const labels = [...new Set(result.evidence.map((item) => item.label.trim()).filter(Boolean))];
  if (!labels.length) return "No supporting evidence was available for this answer.";
  const sources = labels.slice(0, 3).join(", ");
  const extra = labels.length > 3 ? `, plus ${labels.length - 3} more sources` : "";
  const instant = new Date(result.as_of);
  const asOf = Number.isNaN(instant.valueOf())
    ? result.as_of
    : new Intl.DateTimeFormat("en-US", {
        month: "long",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZone: "UTC",
        timeZoneName: "short",
      }).format(instant);
  return `The supporting evidence comes from ${sources}${extra}, as of ${asOf}.`;
}

function sentences(value: string): string[] {
  return (value.match(/.*?[.!?]+(?=\s|$)|.+$/g) ?? [value])
    .map((sentence) => sentence.trim())
    .filter(Boolean);
}

function naturalNextAction(value: string): string {
  const action = value.trim().replace(/[.!?]+$/, "");
  const open = action.match(/^Open\s+(.+)$/i);
  if (open) return `You can open ${open[1]} next.`;
  const review = action.match(/^Review\s+(.+)$/i);
  if (review) return `The next step is to review ${review[1]}.`;
  const refresh = action.match(/^Refresh\s+(.+)$/i);
  if (refresh) return `Refresh ${refresh[1]} before relying on this.`;
  return `The next safe step is to ${action.charAt(0).toLowerCase()}${action.slice(1)}.`;
}

function mentionsAction(answer: string, action: string): boolean {
  const normalizedAnswer = answer.toLocaleLowerCase();
  const normalizedAction = action
    .replace(/^(open|review|refresh)\s+/i, "")
    .toLocaleLowerCase();
  return normalizedAction.length > 3 && normalizedAnswer.includes(normalizedAction);
}

export function spokenAnswer(
  result: LiaResponse,
  mode: SpokenResponseMode = "NORMAL",
): string {
  const cleaned = cleanVisualScaffolding(result.answer);
  const selected = sentences(cleaned).slice(0, sentenceBudget[mode]);
  let answer = selected.join(" ").trim();

  if (
    result.authority === "SOURCE_BACKED" &&
    !/source[- ]backed|source evidence|quickbooks/i.test(answer)
  ) {
    answer += " That's source-backed evidence, not an ACP-native fact.";
  }

  const next = result.safe_next_action?.trim();
  if (
    next &&
    mode !== "EVIDENCE" &&
    !mentionsAction(answer, next) &&
    !/^Refresh authoritative ACP evidence$/i.test(next)
  ) {
    answer += ` ${naturalNextAction(next)}`;
  }

  if (mode === "EVIDENCE") {
    answer += ` ${evidenceSummary(result)}`;
  }

  return answer;
}
