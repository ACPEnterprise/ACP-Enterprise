export type VoiceIntent =
  | { kind: "QUESTION" }
  | { kind: "NAVIGATE"; target: string }
  | { kind: "MUTATION_REQUEST"; action: string };

const mutationPatterns: ReadonlyArray<[RegExp, string]> = [
  [/\b(move|reschedule)\b.*\b(job|appointment)\b/i, "RESCHEDULE_APPOINTMENT"],
  [/\b(assign|dispatch)\b.*\b(job|technician)\b/i, "ASSIGN_DISPATCH"],
  [/\b(approve|run|execute)\b.*\bpayroll\b/i, "PAYROLL_EXECUTION"],
  [/\b(raise|change|activate)\b.*\b(price|pricing)\b/i, "PRICE_BOOK_CHANGE"],
  [/\b(post)\b.*\b(journal|accounting)\b/i, "ACCOUNTING_POST"],
  [
    /^\s*(?:please\s+)?(?:pay|refund|collect|initiate ach)\b/i,
    "MONEY_MOVEMENT",
  ],
  [/\b(grant|revoke|change)\b.*\b(permissions?|roles?)\b/i, "SECURITY_ADMIN"],
];

export function classifyVoiceIntent(transcript: string): VoiceIntent {
  for (const [pattern, action] of mutationPatterns) {
    if (pattern.test(transcript)) return { kind: "MUTATION_REQUEST", action };
  }
  const navigation = transcript.match(
    /^\s*(?:open|go to|take me to)\s+(.+?)[.!?]?\s*$/i,
  );
  if (navigation) return { kind: "NAVIGATE", target: navigation[1].trim() };
  return { kind: "QUESTION" };
}

export function matchingAuthorizedNavigation(
  transcript: string,
  navigation: ReadonlyArray<{ label: string; internal_path: string }>,
) {
  const intent = classifyVoiceIntent(transcript);
  if (intent.kind !== "NAVIGATE") return undefined;
  const words = intent.target.toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return navigation.find((item) => {
    if (!isSafeInternalNavigationPath(item.internal_path)) return false;
    const label = item.label.toLocaleLowerCase();
    const path = item.internal_path.toLocaleLowerCase();
    return words.some((word) => word.length > 2 && (label.includes(word) || path.includes(word)));
  });
}

export function isSafeInternalNavigationPath(path: string): boolean {
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("\\")) {
    return false;
  }
  const route = path.split(/[?#]/, 1)[0];
  return !route.split("/").includes("..");
}
