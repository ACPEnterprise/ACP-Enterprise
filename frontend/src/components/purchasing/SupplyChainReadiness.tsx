import { useState, type FormEvent } from "react";
import type { SupplyChainPolicy, SupplyChainPolicyWrite } from "../../types/purchasing";
import { Alert, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Select } from "../../ui";

const required = ["matching_tolerance", "receiving", "reorder", "valuation", "receipt_accrual", "approval"] as const;

interface Props { policies: readonly SupplyChainPolicy[]; branches: readonly { id: string; name: string }[]; canManage: boolean; pending: boolean; onSave: (input: SupplyChainPolicyWrite) => Promise<unknown>; }

export function SupplyChainReadiness({ policies, branches, canManage, pending, onSave }: Props) {
  const [form, setForm] = useState({ branch_id: "", policy_type: "matching_tolerance", status: "unconfigured" as SupplyChainPolicy["status"], configuration: "{}", readiness_reason: "Company policy is not configured." });
  const [error, setError] = useState<string | null>(null);
  const submit = async (event: FormEvent) => { event.preventDefault(); setError(null); try { const existing = policies.find((item) => item.branch_id === form.branch_id && item.policy_type === form.policy_type); const configuration = JSON.parse(form.configuration) as Record<string, unknown>; await onSave({ ...form, configuration, expected_version: existing?.version ?? null, idempotency_key: crypto.randomUUID() }); } catch { setError("Policy readiness was not saved. Use valid JSON and refresh authoritative policy state."); } };
  return <Card><CardHeader><CardTitle>Supply Chain configuration readiness</CardTitle><CardDescription>Unknown Company policy remains explicitly unconfigured; quantity operations continue without inventing Finance choices.</CardDescription></CardHeader><CardContent className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
    {required.map((type) => { const policy = policies.find((item) => item.policy_type === type); return <div key={type} className="rounded-md border border-stroke p-3"><div className="flex items-center justify-between gap-2"><span className="font-semibold">{type.replaceAll("_", " ")}</span><Badge>{policy?.status ?? "unconfigured"}</Badge></div><p className="mt-1 text-sm text-content-muted">{policy?.readiness_reason ?? "No authoritative Company policy has been configured."}</p></div>; })}
    {required.every((type) => !policies.some((item) => item.policy_type === type && item.status === "active")) && <Alert>Production policy values are intentionally not assumed.</Alert>}
    {canManage && <form className="col-span-full grid gap-2 rounded-md border border-stroke p-3 md:grid-cols-3" onSubmit={(event) => void submit(event)}>
      <Select aria-label="Policy Branch" required value={form.branch_id} onChange={(event) => setForm({ ...form, branch_id: event.target.value })}><option value="">Branch</option>{branches.map((branch) => <option value={branch.id} key={branch.id}>{branch.name}</option>)}</Select>
      <Select aria-label="Policy type" value={form.policy_type} onChange={(event) => setForm({ ...form, policy_type: event.target.value })}>{required.map((type) => <option value={type} key={type}>{type.replaceAll("_", " ")}</option>)}</Select>
      <Select aria-label="Policy readiness status" value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as SupplyChainPolicy["status"], configuration: event.target.value === "unconfigured" ? "{}" : form.configuration })}><option value="unconfigured">Unconfigured</option><option value="draft">Draft</option><option value="active">Active</option><option value="inactive">Inactive</option></Select>
      <Input aria-label="Policy configuration JSON" value={form.configuration} onChange={(event) => setForm({ ...form, configuration: event.target.value })} />
      <Input aria-label="Policy readiness reason" value={form.readiness_reason} onChange={(event) => setForm({ ...form, readiness_reason: event.target.value })} required />
      <Button type="submit" loading={pending}>Save readiness</Button>
      {error && <Alert variant="danger">{error}</Alert>}
    </form>}
  </CardContent></Card>;
}
