import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import * as authenticationApi from "../api/auth";
import { listAccessibleCompanies } from "../api/authorization";
import { configureAuthentication } from "../api/client";
import { AuthenticationContext } from "./AuthenticationContext";
import {
  clearActiveCompanyId,
  clearRefreshToken,
  readActiveCompanyId,
  readRefreshToken,
  writeActiveCompanyId,
  writeRefreshToken,
} from "./sessionStorage";
import type { AccessibleCompany } from "./companyTypes";
import type { AuthenticatedUser, AuthenticationResult, AuthenticationStatus, LoginCredentials } from "./types";

export interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [status, setStatus] = useState<AuthenticationStatus>("restoring");
  const [user, setUser] = useState<AuthenticatedUser | null>(null);
  const [activeCompany, setActiveCompany] = useState<AccessibleCompany | null>(null);
  const accessTokenRef = useRef<string | null>(null);
  const activeCompanyRef = useRef<AccessibleCompany | null>(null);
  const refreshPromiseRef = useRef<Promise<string | null> | null>(null);

  const clearAuthentication = useCallback(() => {
    accessTokenRef.current = null;
    clearRefreshToken();
    clearActiveCompanyId();
    activeCompanyRef.current = null;
    setActiveCompany(null);
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  const applyAuthentication = useCallback((result: AuthenticationResult) => {
    accessTokenRef.current = result.access_token;
    writeRefreshToken(result.refresh_token);
    setUser(result.user);
    return result.access_token;
  }, []);

  const resolveCompanyAccess = useCallback(async () => {
    const companies = await listAccessibleCompanies();
    const savedCompanyId = readActiveCompanyId();
    const company = companies.find((item) => item.id === savedCompanyId) ?? companies[0] ?? null;
    if (!company) {
      clearAuthentication();
      throw new Error("No active company access is available.");
    }
    activeCompanyRef.current = company;
    setActiveCompany(company);
    writeActiveCompanyId(company.id);
    setStatus("authenticated");
  }, [clearAuthentication]);

  const refresh = useCallback((): Promise<string | null> => {
    if (refreshPromiseRef.current) return refreshPromiseRef.current;
    const refreshToken = readRefreshToken();
    if (!refreshToken) return Promise.resolve(null);

    const request = authenticationApi
      .refreshSession(refreshToken)
      .then(applyAuthentication)
      .catch(() => {
        clearAuthentication();
        return null;
      })
      .finally(() => {
        refreshPromiseRef.current = null;
      });
    refreshPromiseRef.current = request;
    return request;
  }, [applyAuthentication, clearAuthentication]);

  useEffect(() => {
    configureAuthentication({
      getAccessToken: () => accessTokenRef.current,
      getActiveCompanyId: () => activeCompanyRef.current?.id ?? null,
      refresh,
      clear: clearAuthentication,
    });
    void refresh()
      .then((accessToken) => (accessToken ? resolveCompanyAccess() : undefined))
      .finally(() => {
        setStatus((current) => (current === "restoring" ? "unauthenticated" : current));
      });
    return () => configureAuthentication(null);
  }, [clearAuthentication, refresh, resolveCompanyAccess]);

  const signIn = useCallback(
    async (credentials: LoginCredentials) => {
      applyAuthentication(await authenticationApi.login(credentials));
      await resolveCompanyAccess();
    },
    [applyAuthentication, resolveCompanyAccess],
  );

  const signOut = useCallback(async () => {
    try {
      if (accessTokenRef.current) await authenticationApi.logout();
    } finally {
      clearAuthentication();
    }
  }, [clearAuthentication]);

  const signOutAll = useCallback(async () => {
    try {
      if (accessTokenRef.current) await authenticationApi.logoutAll();
    } finally {
      clearAuthentication();
    }
  }, [clearAuthentication]);

  const value = useMemo(
    () => ({ status, user, activeCompany, signIn, signOut, signOutAll }),
    [activeCompany, signIn, signOut, signOutAll, status, user],
  );
  return <AuthenticationContext.Provider value={value}>{children}</AuthenticationContext.Provider>;
}
