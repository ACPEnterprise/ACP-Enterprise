import { z } from "zod";
import type { ApiClient } from "./client";

export const serviceLocationSchema = z.object({
  label: z.string(),
  address_line_1: z.string(),
  address_line_2: z.string().nullable(),
  city: z.string(),
  state: z.string(),
  postal_code: z.string(),
  country: z.string(),
});

export const dayAssignmentSchema = z.object({
  appointment_id: z.string().uuid(),
  appointment_number: z.string(),
  appointment_status: z.string(),
  job_id: z.string().uuid().nullable(),
  job_number: z.string().nullable(),
  job_status: z.string().nullable(),
  service_category: z.string().nullable(),
  window_start_at: z.string().datetime({ offset: true }),
  window_end_at: z.string().datetime({ offset: true }),
  assignment_role: z.enum(["primary", "crew"]),
  assignment_status: z.string(),
  designation: z.enum(["current", "next"]).nullable(),
  customer_display_name: z.string(),
  service_location: serviceLocationSchema,
});

export const employeeDaySchema = z.object({
  business_date: z.string().date(),
  timezone: z.string(),
  assignments: z.array(dayAssignmentSchema),
});

export type DayAssignment = z.infer<typeof dayAssignmentSchema>;
export type EmployeeDay = z.infer<typeof employeeDaySchema>;

export interface EmployeeOperationsService {
  day(): Promise<EmployeeDay>;
}

export function createEmployeeOperationsService(client: ApiClient): EmployeeOperationsService {
  return {
    day: () => client.request("/api/v1/employee-operations/me/day", employeeDaySchema),
  };
}
