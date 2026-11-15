import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import * as authenticationApi from "../api/auth";
import { useAuth } from "../auth";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Field,
  Input,
  Stack,
} from "../ui";

export function AccountSecurityRoute() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    if (newPassword !== confirmation) {
      setError("New passwords do not match.");
      return;
    }
    setSubmitting(true);
    try {
      await authenticationApi.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
        confirm_new_password: confirmation,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmation("");
      await signOut();
      await navigate("/login", { replace: true, state: { passwordChanged: true } });
    } catch (requestError: unknown) {
      const response = requestError && typeof requestError === "object" && "response" in requestError
        ? requestError.response
        : null;
      const detail = response && typeof response === "object" && "data" in response && response.data && typeof response.data === "object" && "detail" in response.data
        ? response.data.detail
        : null;
      setError(typeof detail === "string" ? detail : "The password could not be changed. Check your current password and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="mx-auto w-full max-w-3xl space-y-ui-6">
      <header>
        <p className="text-body-s font-semibold text-action-primary">Account</p>
        <h2 className="mt-ui-1 text-heading-l text-content">Security</h2>
        <p className="mt-ui-2 text-body-m text-content-muted">Manage your sign-in credential without changing your employee identity or access.</p>
      </header>
      <Card>
        <CardHeader>
          <CardTitle>Login identity</CardTitle>
          <CardDescription>Your email remains attached to the same User, Membership, Employee, Branch, and role history.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="rounded-[var(--radius-control)] bg-surface-muted px-ui-3 py-ui-2 text-body-m font-medium text-content" data-testid="account-login-email">
            {user?.normalized_email ?? "Unavailable"}
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Change password</CardTitle>
          <CardDescription>After saving, your current session ends and you must sign in again with the new password.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} noValidate>
            <Stack space="large">
              {error && <Alert variant="danger" announcement="assertive">{error}</Alert>}
              <Field label="Current password" controlId="account-current-password" required>
                <Input id="account-current-password" name="current_password" type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required disabled={submitting} />
              </Field>
              <Field label="New password" controlId="account-new-password" required>
                <Input id="account-new-password" name="new_password" type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} minLength={12} required disabled={submitting} />
              </Field>
              <Field label="Confirm new password" controlId="account-confirm-password" required>
                <Input id="account-confirm-password" name="confirm_new_password" type="password" autoComplete="new-password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} minLength={12} required disabled={submitting} />
              </Field>
              <Button type="submit" fullWidth loading={submitting} loadingLabel="Changing password">Change password</Button>
            </Stack>
          </form>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Session</CardTitle>
          <CardDescription>Sign out of this browser when you are finished.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="secondary" onClick={() => void signOut()}>Log out</Button>
        </CardContent>
      </Card>
    </main>
  );
}
