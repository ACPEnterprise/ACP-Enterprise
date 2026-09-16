import { useMemo, useState } from "react";
import { Link } from "react-router";

import { useAuth } from "../../auth";
import { useRealRosterReadiness, useWorkforceDirectory } from "../../hooks/useWorkforce";
import { Alert, Badge, Button, Card, Input, Spinner } from "../../ui";
import { ReadinessBlockers } from "./ReadinessBlockers";

const profileDescriptions: Record<string, string> = {
  ADMIN: "Company Administrator. Owner hard gates remain separately enforced.",
  OFFICE_MANAGER: "Normal office operations, Workforce and time review; no Payroll, money movement, or permission administration.",
  OFFICE_STAFF: "Customer, Job, Scheduling and sanctioned office workflows; no administrator authority.",
  FIELD_TECH: "Technician plus ACP Employee Mobile. Assigned work and own time only; no office, Accounting, or Payroll authority.",
};

const label = (value: string) => value.replaceAll("_", " ");
const formatTime = (value: string | null) => value ? new Date(value).toLocaleString() : "Not recorded";

export function RealRosterActivationConsole() {
  const { activeCompany, permissionCodes = [] } = useAuth();
  const hasManagePermission = permissionCodes.includes("COMPANY_WORKFORCE_CAPABILITY_MANAGE");
  const roster = useRealRosterReadiness(hasManagePermission);
  const canManage = hasManagePermission || roster.canBind;
  const directory = useWorkforceDirectory();
  const [selections, setSelections] = useState<Record<string, string>>({});
  const [sourceSelections, setSourceSelections] = useState<Record<string, string>>({});
  const [deferred, setDeferred] = useState<Set<string>>(new Set());
  const [fieldWindowStart, setFieldWindowStart] = useState("");
  const [fieldWindowEnd, setFieldWindowEnd] = useState("");
  const [readinessReason, setReadinessReason] = useState("");
  const [filter, setFilter] = useState<"ALL" | "NEEDS_ACTION" | "FIELD_TECH">("ALL");
  const mainBranchId = activeCompany?.branches?.find((branch) => branch.code === "MAIN")?.id ?? "";
  const items = useMemo(() => (roster.query.data?.items ?? []).filter((person) =>
    filter === "ALL" || (filter === "FIELD_TECH" ? person.field_tech : person.blockers.length > 0)
  ), [filter, roster.query.data?.items]);

  if (roster.query.isLoading) return <Card className="p-6"><Spinner label="Loading real employee activation" /></Card>;
  if (roster.query.isError) return <Alert variant="danger">Real employee activation evidence is unavailable. No identity or readiness state was inferred.</Alert>;

  return <Card className="p-4 sm:p-6">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h3 className="text-lg font-semibold">Real employee activation</h3><p className="mt-1 text-sm text-content-muted">Review all eight owner-confirmed people. Every binding requires one exact Employee selection; ACP never matches by name or email.</p></div>
      <Link className="rounded-lg bg-action-primary px-4 py-2 font-semibold text-white" to="/administration/identity-onboarding">Onboard missing employee</Link>
    </div>
    <div className="mt-4 grid gap-2 sm:grid-cols-4">
      <div className="rounded-lg bg-surface-subtle p-3"><p className="text-xs text-content-muted">Roster</p><strong>{roster.query.data?.total ?? 8}</strong></div>
      <div className="rounded-lg bg-surface-subtle p-3"><p className="text-xs text-content-muted">Identity certified</p><strong>{roster.query.data?.bound ?? 0}</strong></div>
      <div className="rounded-lg bg-surface-subtle p-3"><p className="text-xs text-content-muted">Field technicians</p><strong>{roster.query.data?.field_tech_total ?? 5}</strong></div>
      <div className="rounded-lg bg-surface-subtle p-3"><p className="text-xs text-content-muted">Technician capability ready</p><strong>{roster.query.data?.field_tech_capability_ready ?? 0}</strong></div>
    </div>
    <div className="mt-4 flex flex-wrap gap-2" aria-label="Roster filters">
      {(["ALL", "NEEDS_ACTION", "FIELD_TECH"] as const).map((value) => <Button key={value} variant={filter === value ? "primary" : "outline"} onClick={() => setFilter(value)}>{label(value)}</Button>)}
    </div>
    {canManage && <section className="mt-4 rounded-lg border border-stroke p-3" aria-label="Bounded MAIN Branch readiness">
      <h4 className="font-semibold">Bounded MAIN Branch readiness</h4>
      <p className="mt-1 text-xs text-content-muted">Creates an audited availability window and technician capability. It expires at the selected end time and never assigns work.</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-3"><label className="text-sm">Start<Input className="mt-1" type="datetime-local" value={fieldWindowStart} onChange={(event) => setFieldWindowStart(event.target.value)} /></label><label className="text-sm">End<Input className="mt-1" type="datetime-local" value={fieldWindowEnd} onChange={(event) => setFieldWindowEnd(event.target.value)} /></label><label className="text-sm">Owner reason<Input className="mt-1" value={readinessReason} onChange={(event) => setReadinessReason(event.target.value)} placeholder="Confirmed operating window" /></label></div>
    </section>}
    <div className="mt-4 space-y-3">{items.map((person) => {
      const boundIds = new Set(roster.query.data?.items.flatMap((item) => item.employee_id ? [item.employee_id] : []) ?? []);
      const onboardingProfile = person.operating_role === "FIELD_TECH" ? "FIELD_TECH" : person.operating_role;
      return <article key={person.roster_key} className="rounded-xl border border-stroke p-4">
        <div className="flex flex-wrap items-start justify-between gap-2"><div><h4 className="font-semibold">{person.display_name}</h4><p className="text-sm text-content-muted">Source: owner-confirmed roster · {label(person.operating_role)}</p></div><Badge variant={person.blockers.length === 0 ? "success" : "neutral"}>{person.blockers.length === 0 ? "Ready" : `${person.blockers.length} actions`}</Badge></div>
        <p className="mt-2 rounded-lg bg-surface-subtle p-2 text-xs text-content-muted">{profileDescriptions[person.operating_role]}</p>
        {person.employee_id ? <>
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div><dt className="text-content-muted">ACP Employee</dt><dd>{person.employee_display_name}</dd></div><div><dt className="text-content-muted">Account</dt><dd>{label(person.user_state)} · {label(person.credential_state)}</dd></div><div><dt className="text-content-muted">Membership / MAIN</dt><dd>{label(person.membership_state)} · {label(person.branch_state)}</dd></div><div><dt className="text-content-muted">Role</dt><dd>{label(person.role_state)}</dd></div>
            <div><dt className="text-content-muted">Workforce</dt><dd>{label(person.workforce_profile_state)}</dd></div><div><dt className="text-content-muted">Mobile</dt><dd>{label(person.mobile_state)}</dd></div><div><dt className="text-content-muted">Dispatch handoff</dt><dd>{label(person.dispatch_state)}</dd></div><div><dt className="text-content-muted">Payroll handoff</dt><dd>{label(person.payroll_linkage_state)}</dd></div>
          </dl>
          {person.field_tech && <div className="mt-3 rounded-lg border border-stroke p-3 text-sm"><p><strong>Technician capability:</strong> {label(person.technician_capability_state)}</p><p><strong>Readiness window:</strong> {formatTime(person.readiness_window_start_at)} – {formatTime(person.readiness_window_end_at)}</p><p><strong>Expiration:</strong> {formatTime(person.readiness_window_end_at)}</p><p><strong>Evidence:</strong> {person.readiness_source ? label(person.readiness_source) : "Explicit owner window required"}</p>{canManage && <Button className="mt-2" variant="outline" disabled={!mainBranchId || !fieldWindowStart || !fieldWindowEnd || readinessReason.trim().length < 3 || roster.prepareFieldReadiness.isPending} onClick={() => roster.prepareFieldReadiness.mutate({employeeId: person.employee_id as string, branchId: mainBranchId, windowStartAt: new Date(fieldWindowStart).toISOString(), windowEndAt: new Date(fieldWindowEnd).toISOString(), reason: readinessReason})}>Record this employee’s bounded readiness</Button>}</div>}
          <div className="mt-3 flex flex-wrap gap-2"><Link className="text-sm font-semibold text-action-primary" to={`/workforce?employee=${person.employee_id}`}>Open access, capabilities and history</Link><Link className="text-sm font-semibold text-action-primary" to="/payroll">Review Payroll blockers</Link></div>
        </> : <div className="mt-3 rounded-lg border border-stroke p-3">
          <p className="text-sm font-semibold">Exact identity certification</p><p className="mt-1 text-xs text-content-muted">Select only an Employee whose authoritative identity the owner has independently verified. The list is not a match recommendation.</p>
          {deferred.has(person.roster_key) ? <Alert variant="warning">Deferred in this browser review only. No identity decision was persisted.</Alert> : canManage && <div className="mt-2 flex flex-wrap gap-2"><select aria-label={`Exact ACP Employee for ${person.display_name}`} className="min-h-11 min-w-64 rounded-md border border-stroke bg-surface px-3" value={selections[person.roster_key] ?? ""} onChange={(event) => setSelections((current) => ({...current, [person.roster_key]: event.target.value}))}><option value="">Select exact verified Employee</option>{(directory.data ?? []).filter((employee) => !boundIds.has(employee.employee_id)).map((employee) => <option key={employee.employee_id} value={employee.employee_id}>{employee.display_name} · {employee.employee_number}</option>)}</select><Button disabled={!selections[person.roster_key] || roster.bind.isPending} onClick={() => roster.bind.mutate({rosterKey: person.roster_key, employeeId: selections[person.roster_key]})}>Confirm exact identity</Button><Button variant="outline" onClick={() => setSelections((current) => ({...current, [person.roster_key]: ""}))}>Not same person</Button><Button variant="outline" onClick={() => setDeferred((current) => new Set(current).add(person.roster_key))}>Defer</Button></div>}
          <Link className="mt-3 inline-block text-sm font-semibold text-action-primary" to={`/administration/identity-onboarding?name=${encodeURIComponent(person.display_name)}&profile=${onboardingProfile}&branch=MAIN`}>Create/onboard ACP Employee</Link>
        </div>}
        {person.blockers.length > 0 && <ReadinessBlockers blockers={person.blockers} />}
      </article>;
    })}</div>
    <section className="mt-4 rounded-lg border border-stroke p-3" aria-label="HCP Employee certification evidence">
      <h4 className="font-semibold">Source Employee certification</h4>
      <p className="mt-1 text-xs text-content-muted">Exact HCP identifiers and persisted ACP targets only. ACP never matches these records by name or email.</p>
      <p className="mt-2 text-sm text-content-muted">{roster.query.data?.source_evidence_total ?? 0} sealed source identities · {roster.query.data?.source_only_total ?? 0} source-only · {roster.query.data?.certification_required_total ?? 0} certification actions remaining</p>
      <div className="mt-3 space-y-2">{roster.query.data?.source_evidence?.map((source) => {
        const sourceKey = `${source.source_system}-${source.source_employee_id}`;
        const unboundRoster = roster.query.data?.items.filter((item) => item.employee_id === null) ?? [];
        return <div className="rounded-md bg-surface-subtle p-2 text-xs" key={sourceKey}>
          <div className="flex flex-wrap justify-between gap-2"><span className="font-medium">{source.source_system} · {source.source_employee_id}</span><Badge variant={source.certification_state === "ACP_EMPLOYEE_BOUND" ? "success" : "neutral"}>{label(source.certification_state)}</Badge></div>
          <p className="mt-1 text-content-muted">{label(source.source_disposition)} · evidence v{source.evidence_version}{source.roster_key ? ` · ${label(source.roster_key)}` : ""}</p>
          {source.certification_state === "OWNER_CERTIFICATION_REQUIRED" && source.acp_employee_id && canManage && <div className="mt-2 flex flex-wrap gap-2"><select aria-label={`Certify ${source.source_system} ${source.source_employee_id}`} className="min-h-10 min-w-64 rounded-md border border-stroke bg-surface px-2" value={sourceSelections[sourceKey] ?? ""} onChange={(event) => setSourceSelections((current) => ({...current, [sourceKey]: event.target.value}))}><option value="">Select owner-confirmed roster identity</option>{unboundRoster.map((person) => <option key={person.roster_key} value={person.roster_key}>{person.display_name} · {label(person.operating_role)}</option>)}</select><Button variant="outline" disabled={!sourceSelections[sourceKey] || roster.bind.isPending} onClick={() => roster.bind.mutate({rosterKey: sourceSelections[sourceKey], employeeId: source.acp_employee_id as string})}>Confirm exact source target</Button></div>}
          {source.certification_state === "SOURCE_ONLY" && permissionCodes.includes("COMPANY_IDENTITY_ONBOARDING_MANAGE") && <Link className="mt-2 inline-block font-semibold text-action-primary" to="/administration/identity-onboarding">Create / onboard after owner certification</Link>}
          {source.certification_state === "NOT_EMPLOYEE" && <p className="mt-2 font-medium text-content-muted">Legacy only — excluded from Employee onboarding.</p>}
        </div>;
      })}</div>
    </section>
  </Card>;
}
