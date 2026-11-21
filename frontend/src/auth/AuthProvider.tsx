import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import * as authenticationApi from "../api/auth";
import { getEffectiveAuthorization, listAccessibleCompanies } from "../api/authorization";
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
  const [permissionCodes, setPermissionCodes] = useState<readonly string[]>([]);
  const accessTokenRef = useRef<string | null>(null);
  const activeCompanyRef = useRef<AccessibleCompany | null>(null);
  const refreshPromiseRef = useRef<Promise<string | null> | null>(null);

  const clearAuthentication = useCallback(() => {
    accessTokenRef.current = null;
    clearRefreshToken();
    clearActiveCompanyId();
    activeCompanyRef.current = null;
    setActiveCompany(null);
    setPermissionCodes([]);
    setUser(null);
    setStatus("unauthenticated");
  }, []);

  const applyAuthentication = useCallback((result: AuthenticationResult) => {
    accessTokenRef.current = result.access_token;
    writeRefreshToken(result.refresh_token);
    setUser(result.user);
    return result.access_token;
  }, []);

  const resolveCompanyAccess = useCallback(async (preferredCompanyId?: string) => {
    const companies = await listAccessibleCompanies();
    const savedCompanyId = readActiveCompanyId();
    const company = preferredCompanyId
      ? companies.find((item) => item.id === preferredCompanyId) ?? null
      : companies.find((item) => item.id === savedCompanyId) ?? companies[0] ?? null;
    if (!company) {
      if (preferredCompanyId) throw new Error("The requested company is not available to this account.");
      clearAuthentication();
      throw new Error("No active company access is available.");
    }
    const previousCompany = activeCompanyRef.current;
    activeCompanyRef.current = company;
    try {
      const authorization = await getEffectiveAuthorization();
      setActiveCompany(company);
      writeActiveCompanyId(company.id);
      setPermissionCodes(authorization.permission_codes);
      setStatus("authenticated");
    } catch (error) {
      activeCompanyRef.current = previousCompany;
      if (previousCompany) {
        setActiveCompany(previousCompany);
        writeActiveCompanyId(previousCompany.id);
      }
      throw error;
    }
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

  const refreshAuthorization = useCallback(async () => {
    const accessToken = await refresh();
    if (!accessToken) throw new Error("The authenticated session could not be refreshed.");
    await resolveCompanyAccess();
  }, [refresh, resolveCompanyAccess]);

  const switchCompany = useCallback(async (companyId: string) => {
    await resolveCompanyAccess(companyId);
  }, [resolveCompanyAccess]);

  const value = useMemo(
    () => ({ status, user, activeCompany, permissionCodes, signIn, signOut, signOutAll, switchCompany, refreshAuthorization, requireReauthentication: clearAuthentication }),
    [activeCompany, clearAuthentication, permissionCodes, refreshAuthorization, signIn, signOut, signOutAll, status, switchCompany, user],
  );
  return <AuthenticationContext.Provider value={value}>{children}</AuthenticationContext.Provider>;
}
