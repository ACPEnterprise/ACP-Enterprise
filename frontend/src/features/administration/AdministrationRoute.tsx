import axios from "axios";
import { Search, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router";

import { useAuth } from "../../auth";
import { Alert, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, ConfirmationDialog, Input, Spinner } from "../../ui";
import type { PermissionDefinition } from "./api";
import { usePermissionMutation, useRolePermissions, useRoles } from "./hooks";

type PendingChange = { action: "grant" | "remove"; permission: PermissionDefinition };

function errorStatus(error: unknown): number | undefined {
  return axios.isAxiosError(error) ? error.response?.status : undefined;
}

export function AdministrationRoute() {
  const navigate = useNavigate();
  const { requireReauthentication } = useAuth();
  const roles = useRoles();
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(null);
  const selectedRole = roles.data?.find((role) => role.id === selectedRoleId) ?? roles.data?.[0] ?? null;
  const permissions = useRolePermissions(selectedRole?.id ?? null);
  const [search, setSearch] = useState("");
  const [pending, setPending] = useState<PendingChange | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const mutation = usePermissionMutation(pending?.action ?? "grant");

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

  return (
    <div className="mx-auto w-full max-w-5xl space-y-ui-5 pb-ui-8">
      <header>
        <div className="flex items-center gap-ui-3"><ShieldCheck aria-hidden="true" /><h1 className="text-heading-m">Role Administration</h1></div>
        <p className="mt-ui-2 text-body-s text-content-muted">Review one role and change one canonical permission at a time.</p>
      </header>
      {mutationError && <Alert variant="danger" announcement="assertive">{mutationError}</Alert>}
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
                  <div className="min-w-0"><div className="flex flex-wrap items-center gap-ui-2"><code className="break-all text-body-s font-semibold">{permission.code}</code><Badge variant={permission.assigned ? "success" : "neutral"}>{permission.assigned ? "Assigned" : "Not assigned"}</Badge></div><p className="mt-ui-1 text-body-s text-content-muted">{permission.description || permission.name}</p></div>
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
    </div>
  );
}
