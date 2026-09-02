export type ApiFailureKind = "invalid_credentials" | "invitation_invalid" | "invalid_request" | "not_found" | "rate_limited" | "unauthenticated" | "forbidden" | "conflict" | "not_ready" | "offline" | "timeout" | "unavailable" | "malformed_response" | "configuration";
export type RecoveryClassification = "RETRY_SAFE" | "RETRY_AFTER_REFRESH" | "USER_CORRECTION_REQUIRED" | "OWNER_ADMIN_ACTION_REQUIRED" | "RECONCILIATION_REQUIRED" | "TEMPORARILY_UNAVAILABLE" | "TERMINAL_FAILURE";
export function recoveryFor(kind: ApiFailureKind): RecoveryClassification {
  if (kind === "offline" || kind === "timeout" || kind === "rate_limited") return "RETRY_SAFE";
  if (kind === "conflict") return "RETRY_AFTER_REFRESH";
  if (kind === "invalid_credentials" || kind === "invitation_invalid" || kind === "invalid_request") return "USER_CORRECTION_REQUIRED";
  if (kind === "forbidden" || kind === "not_ready") return "OWNER_ADMIN_ACTION_REQUIRED";
  if (kind === "unauthenticated") return "RECONCILIATION_REQUIRED";
  if (kind === "unavailable") return "TEMPORARILY_UNAVAILABLE";
  return "TERMINAL_FAILURE";
}
export class ApiFailure extends Error {
  readonly recovery: RecoveryClassification;
  constructor(public readonly kind: ApiFailureKind, message: string, public readonly correlationId?: string, recovery?: RecoveryClassification) { super(message); this.recovery = recovery ?? recoveryFor(kind); }
}
