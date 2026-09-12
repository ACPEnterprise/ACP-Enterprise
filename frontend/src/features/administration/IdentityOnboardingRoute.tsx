import axios from "axios";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router";

import { useAuth } from "../../auth";
import { Alert, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Spinner } from "../../ui";
import {
  getIdentityOnboardingDelivery,
  initiateEmployeeBetaOnboarding,
  listRoles,
  planEmployeeOnboarding,
  reissueIdentityOnboarding,
  revokeIdentityOnboarding,
  type CompanyRole,
  type IdentityOnboardingDeliveryView,
  type IdentityOnboardingView,
} from "./api";

const ONBOARDING_PERMISSION = "COMPANY_IDENTITY_ONBOARDING_MANAGE";
const STANDARD_ROLES = [
  { label: "OWNER", codes: ["OWNER", "COMPANY_ADMINISTRATOR"] },
  { label: "MANAGER", codes: ["MANAGER", "OFFICE_MANAGER"] },
  { label: "ADMIN", codes: ["ADMIN", "COMPANY_ADMINISTRATOR"] },
  { label: "CSR", codes: ["CSR", "SERVICE_CSR"] },
  { label: "TECHNICIAN", codes: ["TECHNICIAN"] },
] as const;

type StandardRole = CompanyRole & { standardLabel: string };
type Preparation =
  | { state: "loading" }
  | { state: "ready"; roles: StandardRole[] }
  | { state: "blocked"; message: string };

function submissionMessage(error: unknown): string {
  if (axios.isAxiosError(error) && error.response?.status === 403) return "You are not authorized to add employees.";
  if (axios.isAxiosError(error) && error.response?.status === 409) return "This employee conflicts with an existing Company identity. Review the existing Team record before retrying.";
  return "The employee was not invited. Please retry or review the existing Team record.";
}

