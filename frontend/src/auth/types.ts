export interface AuthenticatedUser {
  id: string;
  normalized_email: string;
  first_name: string;
  last_name: string;
  display_name: string;
  email_verified_at: string | null;
}

export interface AuthenticationResult {
  token_type: "bearer";
  user: AuthenticatedUser;
  session_id: string;
  access_token: string;
  refresh_token: string;
  access_token_expires_at: string;
  refresh_token_expires_at: string;
  session_absolute_expires_at: string | null;
  session_idle_expires_at: string | null;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export type AuthenticationStatus = "restoring" | "authenticated" | "unauthenticated";
