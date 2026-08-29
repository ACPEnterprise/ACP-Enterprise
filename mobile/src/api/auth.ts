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
  return client.request("/api/v1/auth/login", sessionSchema, { method: "POST", body: JSON.stringify({ email, password, device_label: "ACP Employee" }) });
}
export function refresh(client: ApiClient, refreshToken: string) {
  return client.request("/api/v1/auth/refresh", sessionSchema, { method: "POST", body: JSON.stringify({ refresh_token: refreshToken }) });
}
export function logout(client: ApiClient) {
  return client.request("/api/v1/auth/logout", z.object({ message: z.string() }).passthrough(), { method: "POST" });
}
