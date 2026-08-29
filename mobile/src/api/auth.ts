import { z } from "zod";
import type { ApiClient } from "./client";

const userSchema = z.object({ id: z.string(), display_name: z.string(), normalized_email: z.string() }).passthrough();
export const sessionSchema = z.object({
  user: userSchema,
  session_id: z.string(),
  access_token: z.string().min(1),
  refresh_token: z.string().min(1),
  access_token_expires_at: z.string(),
  refresh_token_expires_at: z.string(),
}).passthrough();

export function login(client: ApiClient, email: string, password: string) {
  return client.request("/api/v1/auth/login", sessionSchema, { method: "POST", authentication: "none", body: JSON.stringify({ email, password, device_label: "ACP Employee" }) });
}
export function refresh(client: ApiClient, refreshToken: string) {
  return client.request("/api/v1/auth/refresh", sessionSchema, { method: "POST", authentication: "none", body: JSON.stringify({ refresh_token: refreshToken }) });
}
export function logout(client: ApiClient) {
  return client.request("/api/v1/auth/logout", z.object({ message: z.string() }).passthrough(), { method: "POST" });
}
const verifiedSessionSchema = z.object({ session_id: z.string(), status: z.string(), absolute_expires_at: z.string(), idle_expires_at: z.string().nullable() }).passthrough();
export function verifySession(client: ApiClient) { return client.request("/api/v1/auth/session", verifiedSessionSchema, { unauthorized: "preserve" }); }

export const accessibleCompanySchema = z.object({ id: z.string(), membership_id: z.string(), default_branch_id: z.string().nullable(), branches: z.array(z.object({ id: z.string() }).passthrough()) }).passthrough();
export function accessibleCompanies(client: ApiClient) { return client.request("/api/v1/authorization/companies", z.array(accessibleCompanySchema)); }

const activationSchema = z.object({ status: z.string(), masked_login: z.string() }).passthrough();
export function completeActivation(client: ApiClient, token: string, password: string) {
  return client.request("/api/v1/identity-onboarding/activate/complete", activationSchema, { method: "POST", authentication: "none", conflict: "invitation_invalid", body: JSON.stringify({ token, password }) });
}
