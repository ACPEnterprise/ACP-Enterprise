export function humanizeCommercialState(value: string | null | undefined): string {
  if (!value) return "Not recorded";
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function accountingReadbackLabel(value: string): string {
  switch (value) {
    case "pending":
      return "Not posted";
    case "posted":
      return "Posted";
    case "reversed":
      return "Reversed";
    case "reconciliation_required":
      return "Needs review";
    default:
      return humanizeCommercialState(value);
  }
}
