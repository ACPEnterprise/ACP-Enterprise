import axios from "axios";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import {
  getRealRosterOnboardingPreview,
  onboardRealRosterEmployee,
  type RealRosterOnboardingPreview,
} from "../../api/workforce";
import { useAuth } from "../../auth";
import { Alert, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Spinner } from "../../ui";
import {
  getIdentityOnboardingDelivery,
  getCanonicalRoleSyncPlan,
  applyCanonicalRoleSync,
  matchSimpleEmployee,
  onboardSimpleEmployee,
  listRoles,
  reissueIdentityOnboarding,
  revokeIdentityOnboarding,
  type CompanyRole,
  type CanonicalRoleSyncPlan,
  type IdentityOnboardingDeliveryView,
  type IdentityOnboardingView,
} from "./api";

const ONBOARDING_PERMISSION = "COMPANY_IDENTITY_ONBOARDING_MANAGE";
const OPERATING_PROFILES = [
  { label: "ADMIN", roleCodes: [["COMPANY_ADMINISTRATOR", "ADMIN"]] },
  { label: "OFFICE_MANAGER", roleCodes: [["OFFICE_MANAGER"]] },
  { label: "OFFICE_STAFF", roleCodes: [["SERVICE_CSR", "CSR"]] },
  {
    label: "FIELD_TECH",
    roleCodes: [["TECHNICIAN"], ["ACP_EMPLOYEE_MOBILE"]],
  },
  {
    label: "FIELD_MANAGER",
    roleCodes: [["TECHNICIAN"], ["ACP_EMPLOYEE_MOBILE"], ["DISPATCHER"]],
  },
] as const;

function profileDisplayName(profile: string): string {
  return profile === "FIELD_MANAGER" ? "Field Manager" : profile.replaceAll("_", " ");
}

type OperatingProfile = { label: string; roles: CompanyRole[] };
type Preparation =
  | { state: "loading" }
  | { state: "ready"; profiles: OperatingProfile[] }
  | { state: "blocked"; message: string; reconciliation?: CanonicalRoleSyncPlan };

function submissionMessage(error: unknown): string {
  if (axios.isAxiosError(error) && error.response?.status === 403) return "You are not authorized to add employees.";
  if (axios.isAxiosError(error) && error.response?.status === 409) return "This employee conflicts with an existing Company identity. Review the existing Team record before retrying.";
  return "The employee was not invited. Please retry or review the existing Team record.";
}

