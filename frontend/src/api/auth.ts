import type { AuthenticationResult, LoginCredentials } from "../auth/types";
import { apiClient } from "./client";

export async function login(credentials: LoginCredentials): Promise<AuthenticationResult> {
  const response = await apiClient.post<AuthenticationResult>("/api/v1/auth/login", {
    ...credentials,
    device_label: "ACP Enterprise Browser",
  });
  return response.data;
}

export async function refreshSession(refreshToken: string): Promise<AuthenticationResult> {
  const response = await apiClient.post<AuthenticationResult>("/api/v1/auth/refresh", {
    refresh_token: refreshToken,
  });
  return response.data;
}

export async function logout(): Promise<void> {
  await apiClient.post("/api/v1/auth/logout");
}

export async function logoutAll(): Promise<void> {
  await apiClient.post("/api/v1/auth/logout-all");
}
