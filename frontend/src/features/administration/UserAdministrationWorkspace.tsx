import { useEffect, useState } from "react";

import { Alert, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Spinner } from "../../ui";
import { createOnboarding, getOnboardingOptions, listOnboarding, reissueOnboarding, revokeOnboarding, type OnboardingOptions, type OnboardingRecord } from "./api";

export function UserAdministrationWorkspace() {
  const [records, setRecords] = useState<OnboardingRecord[] | null>(null);
  const [options, setOptions] = useState<OnboardingOptions | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [form, setForm] = useState({ email: "", first: "", last: "", branch: "", role: "", employee: false });

  const refresh = async () => {
    try {
      const [nextRecords, nextOptions] = await Promise.all([listOnboarding(), getOnboardingOptions()]);
      setRecords(nextRecords);
      setOptions(nextOptions);
      setForm((value) => ({ ...value, branch: value.branch || nextOptions.branches[0]?.id || "", role: value.role || nextOptions.roles[0]?.id || "" }));
    } catch { setError("User Administration could not be loaded safely."); }
  };
  useEffect(() => {
    let active = true;
    void Promise.all([listOnboarding(), getOnboardingOptions()])
      .then(([nextRecords, nextOptions]) => {
        if (!active) return;
        setRecords(nextRecords);
        setOptions(nextOptions);
        setForm((value) => ({ ...value, branch: nextOptions.branches[0]?.id || "", role: nextOptions.roles[0]?.id || "" }));
      })
      .catch(() => { if (active) setError("User Administration could not be loaded safely."); });
    return () => { active = false; };
  }, []);

  if (!records || !options) return error ? <Alert variant="danger">{error}</Alert> : <Spinner label="Loading User Administration" />;
  const submit = async () => {
    setPending(true); setError(null);
    try {
      const display = `${form.first.trim()} ${form.last.trim()}`;
      await createOnboarding({
        request_key: crypto.randomUUID(), branch_id: form.branch, first_name: form.first,
        last_name: form.last, display_name: display, create_employee: form.employee,
        ...(form.employee ? { employee_type: "employee" as const, employee_number_prefix: "EMP-", employee_number_width: 4 } : {}),
        role_ids: form.role ? [form.role] : [], login_email: form.email,
      });
      setForm((value) => ({ ...value, email: "", first: "", last: "" }));
      await refresh();
    } catch { setError("The invitation was not accepted. Verify identity, Branch, role, and current authority."); }
    finally { setPending(false); }
  };
  const action = async (id: string, kind: "revoke" | "reissue") => {
    setPending(true); setError(null);
    try { await (kind === "revoke" ? revokeOnboarding(id) : reissueOnboarding(id)); await refresh(); }
    catch { setError("The invitation action conflicted with current authority."); }
    finally { setPending(false); }
  };

  return <Card><CardHeader><CardTitle>User Administration</CardTitle><CardDescription>Invite a Company identity with explicit Branch and role authority. Passwords remain private to the invited user.</CardDescription></CardHeader>
    <CardContent className="space-y-ui-4">
      {error && <Alert variant="danger" announcement="assertive">{error}</Alert>}
      <div className="grid gap-ui-3 sm:grid-cols-2">
        <Input aria-label="Login email" placeholder="Login email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <Input aria-label="First name" placeholder="First name" value={form.first} onChange={(e) => setForm({ ...form, first: e.target.value })} />
        <Input aria-label="Last name" placeholder="Last name" value={form.last} onChange={(e) => setForm({ ...form, last: e.target.value })} />
        <label className="text-body-s">Branch<select className="mt-ui-1 w-full rounded-md border p-ui-2" value={form.branch} onChange={(e) => setForm({ ...form, branch: e.target.value })}>{options.branches.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label className="text-body-s">Role<select className="mt-ui-1 w-full rounded-md border p-ui-2" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>{options.roles.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label className="flex items-center gap-ui-2 text-body-s"><input type="checkbox" checked={form.employee} onChange={(e) => setForm({ ...form, employee: e.target.checked })} />Link a new Employee record</label>
      </div>
      <Button loading={pending} disabled={!form.email || !form.first || !form.last || !form.branch || !form.role} onClick={() => void submit()}>Send invitation</Button>
      <div className="space-y-ui-2">{records.length === 0 && <p className="text-content-muted">No onboarding records yet.</p>}{records.map((record) => <div key={record.id} className="flex flex-wrap items-center justify-between gap-ui-2 rounded-md border p-ui-3"><div><span>{record.masked_login}</span> <Badge variant={record.status === "activated" ? "success" : record.status === "revoked" ? "neutral" : "warning"}>{record.status}</Badge><p className="text-body-xs text-content-muted">{record.employee_id ? "Employee linked" : "Identity only"}</p></div>{record.status === "invited" && <div className="flex gap-ui-2"><Button variant="outline" disabled={pending} onClick={() => void action(record.id, "reissue")}>Reissue</Button><Button variant="outline" disabled={pending} onClick={() => void action(record.id, "revoke")}>Revoke</Button></div>}</div>)}</div>
    </CardContent></Card>;
}