export function IdentityOnboardingRoute() {
  const [searchParams] = useSearchParams();
  const rosterKey = searchParams.get("roster");
  const { activeCompany, permissionCodes = [] } = useAuth();
  const authorized = permissionCodes.includes(ONBOARDING_PERMISSION);
  const canReconcileProfiles = permissionCodes.includes("COMPANY_PERMISSION_MANAGE");
  const branches = useMemo(() => activeCompany?.branches ?? [], [activeCompany]);
  const requestedBranch = searchParams.get("branch");
  const defaultBranch = branches.find((branch) => branch.code === requestedBranch)?.id ?? activeCompany?.default_branch_id ?? branches.find((branch) => branch.code === "MAIN")?.id ?? branches[0]?.id ?? "";
  const authoritativeName = searchParams.get("name")?.trim() ?? "";
  const nameParts = authoritativeName.split(/\s+/).filter(Boolean);
  const [branchId, setBranchId] = useState(defaultBranch);
  const [firstName, setFirstName] = useState(nameParts.slice(0, -1).join(" "));
  const [lastName, setLastName] = useState(nameParts.at(-1) ?? "");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [profileLabel, setProfileLabel] = useState(searchParams.get("profile") ?? "FIELD_TECH");
  const [requestKey, setRequestKey] = useState(() => `employee-admin-${crypto.randomUUID()}`);
  const [preparation, setPreparation] = useState<Preparation>({ state: "loading" });
  const [readinessAttempt, setReadinessAttempt] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [message, setMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [onboarding, setOnboarding] = useState<IdentityOnboardingView | null>(null);
  const [delivery, setDelivery] = useState<IdentityOnboardingDeliveryView | null>(null);
  const [rosterPreview, setRosterPreview] = useState<RealRosterOnboardingPreview | null>(null);
  const [rosterPreviewError, setRosterPreviewError] = useState(false);
  const [confirmAccessProfile, setConfirmAccessProfile] = useState(false);
  const [matchPlan, setMatchPlan] = useState<import("./api").SimpleEmployeeMatchResponse | null>(null);

  useEffect(() => {
    if (!authorized || !rosterKey) return;
    let current = true;
    void getRealRosterOnboardingPreview(rosterKey).then((preview) => {
      if (!current) return;
      setRosterPreviewError(false);
      setRosterPreview(preview);
      setFirstName(preview.first_name);
      setLastName(preview.last_name);
      setEmail(preview.proposed_login_email);
      setProfileLabel(preview.operating_role);
      setBranchId(preview.source_branch_id);
    }).catch(() => {
      if (current) setRosterPreviewError(true);
    });
    return () => { current = false; };
  }, [authorized, rosterKey]);

  useEffect(() => {
    if (!authorized) return;
    let current = true;
    void listRoles().then((roles) => {
      if (!current) return;
      const systemRoles = roles.filter((role) => role.status === "active" && role.is_system);
      const profiles = OPERATING_PROFILES.flatMap((profile) => {
        const resolved = profile.roleCodes.map((alternatives) =>
          systemRoles.find((candidate) => alternatives.some((code) => code === candidate.code)),
        );
        return resolved.every((role): role is CompanyRole => Boolean(role))
          ? [{ label: profile.label, roles: resolved }]
          : [];
      });
      if (profiles.length !== OPERATING_PROFILES.length) {
        void getCanonicalRoleSyncPlan().then((reconciliation) => {
          if (!current) return;
          const unavailable = OPERATING_PROFILES
            .filter((profile) => !profiles.some((candidate) => candidate.label === profile.label))
            .map((profile) => profile.label.replaceAll("_", " "));
          setPreparation({
            state: "blocked",
            message: `Approved Employee operating profiles require canonical role reconciliation: ${unavailable.join(", ")}.`,
            reconciliation,
          });
        }).catch(() => {
          if (current) setPreparation({ state: "blocked", message: "Approved Employee operating profiles are unavailable and reconciliation readiness could not be verified." });
        });
        return;
      }
      setPreparation({ state: "ready", profiles });
    }).catch(() => {
      if (current) setPreparation({ state: "blocked", message: "Employee onboarding readiness could not be verified." });
    });
    return () => { current = false; };
  }, [authorized, readinessAttempt]);

  if (!authorized) return <Alert variant="danger" announcement="assertive">You are not authorized to add employees.</Alert>;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const selectedProfile = preparation.state === "ready"
      ? preparation.profiles.find((profile) => profile.label === profileLabel)
      : undefined;
    if (!selectedProfile || !branchId || !email.trim() || !firstName.trim() || !lastName.trim()) return;
    setSubmitting(true);
    setMessage(null);
    try {
      if (rosterKey && rosterPreview) {
        const created = await onboardRealRosterEmployee(rosterKey, {
          confirmed_source_employee_id: rosterPreview.source_employee_id,
          confirmed_login_email: email.trim(),
          confirm_access_profile: confirmAccessProfile,
        });
        setOnboarding(created);
        if (created.status === "invited") {
          setDelivery(await getIdentityOnboardingDelivery(created.id));
          setMessage({ kind: "success", text: "Source Employee bound and invited. Delivery status is shown below." });
        } else {
          setDelivery(null);
          setMessage({ kind: "success", text: "Source Employee was bound to the existing active login. No duplicate invitation was sent." });
        }
        return;
      }
      const match = await matchSimpleEmployee({ branch_id: branchId, first_name: firstName.trim(), last_name: lastName.trim(), email: email.trim(), phone: phone.trim() || undefined });
      if (match.outcome !== "NONE") {
        setMatchPlan(match);
        setMessage(null);
        return;
      }
      const created = await onboardSimpleEmployee({
        request_key: requestKey,
        branch_id: branchId,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim(),
        phone: phone.trim() || undefined,
        access_profile: profileLabel === "FIELD_TECH" ? "FIELD_TECHNICIAN" : profileLabel as "ADMINISTRATOR" | "OFFICE_MANAGER" | "OFFICE_STAFF" | "FIELD_MANAGER",
      });
      const view: IdentityOnboardingView = { id: created.onboarding_request_id, employee_id: created.employee_id, membership_id: created.membership_id, branch_id: created.branch_id, masked_login: email.trim(), status: created.status };
      setOnboarding(view);
      setDelivery(await getIdentityOnboardingDelivery(view.id));
      setFirstName(""); setLastName(""); setEmail(""); setPhone("");
      setRequestKey(`employee-admin-${crypto.randomUUID()}`);
      setMessage({ kind: "success", text: "Employee invited. Delivery status is shown below." });
    } catch (error) {
      setMessage({ kind: "error", text: submissionMessage(error) });
    } finally {
      setSubmitting(false);
    }
  };

  const confirmExistingHistory = async () => {
    if (!matchPlan || matchPlan.outcome !== "SINGLE" || !matchPlan.candidates[0] || !branchId || !firstName.trim() || !lastName.trim()) return;
    setSubmitting(true);
    try {
      const linked = await onboardSimpleEmployee({
        request_key: requestKey,
        branch_id: branchId,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim(),
        phone: phone.trim() || undefined,
        access_profile: profileLabel === "FIELD_TECH" ? "FIELD_TECHNICIAN" : profileLabel as "ADMINISTRATOR" | "OFFICE_MANAGER" | "OFFICE_STAFF" | "FIELD_MANAGER",
      });
      const view: IdentityOnboardingView = { id: linked.onboarding_request_id, employee_id: linked.employee_id, membership_id: linked.membership_id, branch_id: linked.branch_id, masked_login: email.trim(), status: linked.status };
      setOnboarding(view);
      setDelivery(linked.status === "invited" ? await getIdentityOnboardingDelivery(view.id) : null);
      setMatchPlan(null);
      setMessage({ kind: "success", text: "Employee linked. Invitation status is shown below." });
    } catch (error) {
      setMessage({ kind: "error", text: submissionMessage(error) });
    } finally { setSubmitting(false); }
  };

  const reconcileProfiles = async () => {
    if (preparation.state !== "blocked" || !preparation.reconciliation?.safe_to_apply) return;
    setReconciling(true);
    setMessage(null);
    try {
      await applyCanonicalRoleSync(preparation.reconciliation.plan_digest);
      setPreparation({ state: "loading" });
      setReadinessAttempt((value) => value + 1);
      setMessage({ kind: "success", text: "Approved Employee operating profiles are ready." });
    } catch {
      setMessage({ kind: "error", text: "Operating-profile reconciliation was not applied. Review the protected role conflict in Administration." });
    } finally {
      setReconciling(false);
    }
  };

  const updateInvitation = async (operation: "reissue" | "revoke") => {
    if (!onboarding) return;
    setSubmitting(true);
    try {
      const updated = operation === "reissue" ? await reissueIdentityOnboarding(onboarding.id) : await revokeIdentityOnboarding(onboarding.id);
      setOnboarding(updated);
      setDelivery(await getIdentityOnboardingDelivery(updated.id));
    } catch (error) {
      setMessage({ kind: "error", text: submissionMessage(error) });
    } finally { setSubmitting(false); }
  };

  return <div className="mx-auto w-full max-w-2xl space-y-ui-5 pb-ui-8">
    <header><h1 className="text-heading-m">Workforce / Add Employee</h1><p className="mt-ui-2 text-body-s text-content-muted">Add an employee, choose their branch and access profile, then send an invitation.</p></header>
    {message && <Alert variant={message.kind === "success" ? "success" : "danger"} announcement={message.kind === "success" ? "polite" : "assertive"}>{message.text}</Alert>}
    {rosterPreviewError && <Alert variant="danger">The exact source Employee is not ready for onboarding. No Employee or invitation was created.</Alert>}
    {rosterKey && !rosterPreview && !rosterPreviewError && <Spinner label="Loading exact source Employee" />}
    {rosterPreview && <Alert variant="information"><strong>{rosterPreview.display_name}</strong> · HCP {rosterPreview.source_employee_id} · {rosterPreview.source_login_email} · {rosterPreview.source_branch_code}. This source identity is locked; ACP will activate the existing deterministic Employee instead of creating a duplicate.</Alert>}
    <Card><CardHeader><CardTitle>{rosterPreview ? "Activate Source Employee" : "Add Employee"}</CardTitle><CardDescription>{rosterPreview ? "The preserved source identity is read-only. Confirm the canonical access profile before issuing its single-use invitation." : "Standard role permissions and Company scope are applied automatically. Duplicate identities fail safely. Login email is never guessed or prefilled from roster identity."}</CardDescription></CardHeader><CardContent>
      {preparation.state === "loading" ? <Spinner label="Checking Employee onboarding readiness" /> : preparation.state === "blocked" ? <Alert variant="danger"><div className="space-y-ui-3"><p>{preparation.message}</p>{preparation.reconciliation && !preparation.reconciliation.safe_to_apply && <p>A protected role identity conflict requires review. No role will be replaced automatically.</p>}<div className="flex flex-wrap gap-ui-3">{preparation.reconciliation?.safe_to_apply && canReconcileProfiles && <Button loading={reconciling} loadingLabel="Preparing profiles" onClick={() => void reconcileProfiles()}>Prepare approved profiles</Button>}<Button variant="secondary" onClick={() => { setPreparation({ state: "loading" }); setReadinessAttempt((value) => value + 1); }}>Retry readiness</Button>{(!preparation.reconciliation?.safe_to_apply || !canReconcileProfiles) && <Link className="text-link" to="/administration">Review protected roles</Link>}</div></div></Alert> :
        <form className="space-y-ui-4" onSubmit={(event) => void submit(event)}>
          <div className="grid gap-ui-3 sm:grid-cols-2">
            <label className="block space-y-ui-2"><span className="text-body-s font-semibold">First name</span><Input value={firstName} onChange={(event) => setFirstName(event.target.value)} readOnly={Boolean(rosterPreview)} required /></label>
            <label className="block space-y-ui-2"><span className="text-body-s font-semibold">Last name</span><Input value={lastName} onChange={(event) => setLastName(event.target.value)} readOnly={Boolean(rosterPreview)} required /></label>
          </div>
          <div className="grid gap-ui-3 sm:grid-cols-2"><label className="block space-y-ui-2"><span className="text-body-s font-semibold">Email</span><Input aria-label="Email" type="email" autoComplete="off" value={email} onChange={(event) => setEmail(event.target.value)} required /></label><label className="block space-y-ui-2"><span className="text-body-s font-semibold">Phone</span><Input aria-label="Phone" type="tel" autoComplete="tel" value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="(555) 555-5555" /></label></div>
          <label className="block space-y-ui-2"><span className="text-body-s font-semibold">Access profile</span><select aria-label="Access profile" className="min-h-11 w-full rounded-md border border-stroke bg-surface px-ui-3" value={profileLabel} onChange={(event) => setProfileLabel(event.target.value)} disabled={Boolean(rosterPreview)} required>{preparation.profiles.map((profile) => <option key={profile.label} value={profile.label}>{profileDisplayName(profile.label)}</option>)}</select></label>
          <label className="block space-y-ui-2"><span className="text-body-s font-semibold">Branch</span><select className="min-h-11 w-full rounded-md border border-stroke bg-surface px-ui-3" value={branchId} onChange={(event) => setBranchId(event.target.value)} disabled={Boolean(rosterPreview)} required><option value="" disabled>Select a Branch</option>{branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}{branch.code === "MAIN" ? " (MAIN)" : ""}</option>)}</select></label>
          {rosterPreview && <label className="flex items-start gap-ui-3 rounded-lg border border-stroke p-ui-3 text-body-s"><input className="mt-1" type="checkbox" checked={confirmAccessProfile} onChange={(event) => setConfirmAccessProfile(event.target.checked)} /><span>I confirm the <strong>{rosterPreview.operating_role.replaceAll("_", " ")}</strong> access profile ({rosterPreview.required_role_codes.join(", ")}) for this exact source Employee.</span></label>}
          <Button type="submit" loading={submitting} loadingLabel="Checking employee history" disabled={submitting || !branchId || !profileLabel || !firstName.trim() || !lastName.trim() || !email.trim() || (Boolean(rosterPreview) && !confirmAccessProfile)}>{rosterPreview ? "Confirm Source & Send Invite" : "Send Invite"}</Button>
        </form>}
    </CardContent></Card>
    {matchPlan && <Card className="border-action-primary"><CardHeader><CardTitle>{matchPlan.outcome === "SINGLE" ? "Existing employee history found" : "Multiple existing employee records found"}</CardTitle><CardDescription>{matchPlan.outcome === "SINGLE" ? "Would you like to link this employee to the existing history?" : "This employee needs a quick identity choice before an invitation can be sent."}</CardDescription></CardHeader><CardContent className="space-y-ui-3">{matchPlan.outcome === "AMBIGUOUS" && <ul className="list-disc pl-5 text-body-s">{matchPlan.candidates.map((candidate) => <li key={candidate.employee_id}>Existing Employee {candidate.employee_id}{candidate.source_employee_id ? ` · source ${candidate.source_employee_id}` : ""}</li>)}</ul>}<div className="flex gap-ui-3">{matchPlan.outcome === "SINGLE" && <Button loading={submitting} onClick={() => void confirmExistingHistory()}>Link &amp; Continue</Button>}<Button variant="secondary" disabled={submitting} onClick={() => setMatchPlan(null)}>Cancel</Button></div></CardContent></Card>}
    {onboarding && <Card><CardHeader><CardTitle>Employee created/linked</CardTitle><CardDescription>Invitation sent. The employee can use the invitation to finish setup.</CardDescription></CardHeader><CardContent className="space-y-ui-3"><p><strong>Branch:</strong> {branches.find((branch) => branch.id === onboarding.branch_id)?.name ?? "Selected branch"}</p><p><strong>Access profile:</strong> {profileDisplayName(profileLabel)}</p><div className="flex flex-wrap gap-ui-3"><Link className="text-link" to={`/employees?employee=${onboarding.employee_id}`}>View Employee</Link><Button variant="secondary" onClick={() => { setOnboarding(null); setDelivery(null); setMessage(null); setMatchPlan(null); setFirstName(""); setLastName(""); setEmail(""); setPhone(""); }}>Add Another Employee</Button></div></CardContent></Card>}
    {onboarding && delivery && <Card><CardHeader><CardTitle>Invitation status</CardTitle><CardDescription>Invitation and email delivery are tracked separately. Queued is not delivered.</CardDescription></CardHeader><CardContent className="space-y-ui-4"><dl className="grid gap-ui-3 text-body-s sm:grid-cols-2"><div><dt className="text-content-muted">Account</dt><dd className="font-semibold">{onboarding.status.replaceAll("_", " ")}</dd></div><div><dt className="text-content-muted">Invitation</dt><dd className="font-semibold">{delivery.invitation_status.replaceAll("_", " ")}</dd></div><div><dt className="text-content-muted">Email delivery</dt><dd className="font-semibold">{delivery.delivery_status.replaceAll("_", " ")}</dd></div><div><dt className="text-content-muted">Provider</dt><dd className="font-semibold">{delivery.provider_reference_present ? "Accepted" : "Not accepted"}</dd></div></dl>{delivery.last_error_code && <Alert variant="warning">Invitation delivery requires attention: {delivery.last_error_code.replaceAll("_", " ")}.</Alert>}<p className="text-body-xs text-content-muted">The employee receives an expiring, single-use activation link and creates their own password.</p><div className="flex gap-ui-3"><Button variant="secondary" loading={submitting} onClick={() => void updateInvitation("reissue")}>Reissue invitation</Button><Button variant="secondary" loading={submitting} onClick={() => void updateInvitation("revoke")}>Revoke invitation</Button></div></CardContent></Card>}
    <div className="flex gap-ui-4"><Link className="text-link" to="/employees">View Team</Link><Link className="text-link" to="/administration">Advanced Administration</Link></div>
  </div>;
}
