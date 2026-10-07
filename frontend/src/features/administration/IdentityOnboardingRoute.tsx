import axios from "axios";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
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
    roleCodes: [["FIELD_MANAGER"], ["TECHNICIAN"], ["ACP_EMPLOYEE_MOBILE"], ["DISPATCHER"]],
  },
] as const;

const HUMAN_POSITIONS = [
  { label: "Owner", profile: "ADMIN" },
  { label: "Operations Manager", profile: "OFFICE_MANAGER" },
  { label: "Field Service Manager", profile: "FIELD_MANAGER" },
  { label: "Technician", profile: "FIELD_TECH" },
  { label: "Helper", profile: "FIELD_TECH" },
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
  const [positionLabel, setPositionLabel] = useState<string>(() => HUMAN_POSITIONS.find((position) => position.profile === (searchParams.get("profile") ?? "FIELD_TECH"))?.label ?? "Technician");
  const [requestKey, setRequestKey] = useState(() => `employee-admin-${crypto.randomUUID()}`);
  const [preparation, setPreparation] = useState<Preparation>({ state: "loading" });
  const [readinessAttempt, setReadinessAttempt] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [message, setMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [onboarding, setOnboarding] = useState<IdentityOnboardingView | null>(null);
  const [onboardedIdentity, setOnboardedIdentity] = useState<{ name: string; email: string } | null>(null);
  const [delivery, setDelivery] = useState<IdentityOnboardingDeliveryView | null>(null);
  const [rosterPreview, setRosterPreview] = useState<RealRosterOnboardingPreview | null>(null);
  const [rosterPreviewError, setRosterPreviewError] = useState(false);
  const [confirmAccessProfile, setConfirmAccessProfile] = useState(false);
  const [matchPlan, setMatchPlan] = useState<import("./api").SimpleEmployeeMatchResponse | null>(null);
  const matchRequestSequence = useRef(0);

  const invalidateMatch = () => {
    matchRequestSequence.current += 1;
    setMatchPlan(null);
  };

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
      setPositionLabel(HUMAN_POSITIONS.find((position) => position.profile === preview.operating_role)?.label ?? "Technician");
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
    if (!selectedProfile || !branchId || !email.trim() || !phone.trim() || !firstName.trim() || !lastName.trim()) return;
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
        setOnboardedIdentity({ name: rosterPreview.display_name, email: email.trim() });
        if (created.status === "invited") {
          setDelivery(await getIdentityOnboardingDelivery(created.id));
          setMessage({ kind: "success", text: "Source Employee bound and invited. Delivery status is shown below." });
        } else {
          setDelivery(null);
          setMessage({ kind: "success", text: "Source Employee was bound to the existing active login. No duplicate invitation was sent." });
        }
        return;
      }
      const requestSequence = ++matchRequestSequence.current;
      setMatchPlan(null);
      const match = await matchSimpleEmployee({ branch_id: branchId, first_name: firstName.trim(), last_name: lastName.trim(), email: email.trim(), phone: phone.trim() || undefined });
      if (requestSequence !== matchRequestSequence.current) return;
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
      setOnboardedIdentity({ name: `${firstName.trim()} ${lastName.trim()}`, email: email.trim() });
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
      setOnboardedIdentity({ name: `${firstName.trim()} ${lastName.trim()}`, email: email.trim() });
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
    <header><h1 className="text-heading-m">Add Employee</h1><p className="mt-ui-2 text-body-s text-content-muted">Five details. TwelveHats handles the operating access underneath.</p></header>
    {message && <Alert variant={message.kind === "success" ? "success" : "danger"} announcement={message.kind === "success" ? "polite" : "assertive"}>{message.text}</Alert>}
    {rosterPreviewError && <Alert variant="danger">The exact source Employee is not ready for onboarding. No Employee or invitation was created.</Alert>}
    {rosterKey && !rosterPreview && !rosterPreviewError && <Spinner label="Loading exact source Employee" />}
    {rosterPreview && <Alert variant="information"><strong>{rosterPreview.display_name}</strong> · HCP {rosterPreview.source_employee_id} · {rosterPreview.source_login_email} · {rosterPreview.source_branch_code}. This source identity is locked; ACP will activate the existing deterministic Employee instead of creating a duplicate.</Alert>}
    <Card><CardHeader><CardTitle>{rosterPreview ? "Activate Source Employee" : "Employee details"}</CardTitle><CardDescription>{rosterPreview ? "The preserved source identity is read-only. Confirm the governed Position before issuing its single-use invitation." : "No Payroll, tax, direct-deposit, permission, or equipment setup is required here."}</CardDescription></CardHeader><CardContent>
      {preparation.state === "loading" ? <Spinner label="Checking Employee onboarding readiness" /> : preparation.state === "blocked" ? <Alert variant="danger"><div className="space-y-ui-3"><p>{preparation.message}</p>{preparation.reconciliation && !preparation.reconciliation.safe_to_apply && <p>A protected role identity conflict requires review. No role will be replaced automatically.</p>}<div className="flex flex-wrap gap-ui-3">{preparation.reconciliation?.safe_to_apply && canReconcileProfiles && <Button loading={reconciling} loadingLabel="Preparing profiles" onClick={() => void reconcileProfiles()}>Prepare approved profiles</Button>}<Button variant="secondary" onClick={() => { setPreparation({ state: "loading" }); setReadinessAttempt((value) => value + 1); }}>Retry readiness</Button>{(!preparation.reconciliation?.safe_to_apply || !canReconcileProfiles) && <Link className="text-link" to="/administration">Review protected roles</Link>}</div></div></Alert> :
        <form className="space-y-ui-4" onSubmit={(event) => void submit(event)}>
          <div className="grid gap-ui-3 sm:grid-cols-2">
            <label className="block space-y-ui-2"><span className="text-body-s font-semibold">First name</span><Input value={firstName} onChange={(event) => { invalidateMatch(); setFirstName(event.target.value); }} readOnly={Boolean(rosterPreview)} required /></label>
            <label className="block space-y-ui-2"><span className="text-body-s font-semibold">Last name</span><Input value={lastName} onChange={(event) => { invalidateMatch(); setLastName(event.target.value); }} readOnly={Boolean(rosterPreview)} required /></label>
          </div>
          <div className="grid gap-ui-3 sm:grid-cols-2"><label className="block space-y-ui-2"><span className="text-body-s font-semibold">Email Address</span><Input aria-label="Email Address" type="email" autoComplete="off" value={email} onChange={(event) => { invalidateMatch(); setEmail(event.target.value); }} required /></label><label className="block space-y-ui-2"><span className="text-body-s font-semibold">Phone Number</span><Input aria-label="Phone Number" type="tel" autoComplete="tel" value={phone} onChange={(event) => { invalidateMatch(); setPhone(event.target.value); }} placeholder="(555) 555-5555" required /></label></div>
          <label className="block space-y-ui-2"><span className="text-body-s font-semibold">Position</span><select aria-label="Position" className="min-h-11 w-full rounded-md border border-stroke bg-surface px-ui-3" value={positionLabel} onChange={(event) => { const position = HUMAN_POSITIONS.find((candidate) => candidate.label === event.target.value); invalidateMatch(); setPositionLabel(event.target.value); setProfileLabel(position?.profile ?? "FIELD_TECH"); }} disabled={Boolean(rosterPreview)} required>{HUMAN_POSITIONS.map((position) => <option key={position.label} value={position.label}>{position.label}</option>)}</select><span className="text-body-xs text-content-muted">Position applies the governed operating role template. Permissions remain in advanced administration.</span></label>
          <p className="rounded-lg bg-surface-subtle p-ui-3 text-body-s"><strong>Branch:</strong> {branches.find((branch) => branch.id === branchId)?.name ?? "Current Branch"} <span className="text-content-muted">(inherited from Company context)</span></p>
          {rosterPreview && <label className="flex items-start gap-ui-3 rounded-lg border border-stroke p-ui-3 text-body-s"><input className="mt-1" type="checkbox" checked={confirmAccessProfile} onChange={(event) => setConfirmAccessProfile(event.target.checked)} /><span>I confirm the <strong>{rosterPreview.operating_role.replaceAll("_", " ")}</strong> access profile ({rosterPreview.required_role_codes.join(", ")}) for this exact source Employee.</span></label>}
          <Button type="submit" loading={submitting} loadingLabel="Checking employee history" disabled={submitting || !branchId || !profileLabel || !firstName.trim() || !lastName.trim() || !email.trim() || !phone.trim() || (Boolean(rosterPreview) && !confirmAccessProfile)}>{rosterPreview ? "Confirm Source & Send Invite" : "Add Employee & Send Invite"}</Button>
        </form>}
    </CardContent></Card>
    {matchPlan && <Card className="border-action-primary"><CardHeader><CardTitle>{matchPlan.outcome === "SINGLE" ? "This person already has a TwelveHats Employee history" : "More than one Employee history needs review"}</CardTitle><CardDescription>{matchPlan.outcome === "SINGLE" ? "Review and link the governed existing history instead of creating a duplicate. Terminated history is never silently reactivated." : "Choose the correct governed Employee record in advanced identity review. No invitation was sent."}</CardDescription></CardHeader><CardContent className="space-y-ui-3">{matchPlan.outcome === "AMBIGUOUS" && <p className="text-body-s">{matchPlan.candidates.length} protected Employee records require review.</p>}<div className="flex gap-ui-3">{matchPlan.outcome === "SINGLE" && <Button loading={submitting} onClick={() => void confirmExistingHistory()}>Review &amp; Link Existing Employee</Button>}<Button variant="secondary" disabled={submitting} onClick={() => setMatchPlan(null)}>Cancel</Button></div></CardContent></Card>}
    {onboarding && <Card><CardHeader><CardTitle>{onboardedIdentity?.name ?? "Employee"} added.</CardTitle><CardDescription>Invitation sent to: {onboardedIdentity?.email ?? onboarding.masked_login}. Waiting for the Employee to accept.</CardDescription></CardHeader><CardContent className="space-y-ui-3"><dl className="grid gap-ui-2 text-body-s sm:grid-cols-5">{[["Account", "Created"], ["Invitation", onboarding.status === "invited" ? "Sent" : "Connected"], ["Mobile", "After acceptance"], ["Payroll Setup", "Not started"], ["Direct Deposit", "Not started"]].map(([label, value]) => <div className="rounded-lg bg-surface-subtle p-ui-2" key={label}><dt className="text-content-muted">{label}</dt><dd className="font-semibold">{value}</dd></div>)}</dl><p><strong>Branch:</strong> {branches.find((branch) => branch.id === onboarding.branch_id)?.name ?? "Selected branch"}</p><p><strong>Position:</strong> {positionLabel || profileDisplayName(profileLabel)}</p><div className="flex flex-wrap gap-ui-3"><Link className="text-link" to={`/employees?employee=${onboarding.employee_id}`}>View Employee</Link><Button variant="secondary" onClick={() => { setOnboarding(null); setOnboardedIdentity(null); setDelivery(null); setMessage(null); setMatchPlan(null); setFirstName(""); setLastName(""); setEmail(""); setPhone(""); }}>Add Another Employee</Button></div></CardContent></Card>}
    {onboarding && delivery && <Card><CardHeader><CardTitle>Invitation status</CardTitle><CardDescription>Invitation and email delivery are tracked separately. Queued is not delivered.</CardDescription></CardHeader><CardContent className="space-y-ui-4"><dl className="grid gap-ui-3 text-body-s sm:grid-cols-2"><div><dt className="text-content-muted">Account</dt><dd className="font-semibold">{onboarding.status.replaceAll("_", " ")}</dd></div><div><dt className="text-content-muted">Invitation</dt><dd className="font-semibold">{delivery.invitation_status.replaceAll("_", " ")}</dd></div><div><dt className="text-content-muted">Email delivery</dt><dd className="font-semibold">{delivery.delivery_status.replaceAll("_", " ")}</dd></div><div><dt className="text-content-muted">Provider</dt><dd className="font-semibold">{delivery.provider_reference_present ? "Accepted" : "Not accepted"}</dd></div></dl>{delivery.last_error_code && <Alert variant="warning">Invitation delivery requires attention: {delivery.last_error_code.replaceAll("_", " ")}.</Alert>}<p className="text-body-xs text-content-muted">The employee receives an expiring, single-use activation link and creates their own password.</p><div className="flex gap-ui-3"><Button variant="secondary" loading={submitting} onClick={() => void updateInvitation("reissue")}>Reissue invitation</Button><Button variant="secondary" loading={submitting} onClick={() => void updateInvitation("revoke")}>Revoke invitation</Button></div></CardContent></Card>}
    <div className="flex gap-ui-4"><Link className="text-link" to="/employees">View Team</Link><Link className="text-link" to="/administration">Advanced Administration</Link></div>
  </div>;
}
