import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { apiClient } from "../api/client";
import { brandConfig } from "../branding/brandConfig";
import { Alert, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Field, Input, Stack } from "../ui";

export function PasswordResetRoute() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [token] = useState(() => searchParams.get("token") ?? "");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [complete, setComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) window.history.replaceState(window.history.state, "", "/reset-password");
  }, [token]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    if (token && password !== confirmation) {
      setError("Passwords do not match.");
      return;
    }
    setSubmitting(true);
    try {
      if (token) {
        await apiClient.post("/api/v1/auth/password-reset/confirm", {
          token,
          new_password: password,
        });
      } else {
        await apiClient.post("/api/v1/auth/password-reset/request", { email });
      }
      setComplete(true);
      setPassword("");
      setConfirmation("");
    } catch {
      setError(token
        ? "This reset link is expired, already used, or unavailable. Request a new link."
        : "Password recovery is temporarily unavailable. Please try again later.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="safe-area-login grid min-h-screen min-h-dvh place-items-center bg-app-background p-ui-4 text-content">
      <div className="w-full max-w-[var(--content-compact)]">
        <Stack space="large">
          <p className="text-heading-s">{brandConfig.productName}</p>
          <Card elevation="medium">
            <CardHeader>
              <CardTitle className="text-heading-m">{token ? "Choose a new password" : "Reset your password"}</CardTitle>
              <CardDescription>{token ? "Create a new password only you will use." : "Enter your employee login email."}</CardDescription>
            </CardHeader>
            <CardContent>
              {complete ? (
                <Stack space="large">
                  <Alert variant="information">{token ? "Your password was reset. Sign in with your new password." : "If the account is eligible, recovery instructions will be sent."}</Alert>
                  <Button onClick={() => void navigate("/login", { replace: true })}>Return to sign in</Button>
                </Stack>
              ) : (
                <form onSubmit={submit} noValidate>
                  <Stack space="large">
                    {error && <Alert variant="danger" announcement="assertive">{error}</Alert>}
                    {token ? (
                      <>
                        <Field label="New password" controlId="reset-password" required>
                          <Input id="reset-password" type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={12} required disabled={submitting} />
                        </Field>
                        <Field label="Confirm new password" controlId="reset-password-confirmation" required>
                          <Input id="reset-password-confirmation" type="password" autoComplete="new-password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} minLength={12} required disabled={submitting} />
                        </Field>
                      </>
                    ) : (
                      <Field label="Email address" controlId="reset-email" required>
                        <Input id="reset-email" type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required disabled={submitting} />
                      </Field>
                    )}
                    <Button type="submit" fullWidth loading={submitting}>{token ? "Reset password" : "Send reset instructions"}</Button>
                  </Stack>
                </form>
              )}
            </CardContent>
          </Card>
        </Stack>
      </div>
    </main>
  );
}
