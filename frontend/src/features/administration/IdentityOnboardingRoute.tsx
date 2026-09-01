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
  getIdentityOnboardingDelivery,
  listPermissions,
  listRoles,
  reissueIdentityOnboarding,
  revokeIdentityOnboarding,
  type IdentityOnboardingDeliveryView,
  type IdentityOnboardingView,
  type CompanyRole,
} from "./api";

const ONBOARDING_PERMISSION = "COMPANY_IDENTITY_ONBOARDING_MANAGE";
const EMPLOYEE_ROLE_CODE = "COMPANY_USER";
const REQUIRED_EMPLOYEE_PERMISSIONS = new Set([
  "COMPANY_TIMEKEEPING_OWN_READ",
  "COMPANY_TIMEKEEPING_OWN_PUNCH",
  "COMPANY_EMPLOYEE_OPERATIONS_OWN_DAY_READ",
  "COMPANY_JOB_READ",
]);

type Preparation =
  | { state: "loading" }
  | { state: "ready"; role: CompanyRole }
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
  const branches = useMemo(
    () => activeCompany?.branches ?? [],
    [activeCompany],
  );
  const initialBranchId =
    activeCompany?.default_branch_id ?? branches[0]?.id ?? "";
  const [branchId, setBranchId] = useState(initialBranchId);
  const [loginAddress, setLoginAddress] = useState("");
  const [preparation, setPreparation] = useState<Preparation>({
    state: "loading",
  });
  const [readinessAttempt, setReadinessAttempt] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<"success" | "error" | null>(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [onboarding, setOnboarding] = useState<IdentityOnboardingView | null>(
    null,
  );
  const [delivery, setDelivery] =
    useState<IdentityOnboardingDeliveryView | null>(null);

  useEffect(() => {
    if (!authorized) return;
    let current = true;
    void listRoles()
      .then(async (roles) => {
        const role = roles.find(
          (candidate) =>
            candidate.code === EMPLOYEE_ROLE_CODE &&
            candidate.status === "active",
        );
        if (!role) return { role: null, permissions: [] };
        return { role, permissions: await listPermissions(role.id) };
      })
      .then(({ role, permissions }) => {
        if (!current) return;
        if (!role) {
          setPreparation({
            state: "blocked",
            message: "The canonical Company Employee role is unavailable.",
          });
          return;
        }
        const assigned = new Set(
          permissions
            .filter((permission) => permission.assigned)
            .map((permission) => permission.code),
        );
        if (
          [...REQUIRED_EMPLOYEE_PERMISSIONS].some((code) => !assigned.has(code))
        ) {
          setPreparation({
            state: "blocked",
            message:
              "The canonical Company Employee role is not ready for ACP Employee onboarding.",
          });
          return;
        }
        setPreparation({ state: "ready", role });
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
    if (preparation.state !== "ready" || !branchId || !loginAddress.trim())
      return;
    setSubmitting(true);
    setResult(null);
    setErrorMessage("");
    try {
      const created = await initiateEmployeeBetaOnboarding({
        request_key: "acp-employee-beta-v1",
        branch_id: branchId,
        first_name: "ACP Employee",
        last_name: "Beta",
        display_name: "ACP Employee Beta",
        employee_type: "employee",
        employee_number_prefix: "EMP-",
        employee_number_width: 4,
        role_ids: [preparation.role.id],
        login_email: loginAddress.trim(),
      });
      setOnboarding(created);
      setDelivery(await getIdentityOnboardingDelivery(created.id));
      setLoginAddress("");
      setResult("success");
    } catch (error) {
      setErrorMessage(submissionMessage(error));
      setResult("error");
    } finally {
      setSubmitting(false);
    }
  };

  const refreshDelivery = async () => {
    if (!onboarding) return;
    try {
      setDelivery(await getIdentityOnboardingDelivery(onboarding.id));
    } catch {
      setErrorMessage("Delivery history could not be refreshed safely.");
      setResult("error");
    }
  };

  const reissue = async () => {
    if (!onboarding) return;
    setSubmitting(true);
    try {
      const next = await reissueIdentityOnboarding(onboarding.id);
      setOnboarding(next);
      setDelivery(await getIdentityOnboardingDelivery(next.id));
      setResult("success");
    } catch (error) {
      setErrorMessage(submissionMessage(error));
      setResult("error");
    } finally {
      setSubmitting(false);
    }
  };

  const revoke = async () => {
    if (!onboarding) return;
    setSubmitting(true);
    try {
      const next = await revokeIdentityOnboarding(onboarding.id);
      setOnboarding(next);
      setDelivery(await getIdentityOnboardingDelivery(next.id));
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
          Create the fixed Preview ACP Employee beta identity through canonical
          Company onboarding.
        </p>
      </header>
      {result === "success" && (
        <Alert variant="success" announcement="polite">
          Onboarding was created. Continue with the protected owner activation
          claim.
        </Alert>
      )}
      {result === "error" && (
        <Alert variant="danger" announcement="assertive">
          {errorMessage}
        </Alert>
      )}
      <Card>
        <CardHeader>
          <CardTitle>ACP Employee beta</CardTitle>
          <CardDescription>
            Identity key: acp-employee-beta-v1. Activation material is never
            shown by this form.
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
            <form
              className="space-y-ui-4"
              onSubmit={(event) => void submit(event)}
            >
              <label className="block space-y-ui-2">
                <span className="text-body-s font-semibold">
                  Preview Branch
                </span>
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
                disabled={submitting || !branchId || !loginAddress.trim()}
              >
                Create beta onboarding
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
      {onboarding && delivery && (
        <Card>
          <CardHeader>
            <CardTitle>Invitation delivery</CardTitle>
            <CardDescription>
              Truthful provider-neutral state for {onboarding.masked_login}.
              Provider acceptance is not proof of delivery.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-ui-4">
            <dl
              className="grid gap-ui-3 sm:grid-cols-2"
              aria-label="Invitation delivery state"
            >
              <div>
                <dt className="text-body-s text-content-muted">Invitation</dt>
                <dd className="font-semibold uppercase">
                  {delivery.invitation_status}
                </dd>
              </div>
              <div>
                <dt className="text-body-s text-content-muted">Delivery</dt>
                <dd className="font-semibold uppercase">
                  {delivery.delivery_status}
                </dd>
              </div>
              <div>
                <dt className="text-body-s text-content-muted">Template</dt>
                <dd>{delivery.template_version ?? "Not prepared"}</dd>
              </div>
              <div>
                <dt className="text-body-s text-content-muted">Attempts</dt>
                <dd>{delivery.retry_count}</dd>
              </div>
            </dl>
            {delivery.last_error_code && (
              <Alert variant="warning">
                Delivery requires review: {delivery.last_error_code}
              </Alert>
            )}
            {delivery.delivery_status === "pending" && (
              <Alert variant="warning">
                Transactional email provider is not configured. The invitation
                remains durable and unsent.
              </Alert>
            )}
            <div className="flex flex-col gap-ui-3 sm:flex-row">
              <Button
                variant="secondary"
                onClick={() => void refreshDelivery()}
              >
                Refresh delivery
              </Button>
              <Button
                variant="secondary"
                disabled={submitting || onboarding.status !== "invited"}
                onClick={() => void reissue()}
              >
                Reissue invitation
              </Button>
              <Button
                variant="destructive"
                disabled={submitting || onboarding.status !== "invited"}
                onClick={() => void revoke()}
              >
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
