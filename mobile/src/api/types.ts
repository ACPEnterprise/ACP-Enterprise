export type ApiFailureKind = "invalid_credentials" | "invitation_invalid" | "rate_limited" | "unauthenticated" | "forbidden" | "conflict" | "not_ready" | "offline" | "timeout" | "unavailable" | "malformed_response" | "configuration";
export class ApiFailure extends Error { constructor(public readonly kind: ApiFailureKind, message: string) { super(message); } }
