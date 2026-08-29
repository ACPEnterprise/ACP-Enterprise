export type UserIdentity = { id: string; display_name: string; normalized_email: string };
export type Session = {
  user: UserIdentity;
  session_id: string;
  access_token: string;
  refresh_token: string;
  access_token_expires_at: string;
  refresh_token_expires_at: string;
};
export type AuthState = "restoring" | "anonymous" | "authenticated" | "expired";
