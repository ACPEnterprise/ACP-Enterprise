export interface ReadinessExplanation {
  missing: string;
  actor: "OWNER" | "EMPLOYEE" | "APPLE / EXTERNAL" | "SYSTEM";
  next: string;
}

const explanations: Record<string, ReadinessExplanation> = {
  OWNER_EMPLOYEE_BINDING_REQUIRED: { missing: "The real roster identity is not bound to an exact ACP Employee.", actor: "OWNER", next: "Select only the independently verified Employee, or use protected onboarding." },
  BOUND_EMPLOYEE_MISSING: { missing: "The certified roster binding no longer resolves to an ACP Employee.", actor: "SYSTEM", next: "Enterprise must reconcile the preserved binding before access is enabled." },
  USER_NOT_READY: { missing: "The Employee does not have an active ACP User.", actor: "OWNER", next: "Complete normal onboarding or restore sanctioned account access." },
  EMPLOYEE_NOT_READY: { missing: "The ACP Employee record is inactive or unavailable.", actor: "OWNER", next: "Review Employee lifecycle state and reactivate only when authorized." },
  MEMBERSHIP_NOT_READY: { missing: "Company Membership is missing, invited, suspended, or revoked.", actor: "OWNER", next: "Complete activation or restore the existing Membership through Account Access." },
  MAIN_BRANCH_NOT_READY: { missing: "MAIN Branch is not the Employee home Branch or authorized Membership Branch.", actor: "OWNER", next: "Confirm the correct Branch and grant it through normal Employee administration." },
  OPERATING_ROLE_NOT_READY: { missing: "The owner-confirmed operating role is not assigned.", actor: "OWNER", next: "Assign the verified operating role without replacing unrelated legitimate roles." },
  WORKFORCE_PROFILE_NOT_READY: { missing: "No active Workforce capability profile exists.", actor: "OWNER", next: "Create the profile through the bounded field-readiness workflow." },
  TECHNICIAN_CAPABILITY_NOT_READY: { missing: "Technician capability has not been owner-certified.", actor: "OWNER", next: "Certify only the supported capability backed by human authority." },
  MOBILE_ROLE_NOT_READY: { missing: "ACP Employee Mobile authority is not active.", actor: "OWNER", next: "Assign ACP_EMPLOYEE_MOBILE after identity, Membership, and Branch are correct." },
  PASSWORD_NOT_ESTABLISHED: { missing: "The Employee has not established an ACP password.", actor: "EMPLOYEE", next: "Use the single-use activation or password-recovery flow; administrators cannot set it." },
  PROFILE_MISSING: { missing: "No active Workforce profile supports assignment readiness.", actor: "OWNER", next: "Review the Employee and record authorized Workforce evidence." },
  BRANCH_INELIGIBLE: { missing: "The Employee is not eligible for the requested Branch.", actor: "OWNER", next: "Confirm Branch authority; do not infer coverage from prior Jobs." },
  AVAILABILITY_MISSING: { missing: "No bounded available window covers the requested work period.", actor: "OWNER", next: "Record the human-confirmed Branch availability window." },
};

export function explainReadiness(code: string): ReadinessExplanation {
  return explanations[code] ?? {
    missing: `Readiness evidence is incomplete (${code.replaceAll("_", " ").toLowerCase()}).`,
    actor: "SYSTEM",
    next: "Refresh authority and review the Employee evidence before making changes.",
  };
}
