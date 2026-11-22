/**
 * Translate the short, natural-language commands people commonly use in the
 * header into the same searchable terms accepted by the Customer roster.
 * Search remains server-authoritative; this only removes command words.
 */
export function normalizeGlobalSearchQuery(value: string): string {
  return value
    .trim()
    .replace(/^(?:find|search(?:\s+for)?|show|open|lookup|locate|go\s+to)\b\s*/i, "")
    .replace(/\b(?:the|me|a|an|at|for|customer|client|account|history|record|records)\b/gi, " ")
    .replace(/['’]s\s*$/i, "")
    .replace(/\s+/g, " ")
    .trim();
}
