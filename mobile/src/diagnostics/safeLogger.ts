const SECRET_FIELDS = /token|password|authorization|credential|invitation|secret|customer|address|email|payroll|compensation|payload|body/i;
export type SafeLogger = { info(message: string, context?: Record<string, unknown>): void; error(message: string, context?: Record<string, unknown>): void };
function safeValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(safeValue);
  if (value && typeof value === "object") return sanitize(value as Record<string, unknown>);
  return value;
}
function sanitize(context?: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(context ?? {}).map(([key, value]) => [key, SECRET_FIELDS.test(key) ? "[REDACTED]" : safeValue(value)]));
}
export const safeLogger: SafeLogger = {
  info: (message, context) => console.info(message, sanitize(context)),
  error: (message, context) => console.error(message, sanitize(context)),
};