export function IdentityOnboardingRoute() {
  const { activeCompany, permissionCodes = [] } = useAuth();
  const authorized = permissionCodes.includes(ONBOARDING_PERMISSION);
  const branches = useMemo(() => activeCompany?.branches ?? [], [activeCompany]);
  const defaultBranch = activeCompany?.default_branch_id ?? branches.find((branch) => branch.code === "MAIN")?.id ?? branches[0]?.id ?? "";
  const [branchId, setBranchId] = useState(defaultBranch);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [roleId, setRoleId] = useState("");
  const [requestKey, setRequestKey] = useState(() => `employee-admin-${crypto.randomUUID()}`);
  const [preparation, setPreparation] = useState<Preparation>({ state: "loading" });
  const [readinessAttempt, setReadinessAttempt] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [onboarding, setOnboarding] = useState<IdentityOnboardingView | null>(null);
  const [delivery, setDelivery] = useState<IdentityOnboardingDeliveryView | null>(null);

  useEffect(() => {
    if (!authorized) return;
    let current = true;
    void listRoles().then((roles) => {
      if (!current) return;
      const systemRoles = roles.filter((role) => role.status === "active" && role.is_system);
      const standardRoles = STANDARD_ROLES.flatMap((option) => {
        const role = systemRoles.find((candidate) => option.codes.some((code) => code === candidate.code));
        return role ? [{ ...role, standardLabel: option.label }] : [];
      });
      if (!standardRoles.some((role) => role.standardLabel === "TECHNICIAN")) {
        setPreparation({ state: "blocked", message: "Standard Employee roles are unavailable." });
        return;
      }
      setRoleId((value) => value || standardRoles.find((role) => role.standardLabel === "TECHNICIAN")?.id || "");
      setPreparation({ state: "ready", roles: standardRoles });
    }).catch(() => {
      if (current) setPreparation({ state: "blocked", message: "Employee onboarding readiness could not be verified." });
    });
    return () => { current = false; };
  }, [authorized, readinessAttempt]);

  if (!authorized) return <Alert variant="danger" announcement="assertive">You are not authorized to add employees.</Alert>;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (preparation.state !== "ready" || !branchId || !roleId || !email.trim() || !firstName.trim() || !lastName.trim()) return;
    setSubmitting(true);
    setMessage(null);
    try {
      const input = {
        branch_id: branchId,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        display_name: `${firstName.trim()} ${lastName.trim()}`,
        role_ids: [roleId],
        additional_permission_ids: [],
        login_email: email.trim(),
      };
      const plan = await planEmployeeOnboarding(input);
      if (!plan.safe_to_apply) {
        setMessage({ kind: "error", text: plan.blockers.length > 0
          ? `This employee needs review before an invitation can be sent: ${plan.blockers.map((item) => item.replaceAll("_", " ")).join(" · ")}.`
          : "This employee needs review before an invitation can be sent." });
        return;
      }
      const created = await initiateEmployeeBetaOnboarding({
        ...input,
        request_key: requestKey,
        employee_type: "employee",
        employee_number_prefix: plan.employee_number_prefix,
        employee_number_width: plan.employee_number_width,
      });
      setOnboarding(created);
      setDelivery(await getIdentityOnboardingDelivery(created.id));
      setFirstName(""); setLastName(""); setEmail("");
      setRequestKey(`employee-admin-${crypto.randomUUID()}`);
      setMessage({ kind: "success", text: "Employee invited. Delivery status is shown below." });
    } catch (error) {
      setMessage({ kind: "error", text: submissionMessage(error) });
    } finally {
      setSubmitting(false);
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
    <header><h1 className="text-heading-m">Team / Employees</h1><p className="mt-ui-2 text-body-s text-content-muted">Add an employee, select their standard role, and send a protected invitation.</p></header>
    {message && <Alert variant={message.kind === "success" ? "success" : "danger"} announcement={message.kind === "success" ? "polite" : "assertive"}>{message.text}</Alert>}
    <Card><CardHeader><CardTitle>Add Employee</CardTitle><CardDescription>Standard role permissions and Company scope are applied automatically. Duplicate identities fail safely.</CardDescription></CardHeader><CardContent>
      {preparation.state === "loading" ? <Spinner label="Checking Employee onboarding readiness" /> : preparation.state === "blocked" ? <Alert variant="danger"><div className="space-y-ui-3"><p>{preparation.message}</p><Button variant="secondary" onClick={() => { setPreparation({ state: "loading" }); setReadinessAttempt((value) => value + 1); }}>Retry readiness</Button></div></Alert> :
        <form className="space-y-ui-4" onSubmit={(event) => void submit(event)}>
          <div className="grid gap-ui-3 sm:grid-cols-2">
            <label className="block space-y-ui-2"><span className="text-body-s font-semibold">First name</span><Input value={firstName} onChange={(event) => setFirstName(event.target.value)} required /></label>
            <label className="block space-y-ui-2"><span className="text-body-s font-semibold">Last name</span><Input value={lastName} onChange={(event) => setLastName(event.target.value)} required /></label>
          </div>
          <label className="block space-y-ui-2"><span className="text-body-s font-semibold">Email</span><Input type="email" autoComplete="off" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
          <label className="block space-y-ui-2"><span className="text-body-s font-semibold">Role</span><select className="min-h-11 w-full rounded-md border border-stroke bg-surface px-ui-3" value={roleId} onChange={(event) => setRoleId(event.target.value)} required>{preparation.roles.map((role) => <option key={`${role.standardLabel}-${role.id}`} value={role.id}>{role.standardLabel}</option>)}</select><span className="text-body-xs text-content-muted">Standard permissions are assigned automatically. Advanced customization remains in Role Administration.</span></label>
          <label className="block space-y-ui-2"><span className="text-body-s font-semibold">Branch</span><select className="min-h-11 w-full rounded-md border border-stroke bg-surface px-ui-3" value={branchId} onChange={(event) => setBranchId(event.target.value)} required><option value="" disabled>Select a Branch</option>{branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}{branch.code === "MAIN" ? " (MAIN)" : ""}</option>)}</select></label>
          <Button type="submit" loading={submitting} loadingLabel="Sending invite" disabled={submitting || !branchId || !roleId || !firstName.trim() || !lastName.trim() || !email.trim()}>Send Invite</Button>
        </form>}
    </CardContent></Card>
    {onboarding && delivery && <Card><CardHeader><CardTitle>Employee status</CardTitle><CardDescription>Invitation and email delivery are tracked separately. Queued is not delivered.</CardDescription></CardHeader><CardContent className="space-y-ui-4"><dl className="grid gap-ui-3 text-body-s sm:grid-cols-2"><div><dt className="text-content-muted">Account</dt><dd className="font-semibold">{onboarding.status.replaceAll("_", " ")}</dd></div><div><dt className="text-content-muted">Invitation</dt><dd className="font-semibold">{delivery.invitation_status.replaceAll("_", " ")}</dd></div><div><dt className="text-content-muted">Email delivery</dt><dd className="font-semibold">{delivery.delivery_status.replaceAll("_", " ")}</dd></div><div><dt className="text-content-muted">Provider</dt><dd className="font-semibold">{delivery.provider_reference_present ? "Accepted" : "Not accepted"}</dd></div></dl>{delivery.last_error_code && <Alert variant="warning">Invitation delivery requires attention: {delivery.last_error_code.replaceAll("_", " ")}.</Alert>}<p className="text-body-xs text-content-muted">The employee receives an expiring, single-use activation link and creates their own password.</p><div className="flex gap-ui-3"><Button variant="secondary" loading={submitting} onClick={() => void updateInvitation("reissue")}>Reissue invitation</Button><Button variant="secondary" loading={submitting} onClick={() => void updateInvitation("revoke")}>Revoke invitation</Button></div></CardContent></Card>}
    <div className="flex gap-ui-4"><Link className="text-link" to="/employees">View Team</Link><Link className="text-link" to="/administration">Advanced Administration</Link></div>
  </div>;
}
