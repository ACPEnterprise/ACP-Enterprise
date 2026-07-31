import axios, { type InternalAxiosRequestConfig } from "axios";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() || "/";

export const apiClient = axios.create({
  baseURL: apiBaseUrl,
  timeout: 10_000,
  headers: {
    "Content-Type": "application/json",
  },
});

interface RetriableRequestConfig extends InternalAxiosRequestConfig {
  authenticationRetry?: boolean;
}

interface AuthenticationHandlers {
  getAccessToken: () => string | null;
  getActiveCompanyId: () => string | null;
  refresh: () => Promise<string | null>;
  clear: () => void;
}

let authenticationHandlers: AuthenticationHandlers | null = null;

export function authenticatedRequestHeaders(): Headers {
  const headers = new Headers({ Accept: "text/event-stream" });
  const accessToken = authenticationHandlers?.getAccessToken();
  const companyId = authenticationHandlers?.getActiveCompanyId();
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (companyId) headers.set("X-Company-ID", companyId);
  return headers;
}

export function activeCompanyId(): string | null {
  return authenticationHandlers?.getActiveCompanyId() ?? null;
}

export async function refreshAuthentication(): Promise<boolean> {
  return Boolean(await authenticationHandlers?.refresh());
}

export function apiUrl(path: string): string {
  return new URL(path.replace(/^\//, ""), new URL(apiBaseUrl, window.location.origin)).toString();
}

export function configureAuthentication(handlers: AuthenticationHandlers | null): void {
  authenticationHandlers = handlers;
}

apiClient.interceptors.request.use((config) => {
  const accessToken = authenticationHandlers?.getAccessToken();
  if (accessToken) config.headers.set("Authorization", `Bearer ${accessToken}`);
  const companyId = authenticationHandlers?.getActiveCompanyId();
  if (companyId) config.headers.set("X-Company-ID", companyId);
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (!axios.isAxiosError(error) || error.response?.status !== 401 || !error.config) {
      return Promise.reject(error);
    }

    const request = error.config as RetriableRequestConfig;
    const isAuthenticationRequest = request.url?.includes("/api/v1/auth/") ?? false;
    if (!authenticationHandlers || request.authenticationRetry || isAuthenticationRequest) {
      return Promise.reject(error);
    }

    request.authenticationRetry = true;
    const accessToken = await authenticationHandlers.refresh();
    if (!accessToken) {
      authenticationHandlers.clear();
      return Promise.reject(error);
    }

    request.headers.set("Authorization", `Bearer ${accessToken}`);
    return apiClient.request(request);
  },
);
