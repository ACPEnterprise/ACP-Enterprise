import axios from "axios";
import { Search, ShieldCheck, Unplug } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
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
  ConfirmationDialog,
  Input,
  Spinner,
} from "../../ui";
import type { PermissionDefinition, QboSandboxConnectionState } from "./api";
import {
  disconnectQuickBooksSandbox,
  getQuickBooksSandboxConnection,
  launchQuickBooksProduction,
  launchQuickBooksSandbox,
} from "./api";
import {
  useAssignMembershipRole,
  useCanonicalRoleSync,
  useCanonicalRoleSyncPlan,
  useCreateRole,
  useMemberships,
  usePermissionMutation,
  useRevokeMembershipRole,
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
  const queryClient = useQueryClient();
  const { permissionCodes = [], refreshAuthorization } = useAuth();
  const canAdminister = permissionCodes.includes("COMPANY_ADMINISTER");
  const canReadRoles = permissionCodes.includes("COMPANY_ROLE_READ");
  const canManagePermissions = permissionCodes.includes("COMPANY_PERMISSION_MANAGE");
  const canManageRoles = permissionCodes.includes("COMPANY_ROLE_MANAGE");
  const canReadMemberships = permissionCodes.includes("COMPANY_MEMBERSHIP_READ");
  const canUseRoleWorkflow =
    canReadRoles && canManageRoles && canManagePermissions && canReadMemberships;
  const canonicalRoles = useCanonicalRoleSyncPlan(canReadRoles);
  const canonicalRoleSync = useCanonicalRoleSync();
  const roles = useRoles(canReadRoles);
  const memberships = useMemberships(canUseRoleWorkflow);
  const createRole = useCreateRole();
  const assignMembershipRole = useAssignMembershipRole();
  const revokeMembershipRole = useRevokeMembershipRole();
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(null);
  const selectedRole =
    roles.data?.find((role) => role.id === selectedRoleId) ??
    roles.data?.[0] ??
    null;
  const permissions = useRolePermissions(selectedRole?.id ?? null, canReadRoles);
  const [search, setSearch] = useState("");
  const [pending, setPending] = useState<PendingChange | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [roleCode, setRoleCode] = useState("");
  const [roleName, setRoleName] = useState("");
  const [roleDescription, setRoleDescription] = useState("");
  const [membershipId, setMembershipId] = useState("");
  const [desiredRoleIds, setDesiredRoleIds] = useState<Set<string>>(new Set());
  const [qboPending, setQboPending] = useState(false);
  const [qboError, setQboError] = useState(false);
  const [qboProductionPending, setQboProductionPending] = useState(false);
  const [qboProductionError, setQboProductionError] = useState(false);
  const [qboDisconnectConfirmation, setQboDisconnectConfirmation] =
    useState(false);
  const [qboState, setQboState] = useState<
    QboSandboxConnectionState | "loading"
  >("loading");
  const mutation = usePermissionMutation(pending?.action ?? "grant");
  const activeMemberships = (memberships.data ?? []).filter(
    (membership) => membership.status === "active",
  );
  const selectedMembership = activeMemberships.find(
    (membership) => membership.id === membershipId,
  );
  const assignableRoles = (roles.data ?? []).filter(
    (role) => role.status === "active" && role.code !== "OWNER",
  );

  const submitRole = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMutationError(null);
    try {
      const created = await createRole.mutateAsync({
        code: roleCode.trim(),
        name: roleName.trim(),
        description: roleDescription.trim() || null,
      });
      setSelectedRoleId(created.id);
      await queryClient.invalidateQueries({ queryKey: ["administration", "roles"] });
      setRoleCode("");
      setRoleName("");
      setRoleDescription("");
    } catch {
      setMutationError("The role was not created. Review the values and current authorization.");
    }
  };

  const submitMembershipRoles = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedMembership) return;
    setMutationError(null);
    try {
      const current = new Set(selectedMembership.role_ids);
      const additions = [...desiredRoleIds].filter((roleId) => !current.has(roleId));
      const removals = [...current].filter(
        (roleId) =>
          !desiredRoleIds.has(roleId) &&
          assignableRoles.some((role) => role.id === roleId),
      );
      for (const roleId of additions) {
        await assignMembershipRole.mutateAsync({ membershipId, roleId });
      }
      for (const roleId of removals) {
        await revokeMembershipRole.mutateAsync({ membershipId, roleId });
      }
      await queryClient.invalidateQueries({ queryKey: ["administration", "memberships"] });
      await refreshAuthorization();
    } catch {
      setMutationError("The access change was not accepted. Refresh and review current authority before retrying.");
    }
  };

  const applyCanonicalRoles = async () => {
    if (!canonicalRoles.data?.safe_to_apply) return;
    await canonicalRoleSync.mutateAsync(canonicalRoles.data.plan_digest);
    await refreshAuthorization();
    await queryClient.invalidateQueries({ queryKey: ["administration"] });
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
      await refreshAuthorization();
      await queryClient.invalidateQueries({ queryKey: ["administration"] });
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

  const connectQuickBooksProduction = async () => {
    setQboProductionError(false);
    setQboProductionPending(true);
    try {
      await launchQuickBooksProduction();
    } catch {
      setQboProductionError(true);
      setQboProductionPending(false);
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
      {permissionCodes.includes("PLATFORM_FACTORY_CONTROL_READ") && (
        <Card>
          <CardHeader>
            <CardTitle>Factory Control</CardTitle>
            <CardDescription>
              View the private Twelve Hats roadmap, scorecard, gates, and live Factory state.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link
              className="inline-flex min-h-11 items-center justify-center rounded-md bg-action-primary px-ui-4 text-body-s font-semibold text-content-inverse"
              to="/administration/factory-control"
            >
              Open Factory Control
            </Link>
          </CardContent>
        </Card>
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
      {permissionCodes.includes("COMPANY_COMMUNICATIONS_READ") && (
        <Card>
          <CardHeader>
            <CardTitle>Communications readiness</CardTitle>
            <CardDescription>
              Review Email, SMS, webhook, message-catalog, and policy admission gates.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link
              className="inline-flex min-h-11 items-center justify-center rounded-md bg-action-primary px-ui-4 text-body-s font-semibold text-content-inverse"
              to="/administration/communications"
            >
              Review Communications
            </Link>
          </CardContent>
        </Card>
      )}
      {canAdminister && (
        <Card className="border-warning/50">
          <CardHeader>
            <CardTitle>QuickBooks REAL company — read-only migration source</CardTitle>
            <CardDescription>
              Connect the real QuickBooks company for verified GET-only migration
              acquisition. This does not authorize QuickBooks changes, payments,
              Accounting posting, or ACP Production.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-ui-3">
            <Badge variant="warning">REAL / PRODUCTION QUICKBOOKS</Badge>
            {qboProductionError && (
              <Alert variant="danger" announcement="assertive">
                Real QuickBooks authorization could not be started. No company was
                connected.
              </Alert>
            )}
            <Button
              loading={qboProductionPending}
              loadingLabel="Opening real QuickBooks authorization"
              disabled={qboProductionPending}
              onClick={() => void connectQuickBooksProduction()}
            >
              Connect REAL QuickBooks — Read Only
            </Button>
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
      {canUseRoleWorkflow && (
        <Card>
          <CardHeader>
            <CardTitle>Create Company role</CardTitle>
            <CardDescription>
              Create an empty role in the current Company. Permissions and Membership
              assignment remain separate audited actions; Branch access is unchanged.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="grid gap-ui-3" onSubmit={(event) => void submitRole(event)}>
              <label>
                <span className="text-body-s font-semibold">Role code</span>
                <Input required value={roleCode} onChange={(event) => setRoleCode(event.target.value)} placeholder="SOURCE4_PREVIEW_ADMISSION" />
              </label>
              <label>
                <span className="text-body-s font-semibold">Role name</span>
                <Input required value={roleName} onChange={(event) => setRoleName(event.target.value)} placeholder="SOURCE.4 Preview Admission" />
              </label>
              <label>
                <span className="text-body-s font-semibold">Description</span>
                <Input value={roleDescription} onChange={(event) => setRoleDescription(event.target.value)} placeholder="Optional operational purpose" />
              </label>
              <Button type="submit" disabled={!roleCode.trim() || !roleName.trim()} loading={createRole.isPending} loadingLabel="Creating role">
                Create role
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
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
                      {canManagePermissions && selectedRole.code !== "OWNER" && <Button
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
      {canUseRoleWorkflow && (
        <Card>
          <CardHeader>
            <CardTitle>Users / Employees / Access</CardTitle>
            <CardDescription>
              Choose a person, select normal job roles, and save once. Canonical Owner
              authority is protected by its separate high-risk workflow.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {memberships.isError ? (
              <Alert variant="danger">Visible Memberships could not be loaded.</Alert>
            ) : (
              <form className="grid gap-ui-4" onSubmit={(event) => void submitMembershipRoles(event)}>
                <label>
                  <span className="text-body-s font-semibold">Active Membership</span>
                  <select
                    aria-label="Active Membership"
                    className="mt-ui-2 min-h-11 w-full rounded-md border border-stroke bg-surface px-ui-3"
                    value={membershipId}
                    onChange={(event) => {
                      const nextMembershipId = event.target.value;
                      setMembershipId(nextMembershipId);
                      const nextMembership = activeMemberships.find(
                        (membership) => membership.id === nextMembershipId,
                      );
                      setDesiredRoleIds(new Set(nextMembership?.role_ids ?? []));
                    }}
                  >
                    <option value="">Select active Membership</option>
                    {activeMemberships.map((membership) => (
                      <option key={membership.id} value={membership.id}>
                        {membership.display_name || membership.email || `Membership ${membership.id.slice(0, 8)}`}
                        {membership.branch_name ? ` — ${membership.branch_name}` : ""}
                        {` — ${membership.status.charAt(0).toUpperCase()}${membership.status.slice(1)}`}
                        {membership.email && membership.email !== membership.display_name ? ` · ${membership.email}` : ""}
                      </option>
                    ))}
                  </select>
                </label>
                {selectedMembership && (
                  <fieldset className="grid gap-ui-2 rounded-lg border border-stroke p-ui-4">
                    <legend className="px-ui-2 text-body-s font-semibold">Roles &amp; Permissions</legend>
                    {assignableRoles.map((role) => (
                      <label key={role.id} className="flex min-h-11 items-start gap-ui-3 rounded-md p-ui-2 hover:bg-surface-subtle">
                        <input
                          type="checkbox"
                          className="mt-1 size-4"
                          checked={desiredRoleIds.has(role.id)}
                          onChange={(event) => {
                            const next = new Set(desiredRoleIds);
                            if (event.target.checked) next.add(role.id);
                            else next.delete(role.id);
                            setDesiredRoleIds(next);
                          }}
                        />
                        <span>
                          <span className="block text-body-s font-semibold">{role.name}</span>
                          <span className="block text-body-xs text-content-muted">{role.description ?? role.code}</span>
                        </span>
                      </label>
                    ))}
                  </fieldset>
                )}
                <Button
                  type="submit"
                  disabled={!selectedMembership}
                  loading={assignMembershipRole.isPending || revokeMembershipRole.isPending}
                  loadingLabel="Saving access"
                >
                  Save access
                </Button>
              </form>
            )}
          </CardContent>
        </Card>
      )}
      {canManagePermissions && pending && selectedRole && (
        <ConfirmationDialog
          title={`${pending.action === "grant" ? "Grant" : "Remove"} permission?`}
          description={`${pending.permission.code} ${pending.action === "grant" ? "will be granted to" : "will be removed from"} ${selectedRole.name}. Current authorization will refresh after this one change.`}
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
