import axios from "axios";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router";

import { useAuth } from "../../auth";
import {
  Alert,
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
  initiateEmployeeBetaOnboarding,
  listRoles,
  type CompanyRole,
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

  if (!authorized) {
    return (
      <Alert variant="danger" announcement="assertive">
        You are not authorized to initiate Company identity onboarding.
      </Alert>
    );
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (preparation.state !== "ready" || !branchId || !roleId || !loginAddress.trim() || !firstName.trim() || !lastName.trim()) return;
    setSubmitting(true);
    setResult(null);
    setErrorMessage("");
    try {
      await initiateEmployeeBetaOnboarding({
        request_key: requestKey,
        branch_id: branchId,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        display_name: displayName.trim() || `${firstName.trim()} ${lastName.trim()}`,
        employee_type: "employee",
        employee_number_prefix: "EMP-",
        employee_number_width: 4,
        role_ids: [roleId],
        login_email: loginAddress.trim(),
      });
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
                <label className="block space-y-ui-2"><span className="text-body-s font-semibold">First name</span><Input value={firstName} onChange={(event) => setFirstName(event.target.value)} required /></label>
                <label className="block space-y-ui-2"><span className="text-body-s font-semibold">Last name</span><Input value={lastName} onChange={(event) => setLastName(event.target.value)} required /></label>
              </div>
              <label className="block space-y-ui-2"><span className="text-body-s font-semibold">Display name</span><Input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder={`${firstName} ${lastName}`.trim()} /></label>
              <label className="block space-y-ui-2">
                <span className="text-body-s font-semibold">Preview Branch</span>
                <select
                  className="min-h-11 w-full rounded-md border border-stroke bg-surface px-ui-3"
                  value={branchId}
                  onChange={(event) => setBranchId(event.target.value)}
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
                <select className="min-h-11 w-full rounded-md border border-stroke bg-surface px-ui-3" value={roleId} onChange={(event) => setRoleId(event.target.value)} required>
                  {preparation.roles.map((role) => <option key={role.id} value={role.id}>{role.name} — {role.description ?? role.code}</option>)}
                </select>
                <span className="text-body-xs text-content-muted">The role is a starting bundle. Effective authority remains permission- and Branch-scoped.</span>
              </label>
              <label className="block space-y-ui-2">
                <span className="text-body-s font-semibold">
                  Employee login address
                </span>
                <Input
                  type="email"
                  autoComplete="off"
                  value={loginAddress}
                  onChange={(event) => setLoginAddress(event.target.value)}
                  required
                />
              </label>
              <Button
                type="submit"
                loading={submitting}
                loadingLabel="Creating onboarding"
                disabled={submitting || !branchId || !roleId || !firstName.trim() || !lastName.trim() || !loginAddress.trim()}
              >
                Prepare Employee onboarding
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
      <Link className="text-link" to="/administration">
        Back to Administration
      </Link>
    </div>
  );
}
