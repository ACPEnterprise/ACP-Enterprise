import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { apiClient } from "../api/client";
import { brandConfig } from "../branding/brandConfig";
import { Alert, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Field, Input, Stack } from "../ui";

export function ActivationRoute() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [token] = useState(() => searchParams.get("token") ?? "");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [complete, setComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    window.history.replaceState(window.history.state, "", "/activate");
  }, []);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    if (!token) {
      setError("This activation link is invalid. Ask your ACP administrator for a current invitation.");
      return;
    }
    if (password !== confirmation) {
      setError("Passwords do not match.");
      return;
    }
    setSubmitting(true);
    try {
      await apiClient.post("/api/v1/identity-onboarding/activate/complete", { token, password });
      setComplete(true);
      setPassword("");
      setConfirmation("");
    } catch {
      setError("This activation link is expired, already used, or unavailable. Ask your ACP administrator for a current invitation.");
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
              <CardTitle className="text-heading-m">Activate your ACP account</CardTitle>
              <CardDescription>Create the password only you will use to sign in.</CardDescription>
            </CardHeader>
            <CardContent>
              {complete ? (
                <Stack space="large">
                  <Alert variant="information">Your account is activated. You can now sign in.</Alert>
                  <Button onClick={() => void navigate("/login", { replace: true })}>Continue to sign in</Button>
                </Stack>
              ) : (
                <form onSubmit={submit} noValidate>
                  <Stack space="large">
                    {!token && <Alert variant="danger">This activation link is invalid. Ask your ACP administrator for a current invitation.</Alert>}
                    {error && <Alert variant="danger" announcement="assertive">{error}</Alert>}
                    <Field label="New password" controlId="activation-password" required>
                      <Input id="activation-password" type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={12} required disabled={submitting || !token} />
                    </Field>
                    <Field label="Confirm new password" controlId="activation-password-confirmation" required>
                      <Input id="activation-password-confirmation" type="password" autoComplete="new-password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} minLength={12} required disabled={submitting || !token} />
                    </Field>
                    <Button type="submit" fullWidth loading={submitting} disabled={!token}>Activate account</Button>
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
