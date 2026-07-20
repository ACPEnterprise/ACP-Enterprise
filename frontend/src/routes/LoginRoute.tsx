import { Eye, EyeOff, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";

import { useAuth } from "../auth";
import { brandConfig } from "../branding/brandConfig";
import { useTheme } from "../theme/useTheme";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Field,
  IconButton,
  Input,
  Select,
  Stack,
} from "../ui";

interface LoginLocationState {
  from?: string;
}

function destinationFromState(state: unknown): string {
  if (!state || typeof state !== "object" || !("from" in state)) return "/mission-control";
  const destination = (state as LoginLocationState).from;
  return destination?.startsWith("/") && destination !== "/login" ? destination : "/mission-control";
}

export function LoginRoute() {
  const { preference, setPreference } = useTheme();
  const { signIn, status } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (status === "authenticated") {
    return <Navigate to={destinationFromState(location.state)} replace />;
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await signIn({ email, password });
      await navigate(destinationFromState(location.state), { replace: true });
    } catch {
      setError("The email or password is incorrect. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="grid min-h-screen place-items-center bg-app-background px-ui-4 py-ui-8 text-content">
      <div className="w-full max-w-[var(--content-compact)]">
        <Stack space="large">
          <div className="flex items-center justify-between gap-ui-4">
            <div className="flex items-center gap-ui-3">
              <div aria-hidden="true" className="grid size-12 place-items-center rounded-lg bg-action-primary text-content-inverse">
                <ShieldCheck />
              </div>
              <div>
                <p className="text-heading-s">{brandConfig.productName}</p>
                <p className="text-caption text-content-muted">Secure enterprise access</p>
              </div>
            </div>
            <Select
              aria-label="Theme preference"
              value={preference}
              onChange={(event) => setPreference(event.target.value as "light" | "dark" | "system")}
              className="w-auto min-w-24"
            >
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </Select>
          </div>

          <Card elevation="medium">
            <CardHeader>
              <CardTitle className="text-heading-m">Sign in</CardTitle>
              <CardDescription>Use your ACP Enterprise administrator credentials.</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={submit} noValidate>
                <Stack space="large">
                  {error && <Alert variant="danger" announcement="assertive">{error}</Alert>}
                  <Field label="Email address" controlId="login-email" required>
                    <Input
                      id="login-email"
                      name="email"
                      type="email"
                      autoComplete="username"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      required
                      disabled={submitting}
                    />
                  </Field>
                  <Field label="Password" controlId="login-password" required>
                    <div className="relative">
                      <Input
                        id="login-password"
                        name="password"
                        type={passwordVisible ? "text" : "password"}
                        autoComplete="current-password"
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                        required
                        disabled={submitting}
                        className="pr-ui-12"
                      />
                      <IconButton
                        icon={passwordVisible ? <EyeOff /> : <Eye />}
                        label={passwordVisible ? "Hide password" : "Show password"}
                        size="small"
                        variant="ghost"
                        className="absolute right-ui-1 top-1/2 -translate-y-1/2"
                        onClick={() => setPasswordVisible((visible) => !visible)}
                        disabled={submitting}
                      />
                    </div>
                  </Field>
                  <Button type="submit" fullWidth loading={submitting} loadingLabel="Signing in">
                    Sign in
                  </Button>
                </Stack>
              </form>
            </CardContent>
          </Card>
        </Stack>
      </div>
    </main>
  );
}
