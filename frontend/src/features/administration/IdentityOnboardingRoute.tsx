import axios from "axios";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router";

import { useAuth } from "../../auth";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Spinner,
} from "../../ui";
import {
  getIdentityOnboardingDelivery,
  initiateEmployeeBetaOnboarding,
  listPermissions,
  listRoles,
  planEmployeeOnboarding,
  reissueIdentityOnboarding,
  revokeIdentityOnboarding,
  type CompanyRole,
  type IdentityOnboardingDeliveryView,
  type IdentityOnboardingPlan,
  type IdentityOnboardingView,
  type PermissionDefinition,
} from "./api";

const ONBOARDING_PERMISSION = "COMPANY_IDENTITY_ONBOARDING_MANAGE";
type Preparation =
  | { state: "loading" }
  | { state: "ready"; roles: CompanyRole[] }
  | { state: "blocked"; message: string };

function submissionMessage(error: unknown): string {
  if (axios.isAxiosError(error) && error.response?.status === 403) {
    return "You are not authorized to initiate Company identity onboarding.";
  }
  if (axios.isAxiosError(error) && error.response?.status === 409) {
    return "Onboarding was not created because the request conflicts with current Company authority.";
  }
  return "Onboarding could not be created. No activation material was displayed.";
}

export function IdentityOnboardingRoute() {
  const { activeCompany, permissionCodes = [] } = useAuth();
  const authorized = permissionCodes.includes(ONBOARDING_PERMISSION);
  const branches = useMemo(() => activeCompany?.branches ?? [], [activeCompany]);
  const initialBranchId = activeCompany?.default_branch_id ?? branches[0]?.id ?? "";
  const [branchId, setBranchId] = useState(initialBranchId);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [roleId, setRoleId] = useState("");
  const [loginAddress, setLoginAddress] = useState("");
  const [requestKey, setRequestKey] = useState(() => `employee-admin-${crypto.randomUUID()}`);
  const [preparation, setPreparation] = useState<Preparation>({ state: "loading" });
  const [readinessAttempt, setReadinessAttempt] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<"success" | "error" | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [permissions, setPermissions] = useState<PermissionDefinition[]>([]);
  const [additionalPermissionIds, setAdditionalPermissionIds] = useState<string[]>([]);
  const [permissionSearch, setPermissionSearch] = useState("");
  const [highImpactOnly, setHighImpactOnly] = useState(false);
  const [onboarding, setOnboarding] = useState<IdentityOnboardingView | null>(null);
  const [delivery, setDelivery] = useState<IdentityOnboardingDeliveryView | null>(null);
  const [plan, setPlan] = useState<IdentityOnboardingPlan | null>(null);

  useEffect(() => {
    if (!authorized) return;
    let current = true;
    void listRoles().then((roles) => {
        if (!current) return;
        const available = roles.filter((role) => role.status === "active" && role.is_system);
        if (available.length === 0) {
          setPreparation({
            state: "blocked",
            message: "Canonical Employee roles are unavailable.",
          });
          return;
        }
        setRoleId((currentRole) => currentRole || available[0].id);
        setPreparation({ state: "ready", roles: available });
      })
      .catch(() => {
        if (current) {
          setPreparation({
            state: "blocked",
            message: "Employee onboarding readiness could not be verified.",
          });
        }
      });
    return () => {
      current = false;
    };
  }, [authorized, readinessAttempt]);

  useEffect(() => {
    if (!authorized || !roleId) {
      return;
    }
    let current = true;
    void Promise.all([listPermissions(roleId), listPermissions()])
      .then(([roleItems, allItems]) => {
        if (!current) return;
        const defaults = new Set(roleItems.filter((item) => item.assigned).map((item) => item.id));
        setPermissions(allItems.map((item) => ({ ...item, assigned: defaults.has(item.id) })));
        setAdditionalPermissionIds([]);
      })
      .catch(() => { if (current) setPermissions([]); });
    return () => { current = false; };
  }, [authorized, roleId]);

  const visiblePermissions = useMemo(() => {
    const query = permissionSearch.trim().toLowerCase();
    return permissions.filter((permission) =>
      (!highImpactOnly || permission.high_impact) &&
      (!query || [permission.name, permission.description ?? "", permission.category ?? "Other", permission.code].some((value) => value.toLowerCase().includes(query)))
    );
  }, [permissions, permissionSearch, highImpactOnly]);
  const permissionGroups = useMemo(() => visiblePermissions.reduce<Record<string, PermissionDefinition[]>>((groups, permission) => {
    (groups[permission.category ?? "Other"] ??= []).push(permission);
    return groups;
  }, {}), [visiblePermissions]);

  if (!authorized) {
    return (
      <Alert variant="danger" announcement="assertive">
        You are not authorized to initiate Company identity onboarding.
      </Alert>
    );
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!plan?.safe_to_apply || preparation.state !== "ready" || !branchId || !roleId || !loginAddress.trim() || !firstName.trim() || !lastName.trim()) return;
    setSubmitting(true);
    setResult(null);
    setErrorMessage("");
    try {
      const created = await initiateEmployeeBetaOnboarding({
        request_key: requestKey,
        branch_id: branchId,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        display_name: displayName.trim() || `${firstName.trim()} ${lastName.trim()}`,
        employee_type: "employee",
        employee_number_prefix: "EMP-",
        employee_number_width: 4,
        role_ids: [roleId],
        additional_permission_ids: additionalPermissionIds,
        login_email: loginAddress.trim(),
      });
      setOnboarding(created);
      setDelivery(await getIdentityOnboardingDelivery(created.id));
      setLoginAddress("");
      setFirstName("");
      setLastName("");
      setDisplayName("");
      setRequestKey(`employee-admin-${crypto.randomUUID()}`);
      setResult("success");
    } catch (error) {
      setErrorMessage(submissionMessage(error));
      setResult("error");
    } finally {
      setSubmitting(false);
    }
  };

  const reviewPlan = async () => {
    if (!branchId || !roleId || !loginAddress.trim() || !firstName.trim() || !lastName.trim()) return;
    setSubmitting(true);
    setResult(null);
    setErrorMessage("");
    try {
      setPlan(await planEmployeeOnboarding({
        branch_id: branchId,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        display_name: displayName.trim() || `${firstName.trim()} ${lastName.trim()}`,
        role_ids: [roleId],
        additional_permission_ids: additionalPermissionIds,
        login_email: loginAddress.trim(),
      }));
    } catch (error) {
      setErrorMessage(submissionMessage(error));
      setResult("error");
    } finally {
      setSubmitting(false);
    }
  };

  const updateInvitation = async (operation: "reissue" | "revoke") => {
    if (!onboarding) return;
    setSubmitting(true);
    try {
      const updated = operation === "reissue"
        ? await reissueIdentityOnboarding(onboarding.id)
        : await revokeIdentityOnboarding(onboarding.id);
      setOnboarding(updated);
      setDelivery(await getIdentityOnboardingDelivery(updated.id));
      setResult("success");
    } catch (error) {
      setErrorMessage(submissionMessage(error));
      setResult("error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-2xl space-y-ui-5 pb-ui-8">
      <header>
        <h1 className="text-heading-m">Identity Onboarding</h1>
        <p className="mt-ui-2 text-body-s text-content-muted">
          Prepare a Company-scoped User, Membership, Employee, Branch grant, role,
          and protected invitation through canonical onboarding.
        </p>
      </header>
      {result === "success" && (
        <Alert variant="success" announcement="polite">
          Onboarding was created. Continue with the protected owner activation claim.
        </Alert>
      )}
      {result === "error" && (
        <Alert variant="danger" announcement="assertive">
          {errorMessage}
        </Alert>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Add Employee</CardTitle>
          <CardDescription>
            Duplicate identity and replay checks are enforced server-side. Activation
            material is never shown by this form.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {preparation.state === "loading" ? (
            <Spinner label="Checking Employee onboarding readiness" />
          ) : preparation.state === "blocked" ? (
            <Alert variant="danger">
              <div className="space-y-ui-3">
                <p>{preparation.message}</p>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setPreparation({ state: "loading" });
                    setReadinessAttempt((attempt) => attempt + 1);
                  }}
                >
                  Retry readiness
                </Button>
              </div>
            </Alert>
          ) : (
            <form className="space-y-ui-4" onSubmit={(event) => void submit(event)}>
              <div className="grid gap-ui-3 sm:grid-cols-2">
                <label className="block space-y-ui-2"><span className="text-body-s font-semibold">First name</span><Input value={firstName} onChange={(event) => { setFirstName(event.target.value); setPlan(null); }} required /></label>
                <label className="block space-y-ui-2"><span className="text-body-s font-semibold">Last name</span><Input value={lastName} onChange={(event) => { setLastName(event.target.value); setPlan(null); }} required /></label>
              </div>
              <label className="block space-y-ui-2"><span className="text-body-s font-semibold">Display name</span><Input value={displayName} onChange={(event) => { setDisplayName(event.target.value); setPlan(null); }} placeholder={`${firstName} ${lastName}`.trim()} /></label>
              <label className="block space-y-ui-2">
                <span className="text-body-s font-semibold">Preview Branch</span>
                <select
                  className="min-h-11 w-full rounded-md border border-stroke bg-surface px-ui-3"
                  value={branchId}
                  onChange={(event) => { setBranchId(event.target.value); setPlan(null); }}
                  required
                >
                  <option value="" disabled>
                    Select a Branch
                  </option>
                  {branches.map((branch) => (
                    <option key={branch.id} value={branch.id}>
                      {branch.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block space-y-ui-2">
                <span className="text-body-s font-semibold">Baseline role</span>
                <select className="min-h-11 w-full rounded-md border border-stroke bg-surface px-ui-3" value={roleId} onChange={(event) => { setRoleId(event.target.value); setPlan(null); }} required>
                  {preparation.roles.map((role) => <option key={role.id} value={role.id}>{role.name} — {role.description ?? role.code}</option>)}
                </select>
                <span className="text-body-xs text-content-muted">The role is a starting bundle. Effective authority remains permission- and Branch-scoped.</span>
              </label>
              <fieldset className="space-y-ui-3 rounded-lg border border-stroke p-ui-4">
                <legend className="px-ui-2 font-semibold">Effective permission preview</legend>
                <p className="text-body-xs text-content-muted">Role defaults and explicit additive Employee permissions are shown before onboarding. Branch scope is <strong>{branches.find((branch) => branch.id === branchId)?.name ?? "not selected"}</strong>. Removing a role default requires choosing a narrower baseline role; hidden deny semantics are not invented.</p>
                <div className="grid gap-ui-3 sm:grid-cols-[1fr_auto]">
                  <label><span className="sr-only">Search permissions</span><Input value={permissionSearch} onChange={(event) => setPermissionSearch(event.target.value)} placeholder="Search permission, category, or capability" /></label>
                  <label className="flex min-h-11 items-center gap-ui-2"><input type="checkbox" checked={highImpactOnly} onChange={(event) => setHighImpactOnly(event.target.checked)} /> High-impact only</label>
                </div>
                <div className="max-h-80 space-y-ui-3 overflow-y-auto" aria-live="polite">
                  {Object.entries(permissionGroups).map(([category, items]) => <section key={category} className="rounded-md bg-surface-subtle p-ui-3"><h3 className="font-semibold">{category}</h3><ul className="mt-ui-2 space-y-ui-2">{items?.map((permission) => <li key={permission.id} className="text-body-s"><label className="flex items-start gap-ui-2"><input type="checkbox" className="mt-1" checked={permission.assigned || additionalPermissionIds.includes(permission.id)} disabled={permission.assigned || !permission.assignable} onChange={(event) => { setPlan(null); setAdditionalPermissionIds((current) => event.target.checked ? [...current, permission.id] : current.filter((id) => id !== permission.id)); }} /><span><span className="font-medium">{permission.name}</span>{permission.assigned && <span className="ml-ui-2 text-body-xs text-content-muted">Role default</span>}{permission.high_impact && <span className="ml-ui-2 rounded bg-status-warning/15 px-ui-2 py-0.5 text-body-xs">High impact</span>}<span className="block text-body-xs text-content-muted">{permission.own_data ? "Own data only" : (permission.access_nature ?? "MUTATION").replaceAll("_", " ")} · {permission.description ?? permission.code}</span></span></label></li>)}</ul></section>)}
                  {visiblePermissions.length === 0 && <p className="text-body-s text-content-muted">No role-default permission matches this filter.</p>}
                </div>
              </fieldset>
              {additionalPermissionIds.length > 0 && <Alert variant="warning">Change summary: {additionalPermissionIds.length} explicit Employee permission{additionalPermissionIds.length === 1 ? "" : "s"} will be added beyond the selected role defaults. This advances effective authority when the account activates.</Alert>}
              <label className="block space-y-ui-2">
                <span className="text-body-s font-semibold">
                  Employee login address
                </span>
                <Input
                  type="email"
                  autoComplete="off"
                  value={loginAddress}
                  onChange={(event) => { setLoginAddress(event.target.value); setPlan(null); }}
                  required
                />
              </label>
              <Button
                type="button"
                loading={submitting}
                loadingLabel="Reviewing plan"
                onClick={() => void reviewPlan()}
                disabled={submitting || !branchId || !roleId || !firstName.trim() || !lastName.trim() || !loginAddress.trim()}
              >
                Review Employee plan
              </Button>
              {plan && <section className="space-y-ui-3 rounded-lg border border-stroke p-ui-4" aria-labelledby="onboarding-plan-heading">
                <div className="flex flex-wrap items-center justify-between gap-ui-2"><h3 id="onboarding-plan-heading" className="font-semibold">Plan before apply</h3><Badge variant={plan.safe_to_apply ? "success" : "warning"}>{plan.classification.replaceAll("_", " ")}</Badge></div>
                <dl className="grid gap-ui-2 text-body-s sm:grid-cols-2"><div><dt className="text-content-muted">Identity</dt><dd>{plan.user_action.replaceAll("_", " ")}</dd></div><div><dt className="text-content-muted">Membership</dt><dd>{plan.membership_action.replaceAll("_", " ")}</dd></div><div><dt className="text-content-muted">Employee</dt><dd>{plan.employee_action.replaceAll("_", " ")}</dd></div><div><dt className="text-content-muted">Branch</dt><dd>{plan.branch_action.replaceAll("_", " ")}</dd></div></dl>
                <div className="flex flex-wrap gap-ui-2">{Object.entries(plan.readiness_stages).map(([stage, state]) => <Badge key={stage} variant={state === "READY" ? "success" : "neutral"}>{stage}: {state.replaceAll("_", " ")}</Badge>)}</div>
                {plan.blockers.length > 0 && <Alert variant="warning">Review required: {plan.blockers.map((item) => item.replaceAll("_", " ")).join(" · ")}</Alert>}
                {plan.safe_to_apply && <Button type="submit" loading={submitting} loadingLabel="Creating onboarding">Apply reviewed Employee onboarding</Button>}
              </section>}
            </form>
          )}
        </CardContent>
      </Card>
      {onboarding && delivery && (
        <Card>
          <CardHeader>
            <CardTitle>Invitation readiness</CardTitle>
            <CardDescription>
              Invitation authority and Communications delivery evidence are reported
              separately. A queued message is not proof of delivery.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-ui-4">
            <dl className="grid gap-ui-3 text-body-s sm:grid-cols-2">
              <div>
                <dt className="text-content-muted">Invitation</dt>
                <dd className="font-semibold">{delivery.invitation_status.replaceAll("_", " ")}</dd>
              </div>
              <div>
                <dt className="text-content-muted">Delivery</dt>
                <dd className="font-semibold">{delivery.delivery_status.replaceAll("_", " ")}</dd>
              </div>
              <div>
                <dt className="text-content-muted">Activation</dt>
                <dd className="font-semibold">{onboarding.status.replaceAll("_", " ")}</dd>
              </div>
              <div>
                <dt className="text-content-muted">Provider acceptance</dt>
                <dd className="font-semibold">
                  {delivery.provider_reference_present ? "Provider reference recorded" : "Provider not configured or not accepted"}
                </dd>
              </div>
            </dl>
            {delivery.last_error_code && (
              <Alert variant="warning">
                Delivery requires attention: {delivery.last_error_code.replaceAll("_", " ")}.
              </Alert>
            )}
            <div className="flex flex-wrap gap-ui-3">
              <Button variant="secondary" loading={submitting} onClick={() => void updateInvitation("reissue")}>
                Reissue invitation
              </Button>
              <Button variant="secondary" loading={submitting} onClick={() => void updateInvitation("revoke")}>
                Revoke invitation
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
      <Link className="text-link" to="/administration">
        Back to Administration
      </Link>
    </div>
  );
}
