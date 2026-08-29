export type ApiFailureKind = "unauthenticated" | "forbidden" | "offline" | "timeout" | "unavailable" | "malformed_response" | "configuration";
export class ApiFailure extends Error { constructor(public readonly kind: ApiFailureKind, message: string) { super(message); } }
