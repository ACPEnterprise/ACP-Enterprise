import { z } from "zod";
import type { ApiClient } from "./client";

export const payStatementSchema = z.object({
  id: z.string().uuid(), pay_period_id: z.string().uuid(), version: z.number().int().positive(),
  currency: z.string(), payment_status: z.string(), ytd_status: z.string(), lifecycle: z.string(),
  digest: z.string(), corrected: z.boolean(),
}).strict();
export const payrollStatusSchema = z.object({
  statement_count: z.number().int().nonnegative(), current_statement_id: z.string().uuid().nullable(),
  current_pay_period_id: z.string().uuid().nullable(), payment_status: z.string(), ytd_status: z.string(), has_correction: z.boolean(),
}).strict();
export type PayStatement = z.infer<typeof payStatementSchema>;
export type PayrollStatus = z.infer<typeof payrollStatusSchema>;
export interface PayrollService {
  status(): Promise<PayrollStatus>;
  statements(): Promise<PayStatement[]>;
  artifact(statementId: string): Promise<string>;
}
export function createPayrollService(client: ApiClient): PayrollService {
  return {
    status: () => client.request("/api/v1/payroll/me/payroll-status", payrollStatusSchema),
    statements: () => client.request("/api/v1/payroll/me/pay-statements", z.array(payStatementSchema)),
    artifact: async (statementId) => (await client.requestText(`/api/v1/payroll/me/pay-statements/${encodeURIComponent(statementId)}/artifact`)).content,
  };
}
