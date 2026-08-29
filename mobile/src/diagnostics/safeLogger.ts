const SECRET_FIELDS = /token|password|authorization|credential|compensation/i;
export type SafeLogger = { info(message: string, context?: Record<string, unknown>): void; error(message: string, context?: Record<string, unknown>): void };
function sanitize(context?: Record<string, unknown>) {
  return Object.fromEntries(Object.entries(context ?? {}).map(([key, value]) => [key, SECRET_FIELDS.test(key) ? "[REDACTED]" : value]));
}
export const safeLogger: SafeLogger = {
  info: (message, context) => console.info(message, sanitize(context)),
  error: (message, context) => console.error(message, sanitize(context)),
};
