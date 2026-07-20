const refreshTokenKey = "acp.auth.refresh-token";
const activeCompanyKey = "acp.auth.active-company";

export function readRefreshToken(): string | null {
  return window.sessionStorage.getItem(refreshTokenKey);
}

export function writeRefreshToken(token: string): void {
  window.sessionStorage.setItem(refreshTokenKey, token);
}

export function clearRefreshToken(): void {
  window.sessionStorage.removeItem(refreshTokenKey);
}

export function readActiveCompanyId(): string | null {
  return window.sessionStorage.getItem(activeCompanyKey);
}

export function writeActiveCompanyId(companyId: string): void {
  window.sessionStorage.setItem(activeCompanyKey, companyId);
}

export function clearActiveCompanyId(): void {
  window.sessionStorage.removeItem(activeCompanyKey);
}
