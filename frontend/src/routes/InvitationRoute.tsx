import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { activateOnboarding } from "../features/administration/api";
import { Alert, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Field, Input } from "../ui";

function invitationToken(): string {
  const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  return fragment.get("token") ?? "";
}

export function InvitationRoute() {
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const token = invitationToken();
    if (!token || password !== confirmation) {
      setError("The invitation or password confirmation is invalid."); return;
    }
    setPending(true); setError(null);
    try {
      await activateOnboarding(token, password);
      window.history.replaceState(null, "", "/invitation");
      await navigate("/login", { replace: true });
    } catch { setError("This invitation is invalid, expired, revoked, or already used."); }
    finally { setPending(false); }
  };
  return <main className="grid min-h-screen place-items-center bg-app-background p-ui-4"><Card className="w-full max-w-lg"><CardHeader><CardTitle>Accept ACP invitation</CardTitle><CardDescription>Establish your private credential. Administrators cannot retrieve it.</CardDescription></CardHeader><CardContent><form className="space-y-ui-4" onSubmit={(event) => void submit(event)}>{error && <Alert variant="danger" announcement="assertive">{error}</Alert>}<Field label="Password" controlId="invite-password" required><Input id="invite-password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field><Field label="Confirm password" controlId="invite-confirm" required><Input id="invite-confirm" type="password" autoComplete="new-password" value={confirmation} onChange={(e) => setConfirmation(e.target.value)} /></Field><Button type="submit" loading={pending}>Activate account</Button></form></CardContent></Card></main>;
}
