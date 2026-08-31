import axios from "axios";
import { Search, ShieldCheck, Unplug } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";

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
  ConfirmationDialog,
  Input,
  Spinner,
} from "../../ui";
import type { PermissionDefinition, QboSandboxConnectionState } from "./api";
import {
  disconnectQuickBooksSandbox,
  getQuickBooksSandboxConnection,
  launchQuickBooksSandbox,
} from "./api";
import {
  useCanonicalRoleSync,
  useCanonicalRoleSyncPlan,
  usePermissionMutation,
  useRolePermissions,
  useRoles,
} from "./hooks";
import { MigrationWorkspace } from "./MigrationWorkspace";

type PendingChange = {
  action: "grant" | "remove";
  permission: PermissionDefinition;
};

function errorStatus(error: unknown): number | undefined {
  return axios.isAxiosError(error) ? error.response?.status : undefined;
}

export function AdministrationRoute() {
  const navigate = useNavigate();
  const { permissionCodes = [], requireReauthentication } = useAuth();
  const canAdminister = permissionCodes.includes("COMPANY_ADMINISTER");
  const canReadRoles = permissionCodes.includes("COMPANY_ROLE_READ");
  const canManagePermissions = permissionCodes.includes("COMPANY_PERMISSION_MANAGE");
  const canManageRoles = permissionCodes.includes("COMPANY_ROLE_MANAGE");
  const canonicalRoles = useCanonicalRoleSyncPlan(canReadRoles);
  const canonicalRoleSync = useCanonicalRoleSync();
  const roles = useRoles(canReadRoles);
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(null);
  const selectedRole =
    roles.data?.find((role) => role.id === selectedRoleId) ??
    roles.data?.[0] ??
    null;
  const permissions = useRolePermissions(selectedRole?.id ?? null, canReadRoles);
  const [search, setSearch] = useState("");
  const [pending, setPending] = useState<PendingChange | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [qboPending, setQboPending] = useState(false);
  const [qboError, setQboError] = useState(false);
  const [qboDisconnectConfirmation, setQboDisconnectConfirmation] =
    useState(false);
  const [qboState, setQboState] = useState<
    QboSandboxConnectionState | "loading"
  >("loading");
  const mutation = usePermissionMutation(pending?.action ?? "grant");

  const applyCanonicalRoles = async () => {
    if (!canonicalRoles.data?.safe_to_apply) return;
    await canonicalRoleSync.mutateAsync(canonicalRoles.data.plan_digest);
    requireReauthentication();
    await navigate("/login", {
      replace: true,
      state: { from: "/administration", authorizationChanged: true },
    });
  };

  useEffect(() => {
    if (!canAdminister) return;
    let active = true;
    void getQuickBooksSandboxConnection()
      .then((connectionState) => {
        if (active) setQboState(connectionState);
      })
      .catch(() => {
        if (active) setQboState("unavailable");
      });
    return () => {
      active = false;
    };
  }, [canAdminister]);

  const visiblePermissions = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (permissions.data ?? []).filter(
      (permission) =>
        !query ||
        `${permission.code} ${permission.name} ${permission.description ?? ""}`
          .toLowerCase()
          .includes(query),
    );
  }, [permissions.data, search]);

  if ((!canReadRoles && !canAdminister) || errorStatus(roles.error) === 403) {
    return (
      <Alert variant="danger" announcement="assertive">
        You are not authorized to administer Company roles.
      </Alert>
    );
  }
  if (canReadRoles && roles.isPending)
    return (
      <div className="grid min-h-48 place-items-center">
        <Spinner label="Loading role administration" />
      </div>
    );
  if (canReadRoles && roles.isError)
    return (
      <Alert variant="danger">
        Role Administration could not be loaded. Try again.
      </Alert>
    );

  const applyChange = async () => {
    if (!pending || !selectedRole) return;
    setMutationError(null);
    try {
      await mutation.mutateAsync({
        roleId: selectedRole.id,
        permissionId: pending.permission.id,
      });
      setPending(null);
      requireReauthentication();
      await navigate("/login", {
        replace: true,
        state: { from: "/administration", authorizationChanged: true },
      });
    } catch {
      setMutationError(
        "The permission change was not accepted. Your role was not changed.",
      );
      setPending(null);
    }
  };

  const connectQuickBooksSandbox = async () => {
    setQboError(false);
    setQboPending(true);
    try {
      await launchQuickBooksSandbox();
    } catch {
      setQboError(true);
      setQboPending(false);
    }
  };

  const disconnectSandbox = async () => {
    setQboDisconnectConfirmation(false);
    setQboError(false);
    setQboPending(true);
    setQboState("disconnecting");
    try {
      const state = await disconnectQuickBooksSandbox();
      setQboState(state);
      setQboPending(false);
    } catch {
      setQboState("disconnect_failed");
      setQboError(true);
      setQboPending(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-5xl space-y-ui-5 pb-ui-8">
      <header>
        <div className="flex items-center gap-ui-3">
          <ShieldCheck aria-hidden="true" />
          <h1 className="text-heading-m">Role Administration</h1>
        </div>
        <p className="mt-ui-2 text-body-s text-content-muted">
          Review one role and change one canonical permission at a time.
        </p>
      </header>
      {mutationError && (
        <Alert variant="danger" announcement="assertive">
          {mutationError}
        </Alert>
      )}
      {permissionCodes.includes("COMPANY_IDENTITY_ONBOARDING_MANAGE") && (
        <Card>
          <CardHeader>
            <CardTitle>Identity Onboarding</CardTitle>
            <CardDescription>
              Initiate the fixed Preview ACP Employee beta identity through protected
              Company onboarding.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link
              className="inline-flex min-h-11 items-center justify-center rounded-md bg-action-primary px-ui-4 text-body-s font-semibold text-content-inverse"
              to="/administration/identity-onboarding"
            >
              Open Identity Onboarding
            </Link>
          </CardContent>
        </Card>
      )}
      {canAdminister && (
        <Card>
          <CardHeader>
            <CardTitle>QuickBooks Development sandbox</CardTitle>
            <CardDescription>
              Connect only the configured Intuit Development company. Production
              is unavailable.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-ui-3">
            {qboState === "loading" && (
              <Spinner label="Loading QuickBooks sandbox connection" />
            )}
            {qboState === "connected" && (
              <Badge variant="success">Connected</Badge>
            )}
            {qboState === "not_connected" && (
              <Badge variant="neutral">Not connected</Badge>
            )}
            {qboState === "disconnecting" && (
              <Badge variant="warning">Disconnecting</Badge>
            )}
            {qboState === "disconnect_failed" && (
              <Alert variant="danger" announcement="assertive">
                Disconnect failed. The existing connection was retained.
              </Alert>
            )}
            {qboState === "unavailable" && (
              <Alert variant="danger" announcement="assertive">
                QuickBooks sandbox connection status is unavailable.
              </Alert>
            )}
            {qboError && qboState !== "disconnect_failed" && (
              <Alert variant="danger" announcement="assertive">
                QuickBooks sandbox authorization could not be started. No
                company was connected.
              </Alert>
            )}
            {(qboState === "connected" || qboState === "disconnect_failed") && (
              <Button
                leadingIcon={<Unplug />}
                loading={qboPending}
                loadingLabel="Disconnecting QuickBooks sandbox"
                disabled={qboPending}
                onClick={() => setQboDisconnectConfirmation(true)}
              >
                Disconnect QuickBooks Sandbox
              </Button>
            )}
            {qboState === "not_connected" && (
              <Button
                leadingIcon={<Unplug />}
                loading={qboPending}
                loadingLabel="Opening QuickBooks sandbox"
                disabled={qboPending}
                onClick={() => void connectQuickBooksSandbox()}
              >
                Connect QuickBooks Sandbox
              </Button>
            )}
          </CardContent>
        </Card>
      )}
      {canAdminister && <MigrationWorkspace />}
      {canReadRoles && (
        <Card>
          <CardHeader>
            <CardTitle>Canonical role readiness</CardTitle>
            <CardDescription>
              Preview and safely reconcile accepted system roles. Tenant-created
              roles and Membership assignments are never changed.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-ui-3">
            {canonicalRoles.isPending && <Spinner label="Checking canonical roles" />}
            {canonicalRoles.isError && (
              <Alert variant="danger">Canonical role readiness is unavailable.</Alert>
            )}
            {canonicalRoles.data && (
              <>
                <ul className="grid gap-ui-2 sm:grid-cols-2">
                  {canonicalRoles.data.items.map((item) => (
                    <li key={item.code} className="rounded-lg border border-stroke p-ui-3">
                      <div className="flex flex-wrap items-center justify-between gap-ui-2">
                        <strong>{item.code}</strong>
                        <Badge
                          variant={
                            item.classification === "ALREADY_CONFORMING"
                              ? "success"
                              : item.classification.includes("CONFLICT") ||
                                  item.classification.includes("UNSAFE")
                                ? "danger"
                                : "warning"
                          }
                        >
                          {item.classification.replaceAll("_", " ")}
                        </Badge>
                      </div>
                      {item.missing_permissions.length > 0 && (
                        <p className="mt-ui-2 text-body-xs text-content-muted">
                          {item.missing_permissions.length} accepted permission(s) missing
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
                {canonicalRoleSync.isError && (
                  <Alert variant="danger">
                    Reconciliation was not applied. Refresh the preview and review conflicts.
                  </Alert>
                )}
                {canManageRoles && canManagePermissions && (
                  <Button
                    disabled={!canonicalRoles.data.safe_to_apply}
                    loading={canonicalRoleSync.isPending}
                    loadingLabel="Reconciling canonical roles"
                    onClick={() => void applyCanonicalRoles()}
                  >
                    Apply safe reconciliation
                  </Button>
                )}
                {!canonicalRoles.data.safe_to_apply && (
                  <Alert variant="warning">
                    A role identity conflict requires review. No changes can be applied.
                  </Alert>
                )}
              </>
            )}
          </CardContent>
        </Card>
      )}
      {!canReadRoles && <Alert variant="information">Role administration requires role-read permission.</Alert>}
      {canReadRoles && <Card>
        <CardHeader>
          <CardTitle>Company roles</CardTitle>
          <CardDescription>
            Select the role whose access you want to review.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-ui-2 sm:grid-cols-2">
            {(roles.data ?? []).map((role) => (
              <Button
                key={role.id}
                variant={selectedRole?.id === role.id ? "primary" : "outline"}
                fullWidth
                onClick={() => setSelectedRoleId(role.id)}
              >
                {role.name} · {role.code}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>}
      {canReadRoles && selectedRole && (
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-start justify-between gap-ui-2">
              <div>
                <CardTitle>{selectedRole.name}</CardTitle>
                <CardDescription>{selectedRole.code}</CardDescription>
              </div>
              <Badge
                variant={
                  selectedRole.status === "active" ? "success" : "warning"
                }
              >
                {selectedRole.status}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-ui-4">
            <label className="relative block">
              <span className="sr-only">Search permissions</span>
              <Search
                aria-hidden="true"
                className="absolute left-ui-3 top-1/2 size-4 -translate-y-1/2 text-content-muted"
              />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search permissions"
                className="pl-ui-10"
              />
            </label>
            {errorStatus(permissions.error) === 403 ? (
              <Alert variant="danger">
                You are not authorized to view role permissions.
              </Alert>
            ) : permissions.isError ? (
              <Alert variant="danger">Permissions could not be loaded.</Alert>
            ) : permissions.isPending ? (
              <Spinner label="Loading permissions" />
            ) : (
              <ul className="space-y-ui-3">
                {visiblePermissions.map((permission) => (
                  <li
                    key={permission.id}
                    className="rounded-lg border border-stroke p-ui-4"
                  >
                    <div className="flex flex-col gap-ui-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-ui-2">
                          <code className="break-all text-body-s font-semibold">
                            {permission.code}
                          </code>
                          <Badge
                            variant={
                              permission.reconciliation_required
                                ? "warning"
                                : permission.assigned
                                  ? "success"
                                  : "neutral"
                            }
                          >
                            {permission.reconciliation_required
                              ? "Reconciliation required"
                              : permission.assigned
                                ? "Assigned"
                                : "Not assigned"}
                          </Badge>
                        </div>
                        <p className="mt-ui-1 text-body-s text-content-muted">
                          {permission.description || permission.name}
                        </p>
                      </div>
                      {canManagePermissions && <Button
                        className="shrink-0 sm:min-w-28"
                        variant={permission.assigned ? "outline" : "primary"}
                        disabled={!permission.assignable}
                        onClick={() =>
                          setPending({
                            action: permission.assigned ? "remove" : "grant",
                            permission,
                          })
                        }
                      >
                        {permission.assigned ? "Remove" : "Grant"}
                      </Button>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}
      {canManagePermissions && pending && selectedRole && (
        <ConfirmationDialog
          title={`${pending.action === "grant" ? "Grant" : "Remove"} permission?`}
          description={`${pending.permission.code} ${pending.action === "grant" ? "will be granted to" : "will be removed from"} ${selectedRole.name}. You will sign in again after this change.`}
          confirmLabel={
            pending.action === "grant"
              ? "Grant permission"
              : "Remove permission"
          }
          destructive={pending.action === "remove"}
          pending={mutation.isPending}
          onCancel={() => setPending(null)}
          onConfirm={() => void applyChange()}
        />
      )}
      {qboDisconnectConfirmation && (
        <ConfirmationDialog
          title="Disconnect QuickBooks Sandbox?"
          description="Intuit access will be revoked before ACP removes the protected local sandbox connection. Connection history and sandbox configuration will be preserved."
          confirmLabel="Disconnect QuickBooks Sandbox"
          destructive
          pending={qboPending}
          onCancel={() => setQboDisconnectConfirmation(false)}
          onConfirm={() => void disconnectSandbox()}
        />
      )}
    </div>
  );
}
