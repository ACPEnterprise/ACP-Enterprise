export type CommercialOnboardingStep =
  | "company"
  | "systems"
  | "import"
  | "review"
  | "ready";

export interface CommercialOnboardingDraft {
  companyName: string;
  businessType: string;
  primaryLocation: string;
  timezone: string;
  crm: string;
  accounting: string;
  payroll: string;
  step: CommercialOnboardingStep;
  completed: boolean;
  deferredExceptionIds: string[];
}

const keyFor = (companyId: string) => `twelvehats.commercial-onboarding.${companyId}`;

export const defaultCommercialOnboardingDraft = (
  companyName = "",
): CommercialOnboardingDraft => ({
  companyName,
  businessType: "",
  primaryLocation: "",
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "America/New_York",
  crm: "",
  accounting: "",
  payroll: "same",
  step: "company",
  completed: false,
  deferredExceptionIds: [],
});

export function loadCommercialOnboardingDraft(
  companyId: string,
  companyName = "",
): CommercialOnboardingDraft {
  const fallback = defaultCommercialOnboardingDraft(companyName);
  try {
    const raw = window.localStorage.getItem(keyFor(companyId));
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<CommercialOnboardingDraft>;
    return {
      ...fallback,
      ...parsed,
      companyName: parsed.companyName || companyName,
      deferredExceptionIds: Array.isArray(parsed.deferredExceptionIds)
        ? parsed.deferredExceptionIds.filter((item): item is string => typeof item === "string")
        : [],
    };
  } catch {
    return fallback;
  }
}

export function saveCommercialOnboardingDraft(
  companyId: string,
  draft: CommercialOnboardingDraft,
): void {
  try {
    window.localStorage.setItem(keyFor(companyId), JSON.stringify(draft));
  } catch {
    // Resume is best effort when browser storage is unavailable.
  }
}

export function isCommercialOnboardingComplete(companyId: string): boolean {
  return loadCommercialOnboardingDraft(companyId).completed;
}
