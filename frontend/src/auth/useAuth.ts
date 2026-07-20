import { useContext } from "react";

import { AuthenticationContext } from "./AuthenticationContext";

export function useAuth() {
  const context = useContext(AuthenticationContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider.");
  return context;
}
