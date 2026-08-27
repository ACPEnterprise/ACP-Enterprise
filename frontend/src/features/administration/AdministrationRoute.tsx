import axios from "axios";
import { Search, ShieldCheck, Unplug } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";

import { useAuth } from "../../auth";
import { Alert, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, ConfirmationDialog, Input, Spinner } from "../../ui";
import type { PermissionDefinition, QboSandboxConnectionState } from "./api";
import { disconnectQuickBooksSandbox, getQuickBooksSandboxConnection, launchQuickBooksSandbox } from "./api";
import { usePermissionMutation, useRolePermissions, useRoles } from "./hooks";

type PendingChange = { action: "grant" | "remove"; permission: PermissionDefinition };

function errorStatus(error: unknown): number | undefined {
  return axios.isAxiosError(error) ? error.response?.status : undefined;
}

export function AdministrationRoute() {
  const navigate = useNavigate();
  const { permissionCodes = [], requireReauthentication } = useAuth();
  const roles = useRoles();
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(null);
  const selectedRole = roles.data?.find((role) => role.id === selectedRoleId) ?? roles.data?.[0] ?? null;
  const permissions = useRolePermissions(selectedRole?.id ?? null);
  const [search, setSearch] = useState("");
  const [pending, setPending] = useState<PendingChange | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [qboPending, setQboPending] = useState(false);
  const [qboError, setQboError] = useState(false);
  const [qboDisconnectConfirmation, setQboDisconnectConfirmation] = useState(false);
  const [qboState, setQboState] = useState<QboSandboxConnectionState | "loading">("loading");
  const mutation = usePermissionMutation(pending?.action ?? "grant");

  useEffect(() => {
    if (!permissionCodes.includes("COMPANY_ADMINISTER")) return;
    let active = true;
    void getQuickBooksSandboxConnection()
      .then((connectionState) => { if (active) setQboState(connectionState); })
      .catch(() => { if (active) setQboState("unavailable"); });
    return () => { active = false; };
  }, [permissionCodes]);

  const visiblePermissions = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (permissions.data ?? []).filter((permission) =>
      !query || `${permission.code} ${permission.name} ${permission.description ?? ""}`.toLowerCase().includes(query),
    );
  }, [permissions.data, search]);

  if (errorStatus(roles.error) === 403) {
    return <Alert variant="danger" announcement="assertive">You are not authorized to administer Company roles.</Alert>;
  }
  if (roles.isPending) return <div className="grid min-h-48 place-items-center"><Spinner label="Loading role administration" /></div>;
  if (roles.isError) return <Alert variant="danger">Role Administration could not be loaded. Try again.</Alert>;

  const applyChange = async () => {
    if (!pending || !selectedRole) return;
    setMutationError(null);
    try {
      await mutation.mutateAsync({ roleId: selectedRole.id, permissionId: pending.permission.id });
      setPending(null);
      requireReauthentication();
      await navigate("/login", {
        replace: true,
        state: { from: "/administration", authorizationChanged: true },
      });
    } catch {
      setMutationError("The permission change was not accepted. Your role was not changed.");
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
        <div className="flex items-center gap-ui-3"><ShieldCheck aria-hidden="true" /><h1 className="text-heading-m">Role Administration</h1></div>
        <p className="mt-ui-2 text-body-s text-content-muted">Review one role and change one canonical permission at a time.</p>
      </header>
      {mutationError && <Alert variant="danger" announcement="assertive">{mutationError}</Alert>}
      {permissionCodes.includes("COMPANY_ADMINISTER") && <Card>
        <CardHeader>
          <CardTitle>QuickBooks Development sandbox</CardTitle>
          <CardDescription>Connect only the configured Intuit Development company. Production is unavailable.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-ui-3">
          {qboState === "loading" && <Spinner label="Loading QuickBooks sandbox connection" />}
          {qboState === "connected" && <Badge variant="success">Connected</Badge>}
          {qboState === "not_connected" && <Badge variant="neutral">Not connected</Badge>}
          {qboState === "disconnecting" && <Badge variant="warning">Disconnecting</Badge>}
          {qboState === "disconnect_failed" && <Alert variant="danger" announcement="assertive">Disconnect failed. The existing connection was retained.</Alert>}
          {qboState === "unavailable" && <Alert variant="danger" announcement="assertive">QuickBooks sandbox connection status is unavailable.</Alert>}
          {qboError && qboState !== "disconnect_failed" && <Alert variant="danger" announcement="assertive">QuickBooks sandbox authorization could not be started. No company was connected.</Alert>}
          {(qboState === "connected" || qboState === "disconnect_failed") && <Button
            leadingIcon={<Unplug />}
            loading={qboPending}
            loadingLabel="Disconnecting QuickBooks sandbox"
            disabled={qboPending}
            onClick={() => setQboDisconnectConfirmation(true)}
          >
            Disconnect QuickBooks Sandbox
          </Button>}
          {qboState === "not_connected" && <Button
            leadingIcon={<Unplug />}
            loading={qboPending}
            loadingLabel="Opening QuickBooks sandbox"
            disabled={qboPending}
            onClick={() => void connectQuickBooksSandbox()}
          >
            Connect QuickBooks Sandbox
          </Button>}
        </CardContent>
      </Card>}
      <Card>
        <CardHeader><CardTitle>Company roles</CardTitle><CardDescription>Select the role whose access you want to review.</CardDescription></CardHeader>
        <CardContent>
          <div className="grid gap-ui-2 sm:grid-cols-2">
            {(roles.data ?? []).map((role) => (
              <Button key={role.id} variant={selectedRole?.id === role.id ? "primary" : "outline"} fullWidth onClick={() => setSelectedRoleId(role.id)}>
                {role.name} · {role.code}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>
      {selectedRole && <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-ui-2"><div><CardTitle>{selectedRole.name}</CardTitle><CardDescription>{selectedRole.code}</CardDescription></div><Badge variant={selectedRole.status === "active" ? "success" : "warning"}>{selectedRole.status}</Badge></div>
        </CardHeader>
        <CardContent className="space-y-ui-4">
          <label className="relative block"><span className="sr-only">Search permissions</span><Search aria-hidden="true" className="absolute left-ui-3 top-1/2 size-4 -translate-y-1/2 text-content-muted" /><Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search permissions" className="pl-ui-10" /></label>
          {errorStatus(permissions.error) === 403 ? <Alert variant="danger">You are not authorized to view role permissions.</Alert> : permissions.isError ? <Alert variant="danger">Permissions could not be loaded.</Alert> : permissions.isPending ? <Spinner label="Loading permissions" /> : (
            <ul className="space-y-ui-3">
              {visiblePermissions.map((permission) => <li key={permission.id} className="rounded-lg border border-stroke p-ui-4">
                <div className="flex flex-col gap-ui-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0"><div className="flex flex-wrap items-center gap-ui-2"><code className="break-all text-body-s font-semibold">{permission.code}</code><Badge variant={permission.reconciliation_required ? "warning" : permission.assigned ? "success" : "neutral"}>{permission.reconciliation_required ? "Reconciliation required" : permission.assigned ? "Assigned" : "Not assigned"}</Badge></div><p className="mt-ui-1 text-body-s text-content-muted">{permission.description || permission.name}</p></div>
                  <Button className="shrink-0 sm:min-w-28" variant={permission.assigned ? "outline" : "primary"} disabled={!permission.assignable} onClick={() => setPending({ action: permission.assigned ? "remove" : "grant", permission })}>{permission.assigned ? "Remove" : "Grant"}</Button>
                </div>
              </li>)}
            </ul>
          )}
        </CardContent>
      </Card>}
      {pending && selectedRole && <ConfirmationDialog
        title={`${pending.action === "grant" ? "Grant" : "Remove"} permission?`}
        description={`${pending.permission.code} ${pending.action === "grant" ? "will be granted to" : "will be removed from"} ${selectedRole.name}. You will sign in again after this change.`}
        confirmLabel={pending.action === "grant" ? "Grant permission" : "Remove permission"}
        destructive={pending.action === "remove"}
        pending={mutation.isPending}
        onCancel={() => setPending(null)}
        onConfirm={() => void applyChange()}
      />}
      {qboDisconnectConfirmation && <ConfirmationDialog
        title="Disconnect QuickBooks Sandbox?"
        description="Intuit access will be revoked before ACP removes the protected local sandbox connection. Connection history and sandbox configuration will be preserved."
        confirmLabel="Disconnect QuickBooks Sandbox"
        destructive
        pending={qboPending}
        onCancel={() => setQboDisconnectConfirmation(false)}
        onConfirm={() => void disconnectSandbox()}
      />}
    </div>
  );
}
