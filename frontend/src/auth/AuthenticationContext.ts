import { createContext } from "react";

import type { AuthenticatedUser, AuthenticationStatus, LoginCredentials } from "./types";
import type { AccessibleCompany } from "./companyTypes";

export interface AuthenticationContextValue {
  status: AuthenticationStatus;
  user: AuthenticatedUser | null;
  activeCompany: AccessibleCompany | null;
  permissionCodes?: readonly string[];
  signIn: (credentials: LoginCredentials) => Promise<void>;
  signOut: () => Promise<void>;
  signOutAll: () => Promise<void>;
  requireReauthentication: () => void;
}

export const AuthenticationContext = createContext<AuthenticationContextValue | null>(null);
