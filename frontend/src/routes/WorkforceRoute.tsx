import { useMemo, useState } from "react";
import { Award, Languages, Search, ShieldCheck, UserRoundCheck, UsersRound } from "lucide-react";
import { Link } from "react-router";

import { getOperatorApiError } from "../api/errors";
import type { EmployeePermissionExplanation } from "../api/workforce";
import { useAuth } from "../auth";
import { useRoles } from "../features/administration/hooks";
import { useEmployeeAccessMutation, useEmployeeAdministration, useWorkforceDirectory, useWorkforceEligibility, useWorkforceEmployee } from "../hooks/useWorkforce";
import { Alert, Badge, Card, Input, Spinner } from "../ui";

function Readiness({ state }: { state: "READY" | "BLOCKED" | "INSUFFICIENT_EVIDENCE" }) {
  return <Badge variant={state === "READY" ? "success" : state === "BLOCKED" ? "danger" : "neutral"}>{state.replaceAll("_", " ")}</Badge>;
}

export function WorkforceRoute() {
  const { activeCompany, permissionCodes = [] } = useAuth();
  const canAdministerEmployees = permissionCodes.includes("COMPANY_WORKFORCE_MANAGE") && permissionCodes.includes("COMPANY_MEMBERSHIP_READ") && permissionCodes.includes("COMPANY_ROLE_READ");
  const directory = useWorkforceDirectory();
  const [selected, setSelected] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [branchFilter, setBranchFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [readinessFilter, setReadinessFilter] = useState("");
  const detail = useWorkforceEmployee(selected);
  const administration = useEmployeeAdministration(selected, canAdministerEmployees);
  const accessMutation = useEmployeeAccessMutation(selected);
  const canManageMembership = permissionCodes.includes("COMPANY_MEMBERSHIP_MANAGE");
  const canManageBranches = permissionCodes.includes("COMPANY_BRANCH_ACCESS_MANAGE");
  const canManageRoles = permissionCodes.includes("COMPANY_ROLE_MANAGE");
  const roles = useRoles(canManageRoles);
  const [selectedBranchGrant, setSelectedBranchGrant] = useState("");
  const [selectedRoleGrant, setSelectedRoleGrant] = useState("");
  const eligibility = useWorkforceEligibility();
  const [branchId, setBranchId] = useState("");
  const [windowStart, setWindowStart] = useState("");
  const [windowEnd, setWindowEnd] = useState("");
  const [capabilities, setCapabilities] = useState("");
  const [languages, setLanguages] = useState("");
  const administrationPermissions = administration.data?.permissions;
  const permissionAreas = useMemo(() => {
    const groups: Record<string, EmployeePermissionExplanation[]> = {};
    for (const permission of administrationPermissions ?? []) {
      (groups[permission.business_area] ??= []).push(permission);
    }
    return groups;
  }, [administrationPermissions]);
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (directory.data ?? []).filter((item) =>
      (!query || [item.display_name, item.employee_number, item.job_title ?? "", ...item.capability_codes, ...item.language_codes].some((value) => value.toLowerCase().includes(query)))
      && (!branchFilter || item.home_branch_id === branchFilter)
      && (!statusFilter || item.employee_status === statusFilter)
      && (!readinessFilter || item.readiness_state === readinessFilter)
    );
  }, [branchFilter, directory.data, readinessFilter, search, statusFilter]);
  const morningReview = useMemo(() => ({
    total: directory.data?.length ?? 0,
    inactive: (directory.data ?? []).filter((item) => item.employee_status !== "active").length,
    missingProfile: (directory.data ?? []).filter((item) => !item.profile_id).length,
    needsAttention: (directory.data ?? []).filter((item) => item.readiness_state !== "READY").length,
  }), [directory.data]);

  return <div className="space-y-6">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm font-medium text-action-primary">Workforce operations</p><h2 className="mt-1 text-2xl font-bold sm:text-3xl">Employee readiness</h2><p className="mt-2 text-content-muted">Operational identity, capability, credential, language, and Branch evidence. Payroll data is excluded.</p></div>{permissionCodes.includes("COMPANY_IDENTITY_ONBOARDING_MANAGE") && <Link className="rounded-lg bg-action-primary px-4 py-2 font-semibold text-white" to="/administration/identity-onboarding">Add Employee</Link>}</header>
    <Card className="p-4 sm:p-6">
      <h3 className="text-lg font-semibold">Assignment eligibility</h3>
      <p className="mt-1 text-sm text-content-muted">Evaluate explicit Branch, availability, capability, language, restriction, and assignment evidence. This does not assign work.</p>
      <form className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5" onSubmit={(event) => { event.preventDefault(); eligibility.mutate({ branch_id: branchId, window_start_at: new Date(windowStart).toISOString(), window_end_at: new Date(windowEnd).toISOString(), required_capability_codes: capabilities.split(",").map((value) => value.trim()).filter(Boolean), required_language_codes: languages.split(",").map((value) => value.trim()).filter(Boolean) }); }}>
        <label className="text-sm"><span className="mb-1 block font-medium">Branch ID</span><Input required value={branchId} onChange={(event) => setBranchId(event.target.value)} placeholder="Authorized Branch UUID"/></label>
        <label className="text-sm"><span className="mb-1 block font-medium">Window start</span><Input required type="datetime-local" value={windowStart} onChange={(event) => setWindowStart(event.target.value)}/></label>
        <label className="text-sm"><span className="mb-1 block font-medium">Window end</span><Input required type="datetime-local" value={windowEnd} onChange={(event) => setWindowEnd(event.target.value)}/></label>
        <label className="text-sm"><span className="mb-1 block font-medium">Capabilities</span><Input value={capabilities} onChange={(event) => setCapabilities(event.target.value)} placeholder="plumbing, technician"/></label>
        <label className="text-sm"><span className="mb-1 block font-medium">Languages</span><Input value={languages} onChange={(event) => setLanguages(event.target.value)} placeholder="en, es"/></label>
        <button type="submit" disabled={eligibility.isPending} className="min-h-10 rounded-lg bg-action-primary px-4 font-semibold text-white disabled:opacity-50 md:col-span-2 xl:col-span-1">{eligibility.isPending ? "Evaluating…" : "Evaluate"}</button>
      </form>
      {eligibility.isError && <div className="mt-4"><Alert variant="danger" title="Eligibility unavailable">The evidence could not be evaluated. Verify the authorized Branch and time window.</Alert></div>}
      {eligibility.data && <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-3">{eligibility.data.map((item) => <div key={item.employee_id} className="rounded-xl border border-stroke p-3"><div className="flex items-start justify-between gap-2"><div><strong>{item.display_name}</strong><p className="text-xs text-content-muted">{item.employee_number}</p></div><Badge variant={item.eligible ? "success" : "neutral"}>{item.decision}</Badge></div><p className="mt-2 text-xs text-content-muted">{item.reasons.length ? item.reasons.join(" · ") : "No blockers"} · {item.availability_confidence}</p></div>)}</div>}
    </Card>
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Owner morning Employee review">
      {[['Authorized Employees', morningReview.total], ['Inactive identities', morningReview.inactive], ['Missing Workforce profile', morningReview.missingProfile], ['Readiness needs attention', morningReview.needsAttention]].map(([label, value]) => <Card key={String(label)} className="p-4"><p className="text-sm text-content-muted">{label}</p><p className="mt-1 text-2xl font-bold">{value}</p></Card>)}
    </section>
    <div className="grid gap-6 xl:grid-cols-[minmax(20rem,0.85fr)_minmax(0,1.4fr)]">
      <Card className="min-w-0 overflow-hidden">
        <div className="space-y-3 border-b border-stroke p-4"><label className="relative block"><span className="sr-only">Search workforce</span><Search size={17} className="absolute left-3 top-3 text-content-muted"/><Input className="pl-10" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name, number, role, capability, language"/></label><div className="grid gap-2 sm:grid-cols-3"><label className="text-xs text-content-muted">Branch<select aria-label="Filter by Branch" className="mt-1 min-h-10 w-full rounded-lg border border-stroke bg-surface px-2 text-content" value={branchFilter} onChange={(event) => setBranchFilter(event.target.value)}><option value="">All authorized</option>{(activeCompany?.branches ?? []).map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}</select></label><label className="text-xs text-content-muted">Employee status<select aria-label="Filter by Employee status" className="mt-1 min-h-10 w-full rounded-lg border border-stroke bg-surface px-2 text-content" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">All</option><option value="active">Active</option><option value="inactive">Inactive</option><option value="archived">Archived</option></select></label><label className="text-xs text-content-muted">Readiness<select aria-label="Filter by readiness" className="mt-1 min-h-10 w-full rounded-lg border border-stroke bg-surface px-2 text-content" value={readinessFilter} onChange={(event) => setReadinessFilter(event.target.value)}><option value="">All</option><option value="READY">Ready</option><option value="BLOCKED">Blocked</option><option value="INSUFFICIENT_EVIDENCE">Insufficient evidence</option></select></label></div></div>
        {directory.isLoading && <div className="p-8"><Spinner label="Loading workforce"/></div>}
        {directory.isError && (() => { const error = getOperatorApiError(directory.error, "workforce directory"); return <div className="p-4"><Alert variant="danger" title={error.title}>{error.message}</Alert></div>; })()}
        <div className="divide-y divide-stroke">
          {filtered.map((employee) => <button key={employee.employee_id} type="button" onClick={() => setSelected(employee.employee_id)} className="flex min-h-16 w-full items-center justify-between gap-3 p-4 text-left hover:bg-surface-subtle focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus"><span className="min-w-0"><span className="block truncate font-semibold">{employee.display_name}</span><span className="block truncate text-xs text-content-muted">{employee.employee_number} · {employee.job_title ?? employee.employee_type}</span></span><Readiness state={employee.readiness_state}/></button>)}
        </div>
        {directory.isSuccess && filtered.length === 0 && <p className="p-5 text-sm text-content-muted">No authorized Employee profile matches this search.</p>}
      </Card>
      {!selected ? <Card className="flex min-h-72 items-center justify-center p-8 text-center"><div><UsersRound className="mx-auto text-action-primary"/><h3 className="mt-3 text-xl font-semibold">Select an Employee</h3><p className="mt-2 text-sm text-content-muted">Inspect explicit readiness evidence without exposing Payroll or compensation data.</p></div></Card> : detail.isLoading ? <Card className="p-8"><Spinner label="Loading Employee profile"/></Card> : detail.isError || !detail.data ? <Alert variant="danger" title="Employee profile unavailable">The profile could not be loaded within the current Company and Branch authority.</Alert> : <Card className="min-w-0 p-4 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm text-action-primary">{detail.data.employee_number}</p><h3 className="mt-1 text-2xl font-bold">{detail.data.display_name}</h3><p className="mt-1 text-content-muted">{detail.data.job_title ?? detail.data.employee_type}</p></div><Readiness state={detail.data.readiness_state}/></div>
        {detail.data.readiness_blockers.length > 0 && <section className="mt-5 rounded-xl border border-status-warning/40 bg-status-warning/5 p-4"><h4 className="font-semibold">Assignment readiness blockers</h4><ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-content-muted">{detail.data.readiness_blockers.map((item) => <li key={item}>{item.replaceAll("_", " ")}</li>)}</ul></section>}
        {canAdministerEmployees && administration.isLoading && <div className="mt-5"><Spinner label="Loading Employee administration"/></div>}
        {canAdministerEmployees && administration.isError && <div className="mt-5"><Alert variant="danger" title="Employee administration unavailable">Operational Workforce evidence remains visible, but identity and permission readiness could not be loaded.</Alert></div>}
        {administration.data && <section className="mt-5 rounded-xl border border-stroke p-4" aria-labelledby="employee-access-heading">
          <div className="flex flex-wrap items-start justify-between gap-3"><div><h4 id="employee-access-heading" className="font-semibold">Identity, access, and Mobile readiness</h4><p className="mt-1 text-sm text-content-muted">User, Membership, Branch grants, canonical roles, and effective permissions remain distinct authorities.</p></div><Badge variant={administration.data.mobile_readiness === "READY" ? "success" : "warning"}>{administration.data.mobile_readiness.replaceAll("_", " ")}</Badge></div>
          <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <div><dt className="text-content-muted">User</dt><dd className="font-medium">{administration.data.user_status ?? "Not linked"}</dd></div>
            <div><dt className="text-content-muted">Membership</dt><dd className="font-medium">{administration.data.membership_status ?? "Not linked"}</dd></div>
            <div><dt className="text-content-muted">Invitation</dt><dd className="font-medium">{administration.data.onboarding_status ?? "Not prepared"}</dd></div>
            <div><dt className="text-content-muted">Login</dt><dd className="font-medium">{administration.data.masked_login ?? "Unavailable"}</dd></div>
          </dl>
          <div className="mt-4 grid gap-4 lg:grid-cols-2"><div><h5 className="text-sm font-semibold">Roles</h5><div className="mt-2 flex flex-wrap gap-2">{administration.data.role_codes.map((code) => <Badge key={code} variant="neutral">{code.replaceAll("_", " ")}</Badge>)}{administration.data.role_codes.length === 0 && <span className="text-sm text-content-muted">No active role assignment.</span>}</div></div><div><h5 className="text-sm font-semibold">Branch grants</h5><p className="mt-2 break-words text-sm text-content-muted">{administration.data.branch_ids.length ? administration.data.branch_ids.join(", ") : "No explicit Branch grant."}</p></div></div>
          {administration.data.membership_id && (canManageMembership || canManageBranches || canManageRoles) && <div className="mt-4 grid gap-3 rounded-lg bg-surface-subtle p-3 lg:grid-cols-3">
            {canManageMembership && <div><h5 className="text-sm font-semibold">Membership state</h5><button type="button" disabled={accessMutation.isPending} onClick={() => accessMutation.mutate({ type: "membership", membershipId: administration.data.membership_id!, status: administration.data.membership_status === "active" ? "suspended" : "active" })} className="mt-2 rounded-lg border border-stroke px-3 py-2 text-sm font-medium">{administration.data.membership_status === "active" ? "Suspend access" : "Reactivate access"}</button></div>}
            {canManageBranches && <form onSubmit={(event) => { event.preventDefault(); if (selectedBranchGrant) accessMutation.mutate({ type: "branch", membershipId: administration.data.membership_id!, branchId: selectedBranchGrant, enabled: !administration.data.branch_ids.includes(selectedBranchGrant) }); }}><label className="text-sm font-semibold" htmlFor="employee-branch-grant">Branch access</label><select id="employee-branch-grant" className="mt-2 min-h-10 w-full rounded-lg border border-stroke bg-surface px-2" value={selectedBranchGrant} onChange={(event) => setSelectedBranchGrant(event.target.value)}><option value="">Select Branch</option>{(activeCompany?.branches ?? []).map((branch) => <option key={branch.id} value={branch.id}>{branch.name}{administration.data.branch_ids.includes(branch.id) ? " (granted)" : ""}</option>)}</select><button type="submit" disabled={!selectedBranchGrant || accessMutation.isPending} className="mt-2 rounded-lg border border-stroke px-3 py-2 text-sm font-medium">{administration.data.branch_ids.includes(selectedBranchGrant) ? "Remove grant" : "Grant Branch"}</button></form>}
            {canManageRoles && <form onSubmit={(event) => { event.preventDefault(); const role = roles.data?.find((item) => item.id === selectedRoleGrant); if (role) accessMutation.mutate({ type: "role", membershipId: administration.data.membership_id!, roleId: role.id, enabled: !administration.data.role_codes.includes(role.code) }); }}><label className="text-sm font-semibold" htmlFor="employee-role-grant">Role bundle</label><select id="employee-role-grant" className="mt-2 min-h-10 w-full rounded-lg border border-stroke bg-surface px-2" value={selectedRoleGrant} onChange={(event) => setSelectedRoleGrant(event.target.value)}><option value="">Select role</option>{(roles.data ?? []).map((role) => <option key={role.id} value={role.id}>{role.name}{administration.data.role_codes.includes(role.code) ? " (assigned)" : ""}</option>)}</select><button type="submit" disabled={!selectedRoleGrant || accessMutation.isPending} className="mt-2 rounded-lg border border-stroke px-3 py-2 text-sm font-medium">Update role</button></form>}
          </div>}
          {accessMutation.isError && <div className="mt-3"><Alert variant="danger" title="Access change not applied">The change conflicts with current authority or requires a permitted administrator. Refresh and review the Employee state.</Alert></div>}
          {administration.data.mobile_readiness_blockers.length > 0 && <Alert variant="warning" title="Mobile readiness blockers"><ul className="list-disc pl-5">{administration.data.mobile_readiness_blockers.map((item) => <li key={item}>{item.replaceAll("_", " ")}</li>)}</ul></Alert>}
          <div className="mt-5"><h5 className="font-semibold">Effective permission explanation</h5><p className="mt-1 text-sm text-content-muted">Permissions are grouped by business area and derived from active roles. Own-data permissions never authorize another Employee identity.</p><div className="mt-3 grid gap-3 md:grid-cols-2">{Object.entries(permissionAreas).map(([area, items]) => <section key={area} className="rounded-lg bg-surface-subtle p-3"><h6 className="font-semibold">{area}</h6><ul className="mt-2 space-y-2">{items.map((permission) => <li key={permission.code} className="text-sm"><span className="font-medium">{permission.name}</span><span className="block text-xs text-content-muted">{permission.authority.replaceAll("_", " ")} · {permission.branch_scoped ? "Branch scoped" : "Company scoped"} · {permission.role_codes.join(", ")}</span></li>)}</ul></section>)}</div></div>
        </section>}
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <section className="rounded-xl border border-stroke p-4"><h4 className="flex items-center gap-2 font-semibold"><UserRoundCheck size={17}/>Capabilities</h4><div className="mt-3 space-y-2">{detail.data.capabilities.map((item) => <p key={item.code} className="text-sm"><strong>{item.display_name}</strong> · {item.proficiency}</p>)}{detail.data.capabilities.length === 0 && <p className="text-sm text-content-muted">No explicit capability evidence.</p>}</div></section>
          <section className="rounded-xl border border-stroke p-4"><h4 className="flex items-center gap-2 font-semibold"><Languages size={17}/>Languages</h4><div className="mt-3 space-y-2">{detail.data.languages.map((item) => <p key={item.code} className="text-sm"><strong>{item.english_name}</strong> · {item.spoken_proficiency}{item.customer_facing_eligible ? " · customer-facing" : ""}</p>)}{detail.data.languages.length === 0 && <p className="text-sm text-content-muted">No explicit language evidence.</p>}</div></section>
          <section className="rounded-xl border border-stroke p-4 md:col-span-2"><h4 className="flex items-center gap-2 font-semibold"><Award size={17}/>Certifications</h4><div className="mt-3 grid gap-2 md:grid-cols-2">{detail.data.certifications.map((item) => <div key={`${item.code}-${item.credential_reference}`} className="rounded-lg bg-surface-subtle p-3 text-sm"><div className="flex justify-between gap-3"><strong>{item.display_name}</strong><Badge variant="neutral">{item.status}</Badge></div><p className="mt-1 text-xs text-content-muted">Evidence {item.credential_reference}{item.expires_on ? ` · expires ${item.expires_on}` : " · no expiration recorded"}</p></div>)}{detail.data.certifications.length === 0 && <p className="text-sm text-content-muted">No certification evidence.</p>}</div></section>
          <section className="rounded-xl border border-stroke p-4"><h4 className="flex items-center gap-2 font-semibold"><ShieldCheck size={17}/>Branch authority</h4><div className="mt-3 space-y-2">{detail.data.branches.map((item) => <p key={item.branch_id} className="break-all text-sm">{item.branch_id} · {item.status}</p>)}{detail.data.branches.length === 0 && <p className="text-sm text-content-muted">Home Branch only or no explicit eligibility evidence.</p>}</div></section>
          <section className="rounded-xl border border-stroke p-4"><h4 className="font-semibold">Restrictions and equipment</h4><p className="mt-3 text-sm text-content-muted">{detail.data.work_restrictions.length ? detail.data.work_restrictions.join(", ") : "No active work restriction evidence."}</p><p className="mt-2 text-sm text-content-muted">{detail.data.equipment_capabilities.length ? detail.data.equipment_capabilities.map((item) => item.display_name).join(", ") : "No equipment capability evidence."}</p></section>
          <section className="rounded-xl border border-stroke p-4 md:col-span-2"><h4 className="font-semibold">Recorded availability</h4><div className="mt-3 grid gap-2 md:grid-cols-2">{detail.data.availability.map((item) => <div key={`${item.branch_id}-${item.start_at}-${item.end_at}`} className="rounded-lg bg-surface-subtle p-3 text-sm"><div className="flex justify-between gap-3"><strong>{item.status}</strong><span className="text-xs text-content-muted">{item.source}</span></div><p className="mt-1 text-xs text-content-muted">{new Date(item.start_at).toLocaleString()} – {new Date(item.end_at).toLocaleString()}</p></div>)}{detail.data.availability.length === 0 && <p className="text-sm text-content-muted">No configured working-availability evidence.</p>}</div></section>
        </div>
      </Card>}
    </div>
  </div>;
}
